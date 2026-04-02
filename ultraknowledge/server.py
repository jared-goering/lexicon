"""FastAPI server — dashboard, search, Q&A, and management API."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ultraknowledge.compiler import WikiCompiler
from ultraknowledge.config import get_settings
from ultraknowledge.connectors.url import URLConnector
from ultraknowledge.connectors.web_search import ExaConnector
from ultraknowledge.export import Exporter
from ultraknowledge.linker import AutoLinker
from ultraknowledge.linter import KBLinter
from ultraknowledge.qa import QAAgent
from ultraknowledge.ultramemory_client import UltramemoryClient

app = FastAPI(
    title="ultraknowledge",
    description="LLM-compiled personal knowledge base",
    version="0.1.0",
)

settings = get_settings()
um_client = UltramemoryClient(settings)
compiler = WikiCompiler(settings, client=um_client)
linker = AutoLinker(settings)
qa = QAAgent(settings, client=um_client)
linter = KBLinter(settings)
exporter = Exporter(settings)
exa = ExaConnector(settings)
url_connector = URLConnector(settings, client=um_client)


# --- Request/Response models ---


class IngestRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    title: str | None = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class AskRequest(BaseModel):
    question: str


class ResearchRequest(BaseModel):
    query: str
    num_results: int = 10


class CompileRequest(BaseModel):
    topic: str | None = None


class ExportRequest(BaseModel):
    topic: str
    format: str = "report"  # "slides", "report", "briefing"


# --- Routes ---


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    """Simple HTML dashboard showing KB stats and recent activity."""
    articles_dir = settings.articles_dir
    article_count = len(list(articles_dir.glob("*.md"))) if articles_dir.exists() else 0

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ultraknowledge</title>
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #e0e0e0; background: #1a1a2e; }}
            h1 {{ color: #e94560; }}
            .stat {{ display: inline-block; padding: 1rem 2rem; margin: 0.5rem; background: #16213e; border-radius: 8px; border: 1px solid #0f3460; }}
            .stat .number {{ font-size: 2rem; font-weight: bold; color: #e94560; }}
            .stat .label {{ color: #a0a0b0; font-size: 0.9rem; }}
            a {{ color: #e94560; }}
            code {{ background: #16213e; padding: 0.2rem 0.4rem; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <h1>ultraknowledge</h1>
        <p>LLM-compiled personal knowledge base</p>

        <div>
            <div class="stat">
                <div class="number">{article_count}</div>
                <div class="label">Articles</div>
            </div>
            <div class="stat">
                <div class="number">{settings.llm_model.split('/')[-1]}</div>
                <div class="label">LLM Model</div>
            </div>
        </div>

        <h2>API Endpoints</h2>
        <ul>
            <li><code>POST /ingest</code> — Ingest a URL or text</li>
            <li><code>POST /search</code> — Semantic search</li>
            <li><code>POST /ask</code> — Ask a question</li>
            <li><code>POST /research</code> — Research a topic via Exa</li>
            <li><code>GET /articles</code> — List all articles</li>
            <li><code>GET /articles/{{slug}}</code> — Read an article</li>
            <li><code>POST /compile</code> — Trigger wiki compilation</li>
            <li><code>POST /lint</code> — Run KB quality checks</li>
            <li><code>POST /export</code> — Export an article</li>
        </ul>

        <p>See <a href="/docs">/docs</a> for interactive API documentation.</p>
    </body>
    </html>
    """


@app.post("/ingest")
async def ingest(req: IngestRequest) -> dict[str, Any]:
    """Ingest a URL or raw text into the knowledge base."""
    if req.url:
        chunk = await url_connector.fetch_and_ingest(req.url)
        return {
            "status": "ingested",
            "source": req.url,
            "title": chunk["title"],
            "memories_created": chunk.get("ultramemory", {}).get("memories_created", 0),
        }
    elif req.text:
        result = await um_client.ingest(
            text=req.text,
            session_key=um_client._make_session_key("api"),
            agent_id="uk-api",
        )
        return {
            "status": "ingested",
            "source": "manual",
            "title": req.title or "Untitled",
            "memories_created": result.get("memories_created", 0),
        }
    else:
        raise HTTPException(status_code=400, detail="Provide either 'url' or 'text'")


@app.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    """Semantic search across the knowledge base via Ultramemory."""
    results = await um_client.search(req.query, top_k=req.limit)
    return {
        "query": req.query,
        "results": [
            {
                "id": r.get("id"),
                "content": r.get("content", ""),
                "category": r.get("category"),
                "confidence": r.get("confidence"),
                "similarity": r.get("similarity"),
            }
            for r in results
        ],
    }


@app.post("/ask")
async def ask(req: AskRequest) -> dict[str, Any]:
    """Ask a question and get an answer with citations."""
    response = await qa.answer_or_research(req.question)
    return {
        "answer": response.answer,
        "citations": [
            {"title": c.article_title, "path": c.article_path, "score": c.relevance_score}
            for c in response.citations
        ],
        "confidence": response.confidence,
        "needs_research": response.needs_research,
        "suggested_queries": response.suggested_queries,
    }


@app.post("/research")
async def research(req: ResearchRequest) -> dict[str, Any]:
    """Research a topic via Exa web search and ingest results into Ultramemory."""
    results = await exa.research(req.query, num_results=req.num_results)
    chunks = exa.to_chunks(results)

    # Send research results to Ultramemory
    memories_created = 0
    session_key = um_client._make_session_key("research")
    for chunk in chunks:
        text = chunk.get("text", "")
        if text.strip():
            result = await um_client.ingest(
                text=text,
                session_key=session_key,
                agent_id="uk-research",
            )
            memories_created += result.get("memories_created", 0)

    return {
        "query": req.query,
        "results_found": len(results),
        "memories_created": memories_created,
        "results": [{"title": r.title, "url": r.url, "score": r.score} for r in results],
    }


@app.get("/articles")
async def list_articles() -> dict[str, Any]:
    """List all wiki articles."""
    articles_dir = settings.articles_dir
    if not articles_dir.exists():
        return {"articles": []}

    articles = []
    for md_file in sorted(articles_dir.glob("*.md")):
        stat = md_file.stat()
        articles.append({
            "slug": md_file.stem,
            "title": md_file.stem.replace("-", " ").title(),
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    return {"articles": articles}


@app.get("/articles/{slug}")
async def get_article(slug: str) -> dict[str, Any]:
    """Read a specific article by slug."""
    article_path = settings.articles_dir / f"{slug}.md"
    if not article_path.exists():
        raise HTTPException(status_code=404, detail=f"Article not found: {slug}")

    content = article_path.read_text(encoding="utf-8")
    return {"slug": slug, "content": content}


@app.post("/compile")
async def compile_kb(req: CompileRequest) -> dict[str, Any]:
    """Trigger wiki compilation — either a single topic or full recompile."""
    if req.topic:
        # Fetch chunks related to the topic from Ultramemory
        results = await um_client.search(req.topic, top_k=50, include_source=True)
        chunks = [
            {"text": r.get("content", ""), "source": r.get("source_session", "ultramemory")}
            for r in results
        ]
        if chunks:
            path = await compiler.compile_topic(req.topic, chunks)
            linker.generate_backlinks()
            linker.rebuild_index()
            return {"status": "compiled", "topic": req.topic, "articles": 1, "path": str(path)}
        return {"status": "no_data", "topic": req.topic, "articles": 0}
    else:
        paths = await compiler.recompile_all()
        linker.generate_backlinks()
        linker.rebuild_index()
        return {"status": "compiled", "articles": len(paths)}


@app.post("/lint")
async def lint_kb() -> dict[str, Any]:
    """Run quality checks on the knowledge base."""
    report = await linter.lint()
    return {
        "summary": report.summary(),
        "articles_checked": report.articles_checked,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "article": i.article,
                "details": i.details,
            }
            for i in report.issues
        ],
    }


@app.post("/export")
async def export_article(req: ExportRequest) -> dict[str, Any]:
    """Export an article in the specified format."""
    export_fn = {
        "slides": exporter.to_slides,
        "report": exporter.to_report,
        "briefing": exporter.to_briefing,
    }.get(req.format)

    if not export_fn:
        raise HTTPException(status_code=400, detail=f"Unknown format: {req.format}. Use slides, report, or briefing.")

    try:
        result = export_fn(req.topic)
        return {
            "status": "exported",
            "format": result.format,
            "output_path": str(result.output_path),
            "word_count": result.word_count,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Article not found: {req.topic}")
