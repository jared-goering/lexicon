"""FastAPI server — dashboard, search, Q&A, and management API."""

from __future__ import annotations

from collections import Counter
import mimetypes
from pathlib import Path
import secrets
from typing import Any
import unicodedata

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lexicon import __version__
from lexicon.compiler import WikiCompiler
from lexicon.config import get_settings
from lexicon.connectors.url import URLConnector
from lexicon.export import Exporter
from lexicon.linker import AutoLinker
from lexicon.linter import KBLinter
from lexicon.qa import QAAgent
from lexicon.research import ResearchAgent
from lexicon.ultramemory_client import UltramemoryClient
from lexicon.utils import safe_slug

app = FastAPI(
    title="lexicon",
    description="LLM-compiled personal knowledge base",
    version=__version__,
)

settings = get_settings()

# --- CORS (restrictive defaults — localhost only) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8899", "http://127.0.0.1:8899"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Optional bearer-token auth for write endpoints ---

async def require_auth(request: Request) -> None:
    """If LEXICON_API_TOKEN is set, require a matching Bearer token."""
    token = settings.api_token
    if not token:
        return
    auth = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    prefix = "bearer "
    if auth.lower().startswith(prefix):
        provided = auth[len(prefix):].strip()
    else:
        provided = ""
    if not provided or not secrets.compare_digest(token, provided):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
um_client = UltramemoryClient(settings)
compiler = WikiCompiler(settings, client=um_client)
linker = AutoLinker(settings)
linter = KBLinter(settings)
exporter = Exporter(settings)
research_agent = ResearchAgent(settings, client=um_client, compiler=compiler, linker=linker)
qa = QAAgent(settings, client=um_client, research_agent=research_agent)
url_connector = URLConnector(settings, client=um_client)

# --- Static files ---
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Track last compilation timestamp for auto-refresh
import time
import threading
_last_compiled_at: float = 0.0
_processing_count: int = 0
_processing_items: list[dict[str, str]] = []  # [{source, title}]
_processing_lock = threading.Lock()

# --- Request/Response models ---


class IngestRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    title: str | None = None
    compile: bool = True


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class AskRequest(BaseModel):
    question: str
    article_slug: str | None = None


class ResearchRequest(BaseModel):
    query: str
    num_results: int = 10
    compile: bool = True


class CompileRequest(BaseModel):
    topic: str | None = None


class ExportRequest(BaseModel):
    topic: str
    format: str = "report"  # "slides", "report", "briefing", "html", "pdf"


class SnapshotRequest(BaseModel):
    slug: str


# --- Routes ---


@app.get("/", response_class=HTMLResponse)
async def root() -> FileResponse:
    """Serve the SPA shell."""
    return FileResponse(str(_static_dir / "index.html"), media_type="text/html")


@app.get("/api/stats")
async def stats() -> dict[str, Any]:
    """Return aggregate KB statistics for the UI footer."""
    articles_dir = settings.articles_dir
    article_count = len(list(articles_dir.glob("*.md"))) if articles_dir.exists() else 0
    return {
        "article_count": article_count,
        "llm_model": settings.llm_model,
        "system_state": "SUBSCRIBED" if article_count > 0 else "READY",
    }


@app.get("/api/topics")
async def topics() -> dict[str, Any]:
    """Return the top topics for the home-screen cards (most recently modified first)."""
    articles_dir = settings.articles_dir
    if not articles_dir.exists():
        return {"topics": []}

    items = []
    for md_file in articles_dir.glob("*.md"):
        stat = md_file.stat()
        items.append({
            "slug": md_file.stem,
            "title": md_file.stem.replace("-", " ").title(),
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    # Most recently modified first
    items.sort(key=lambda x: x["modified"], reverse=True)
    return {"topics": items}


@app.get("/api/graph")
async def graph() -> dict[str, Any]:
    """Return article graph data for the knowledge-graph UI."""
    articles = linker.scan_articles()
    if not articles:
        return {"nodes": [], "edges": [], "clusters": []}

    cluster_palette = ["#E8913A", "#3A8FE8", "#6B3AE8", "#3AE89B"]
    cluster_labels = _build_graph_cluster_labels(articles)
    slug_by_title = {info.title.casefold(): info.slug for info in articles.values()}

    nodes = []
    edges = []
    seen_edges: set[tuple[str, str]] = set()

    for info in sorted(articles.values(), key=lambda item: item.title.casefold()):
        cluster_id = _cluster_id_for_article(info, cluster_labels)
        nodes.append({
            "id": info.slug,
            "title": info.title,
            "source_count": info.source_count,
            "headings": info.headings,
            "cluster": cluster_id,
        })

        for link_title in info.outbound_links:
            target_slug = slug_by_title.get(link_title.casefold())
            if not target_slug or target_slug == info.slug:
                continue
            edge = (info.slug, target_slug)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            edges.append({"source": info.slug, "target": target_slug})

    clusters = [
        {"id": idx, "color": color, "label": label}
        for idx, (color, label) in enumerate(zip(cluster_palette, cluster_labels, strict=False))
    ]
    return {"nodes": nodes, "edges": edges, "clusters": clusters}


@app.get("/api/processing")
async def processing_status() -> dict[str, Any]:
    """Return the current number of ingest/compile jobs in progress."""
    with _processing_lock:
        items = list(_processing_items)
    return {"processing": _processing_count, "items": items}


@app.post("/api/ingest", dependencies=[Depends(require_auth)])
async def ingest(req: IngestRequest) -> dict[str, Any]:
    """Ingest a URL or raw text into the knowledge base."""
    global _processing_count
    item = {"source": req.url or "manual", "title": req.title or req.url or "Untitled"}
    with _processing_lock:
        _processing_count += 1
        _processing_items.append(item)
    try:
        return await _do_ingest(req)
    finally:
        with _processing_lock:
            _processing_count = max(0, _processing_count - 1)
            try:
                _processing_items.remove(item)
            except ValueError:
                pass


async def _do_ingest(req: IngestRequest) -> dict[str, Any]:
    """Internal ingest implementation."""
    source = "manual"
    title = req.title or "Untitled"
    memories_created = 0
    chunk = None

    if req.url:
        try:
            chunk = await url_connector.fetch_and_ingest(req.url)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {exc}")
        source = req.url
        title = chunk.get("title", "Untitled")
        memories_created = chunk.get("ultramemory", {}).get("memories_created", 0)
    elif req.text:
        result = await um_client.ingest(
            text=req.text,
            session_key=um_client._make_session_key("api"),
            agent_id="uk-api",
        )
        memories_created = result.get("memories_created", 0)
    else:
        raise HTTPException(status_code=400, detail="Provide either 'url' or 'text'")

    # Auto-compile: compile an article from the ingested content only
    compiled_article = None
    if req.compile:
        try:
            topic_hint = title if title != "Untitled" else (req.text or "")[:200]
            # Use the actual ingested text rather than searching all memories,
            # which would pull in unrelated content from prior ingests.
            ingest_text = req.text or ""
            if req.url and chunk:
                ingest_text = chunk.get("text", "")
            if topic_hint and ingest_text.strip():
                chunks = [{"text": ingest_text, "source": source}]
                path = await compiler.compile_topic(topic_hint, chunks)
                linker.generate_backlinks()
                linker.rebuild_index()
                compiled_article = str(path)
                global _last_compiled_at
                _last_compiled_at = time.time()
        except Exception:
            pass  # Compilation is best-effort; ingest still succeeded

    return {
        "status": "ingested",
        "source": source,
        "title": title,
        "memories_created": memories_created,
        "compiled": compiled_article,
    }


_MEDIA_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".mp3", ".wav", ".mp4", ".mov"}
_MEDIA_IMAGE_EXT = {".png", ".jpg", ".jpeg"}
_MEDIA_AUDIO_EXT = {".mp3", ".wav"}
_MEDIA_VIDEO_EXT = {".mp4", ".mov"}
_MAX_IMAGE = 20 * 1024 * 1024   # 20 MB
_MAX_AUDIO = 25 * 1024 * 1024   # 25 MB
_MAX_VIDEO = 50 * 1024 * 1024   # 50 MB


@app.post("/api/ingest-media", dependencies=[Depends(require_auth)])
async def ingest_media(file: UploadFile = File(...)) -> dict[str, Any]:
    """Ingest a media file (image/audio/video) into the knowledge base."""
    import tempfile

    global _processing_count

    # Validate extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _MEDIA_ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(_MEDIA_ALLOWED_EXT))}",
        )

    # Determine size limit
    if ext in _MEDIA_IMAGE_EXT:
        max_size = _MAX_IMAGE
    elif ext in _MEDIA_AUDIO_EXT:
        max_size = _MAX_AUDIO
    else:
        max_size = _MAX_VIDEO

    # Reject oversized uploads early via Content-Length header
    if file.size is not None and file.size > max_size:
        max_mb = max_size // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File too large. Max {max_mb}MB for {ext} files.")

    # Save to temp file and validate size during streaming
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_size:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                max_mb = max_size // (1024 * 1024)
                raise HTTPException(status_code=413, detail=f"File too large. Max {max_mb}MB for {ext} files.")
            tmp.write(chunk)
        tmp.close()

        item = {"source": file.filename or "media", "title": file.filename or "Media upload"}
        with _processing_lock:
            _processing_count += 1
            _processing_items.append(item)

        try:
            result = await um_client.ingest_media(
                file_path=tmp.name,
                session_key=um_client._make_session_key("media"),
                agent_id="uk-api",
            )

            # Auto-compile article from the generated description
            compiled_article = None
            description = result.get("description", "")
            if description.strip():
                title_hint = Path(file.filename or "media").stem.replace("-", " ").replace("_", " ").title()
                chunks = [{"text": description, "source": file.filename or "media-upload"}]
                try:
                    path = await compiler.compile_topic(title_hint, chunks)
                    linker.generate_backlinks()
                    linker.rebuild_index()
                    compiled_article = str(path)
                    global _last_compiled_at
                    _last_compiled_at = time.time()
                except Exception:
                    pass  # Compilation is best-effort

            return {
                "status": "ingested",
                "source": file.filename,
                "title": result.get("description", file.filename)[:120],
                "memories_created": 1,
                "compiled": compiled_article,
            }
        finally:
            with _processing_lock:
                _processing_count = max(0, _processing_count - 1)
                try:
                    _processing_items.remove(item)
                except ValueError:
                    pass
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@app.post("/api/search")
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


@app.post("/api/ask", dependencies=[Depends(require_auth)])
async def ask(req: AskRequest) -> dict[str, Any]:
    """Ask a question and get an answer with citations."""
    question = req.question
    # If asking from an article page, prepend article content as context
    if req.article_slug:
        slug = safe_slug(req.article_slug)
        article_path = settings.articles_dir / f"{slug}.md"
        if article_path.exists():
            article_text = article_path.read_text()[:4000]  # Cap context size
            question = f"[Context from article '{safe_slug}':\n{article_text}\n]\n\nQuestion: {req.question}"
    response = await qa.answer_or_research(question)
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


@app.post("/api/research", dependencies=[Depends(require_auth)])
async def research(req: ResearchRequest) -> dict[str, Any]:
    """Research a topic via Exa web search and ingest results into Ultramemory."""
    if not settings.exa_api_key:
        return JSONResponse(
            status_code=503,
            content={"error": "EXA_API_KEY not configured. Set it in your environment."},
        )
    result = await research_agent.research(
        req.query,
        num_results=req.num_results,
        compile=req.compile,
    )
    return {
        "query": req.query,
        "results_found": len(result.results),
        "memories_created": result.memories_created,
        "compiled": bool(result.article_paths),
        "articles": [str(path) for path in result.article_paths],
        "links_added": result.links_added,
        "results": [{"title": r.title, "url": r.url, "score": r.score} for r in result.results],
    }


@app.get("/api/articles")
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


@app.get("/api/articles/{slug}")
async def get_article(slug: str) -> dict[str, Any]:
    """Read a specific article by slug."""
    slug = safe_slug(slug)
    article_path = settings.articles_dir / f"{slug}.md"
    if not article_path.exists():
        raise HTTPException(status_code=404, detail=f"Article not found: {slug}")

    content = article_path.read_text(encoding="utf-8")
    return {"slug": slug, "content": content}


@app.delete("/api/articles/{slug}", dependencies=[Depends(require_auth)])
async def delete_article(slug: str) -> dict[str, Any]:
    """Delete a wiki article by slug. Removes the .md file and rebuilds links/index."""
    slug = safe_slug(slug)
    article_path = settings.articles_dir / f"{slug}.md"
    if not article_path.exists():
        raise HTTPException(status_code=404, detail=f"Article not found: {slug}")
    article_path.unlink()
    # Rebuild backlinks and index after removal
    linker.generate_backlinks()
    linker.rebuild_index()
    global _last_compiled_at
    _last_compiled_at = time.time()
    return {"status": "deleted", "slug": slug}


@app.post("/api/compile", dependencies=[Depends(require_auth)])
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
            global _last_compiled_at
            _last_compiled_at = time.time()
            return {"status": "compiled", "topic": req.topic, "articles": 1, "path": str(path)}
        return {"status": "no_data", "topic": req.topic, "articles": 0}
    else:
        paths = await compiler.recompile_all()
        linker.generate_backlinks()
        linker.rebuild_index()
        _last_compiled_at = time.time()
        return {"status": "compiled", "articles": len(paths)}


@app.get("/api/last-compiled")
async def last_compiled() -> dict[str, Any]:
    """Return the timestamp of the last successful compilation (for auto-refresh)."""
    return {"last_compiled_at": _last_compiled_at}


@app.post("/api/lint")
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


@app.post("/api/export")
async def export_article(req: ExportRequest) -> dict[str, Any]:
    """Export an article in the specified format."""
    export_fn = {
        "slides": exporter.to_slides,
        "report": exporter.to_report,
        "briefing": exporter.to_briefing,
        "html": exporter.to_html,
        "pdf": exporter.to_pdf,
    }.get(req.format)

    if not export_fn:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format: {req.format}. Use slides, report, briefing, html, or pdf.",
        )

    try:
        result = export_fn(req.topic)
        return {
            "status": "exported",
            "format": result.format,
            "output_path": str(result.output_path),
            "filename": result.output_path.name,
            "word_count": result.word_count,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Article not found: {req.topic}")


@app.get("/api/exports/{filename}")
async def download_export(filename: str) -> FileResponse:
    """Serve exported files from the knowledge base exports directory."""
    exports_dir = settings.kb_dir / "exports"
    target = (exports_dir / filename).resolve()
    try:
        target.relative_to(exports_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid export filename.") from exc

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Export not found: {filename}")

    media_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(str(target), media_type=media_type or "application/octet-stream", filename=target.name)


@app.post("/api/snapshot")
async def snapshot_article(req: SnapshotRequest) -> FileResponse:
    """Generate a static article snapshot and return it as a download."""
    try:
        result = exporter.snapshot_article(req.slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Article not found: {req.slug}") from exc

    return FileResponse(str(result.output_path), media_type="text/html", filename=result.output_path.name)


@app.get("/api/snapshot/{slug}")
async def snapshot_article_direct(slug: str) -> FileResponse:
    """Generate a static article snapshot and serve it directly."""
    slug = safe_slug(slug)
    try:
        result = exporter.snapshot_article(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Article not found: {slug}") from exc

    return FileResponse(str(result.output_path), media_type="text/html", filename=result.output_path.name)


@app.post("/api/export-all")
async def export_all_articles() -> FileResponse:
    """Generate a self-contained HTML export of the entire knowledge base."""
    result = exporter.export_all()
    return FileResponse(str(result.output_path), media_type="text/html", filename=result.output_path.name)


def _build_graph_cluster_labels(articles: dict[str, Any]) -> list[str]:
    """Choose four stable cluster labels from article headings or title ranges."""
    heading_counts = Counter(
        info.headings[0].strip()
        for info in articles.values()
        if info.headings and info.headings[0].strip()
    )
    if len(heading_counts) >= 4:
        top_headings = sorted(heading_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        return [heading for heading, _count in top_headings[:4]]
    return ["A-F", "G-L", "M-R", "S-Z"]


def _cluster_id_for_article(info: Any, cluster_labels: list[str]) -> int:
    """Map an article into one of the four graph clusters."""
    if cluster_labels == ["A-F", "G-L", "M-R", "S-Z"]:
        first_char = _graph_bucket_char(info.title)
        if first_char <= "F":
            return 0
        if first_char <= "L":
            return 1
        if first_char <= "R":
            return 2
        return 3

    heading = info.headings[0].strip() if info.headings else ""
    if heading in cluster_labels:
        return cluster_labels.index(heading)

    # Preserve four clusters even when an article falls outside the top heading groups.
    first_char = _graph_bucket_char(info.title)
    return min((ord(first_char) - ord("A")) // 6 if "A" <= first_char <= "Z" else 3, 3)


def _graph_bucket_char(title: str) -> str:
    """Normalize the first title character for stable ASCII cluster bucketing."""
    first_char = (title or "").strip()[:1]
    if not first_char:
        return "#"

    normalized = unicodedata.normalize("NFKD", first_char)
    ascii_char = normalized.encode("ascii", "ignore").decode("ascii")[:1]
    return (ascii_char or first_char).upper()
