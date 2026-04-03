"""Research orchestration for web search, ingestion, compilation, and linking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lexicon.compiler import WikiCompiler
from lexicon.config import Settings, get_settings
from lexicon.connectors.web_search import ExaConnector, SearchResult
from lexicon.linker import AutoLinker
from lexicon.ultramemory_client import UltramemoryClient


RESEARCH_TITLE_RE = re.compile(r"^Source Title:\s*(.+)$", re.MULTILINE)
RESEARCH_URL_RE = re.compile(r"^Source URL:\s*(.+)$", re.MULTILINE)
RESEARCH_DATE_RE = re.compile(r"^Published Date:\s*(.+)$", re.MULTILINE)


@dataclass
class ResearchRun:
    """Summary of a research cycle."""

    topic: str
    num_results: int
    compiled: bool
    results: list[SearchResult] = field(default_factory=list)
    memories_created: int = 0
    article_paths: list[Path] = field(default_factory=list)
    links_added: int = 0
    failed_results: list[str] = field(default_factory=list)


def build_research_document(result: SearchResult) -> str:
    """Build a memory payload that preserves source metadata for later citation."""
    published = result.published_date or "unknown"
    return (
        f"Source Title: {result.title}\n"
        f"Source URL: {result.url}\n"
        f"Published Date: {published}\n"
        f"Search Score: {(result.score or 0.0):.3f}\n\n"
        f"{result.text.strip()}"
    )


def extract_research_metadata(text: str) -> dict[str, str]:
    """Extract source metadata embedded in a research memory payload."""
    title_match = RESEARCH_TITLE_RE.search(text)
    url_match = RESEARCH_URL_RE.search(text)
    date_match = RESEARCH_DATE_RE.search(text)
    return {
        "title": title_match.group(1).strip() if title_match else "",
        "url": url_match.group(1).strip() if url_match else "",
        "published_date": date_match.group(1).strip() if date_match else "",
    }


class ResearchAgent:
    """Orchestrates research: search -> ingest -> compile -> link."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: UltramemoryClient | None = None,
        connector: ExaConnector | None = None,
        compiler: WikiCompiler | None = None,
        linker: AutoLinker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or UltramemoryClient(self.settings)
        self.connector = connector or ExaConnector(self.settings)
        self.compiler = compiler or WikiCompiler(self.settings, client=self.client)
        self.linker = linker or AutoLinker(self.settings)

    async def research(
        self,
        topic: str,
        num_results: int = 10,
        compile: bool = True,
    ) -> ResearchRun:
        """Run a full research pass for a topic."""
        results = await self.connector.research(topic, num_results=num_results)
        research_run = ResearchRun(
            topic=topic,
            num_results=num_results,
            compiled=compile,
            results=results,
        )

        if not results:
            return research_run

        session_key = self.client._make_session_key("research")
        compile_chunks: list[dict[str, str]] = []
        for result in results:
            document = build_research_document(result)
            try:
                ingest_result = await self.client.ingest(
                    text=document,
                    session_key=session_key,
                    agent_id="uk-research",
                    document_date=result.published_date,
                )
            except Exception:
                research_run.failed_results.append(result.url)
                continue

            research_run.memories_created += ingest_result.get("memories_created", 0)
            compile_chunks.append(
                {
                    "text": document,
                    "source": result.url,
                    "title": result.title,
                }
            )

        if compile and compile_chunks:
            article_path = await self.compiler.compile_topic(topic, compile_chunks)
            link_report = self.linker.generate_backlinks()
            self.linker.rebuild_index()
            research_run.article_paths.append(article_path)
            research_run.links_added = link_report.links_added

        return research_run
