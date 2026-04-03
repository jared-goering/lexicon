"""Exa web search connector for active knowledge research."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ultraknowledge.config import Settings, get_settings


@dataclass
class SearchResult:
    """A single search result from Exa."""

    title: str
    url: str
    text: str
    score: float = 0.0
    published_date: str | None = None


class ExaConnector:
    """Research topics via Exa's neural search API.

    Exa provides semantic search over the web, returning full-text content
    that can be directly ingested into the knowledge base.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.settings.exa_api_key:
                raise ValueError("EXA_API_KEY is required for web search. Set it in your environment.")
            from exa_py import Exa

            self._client = Exa(api_key=self.settings.exa_api_key)
        return self._client

    async def research(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Search the web for a topic and return full-text results.

        Uses Exa's neural search for semantic matching, then fetches
        the full text content of each result for ingestion.
        """
        response = await asyncio.to_thread(
            self.client.search_and_contents,
            query=query,
            num_results=num_results,
            text=True,

        )

        results = []
        for item in response.results:
            try:
                text = (item.text or "").strip()
                if not text:
                    continue
                results.append(
                    SearchResult(
                        title=item.title or "Untitled",
                        url=item.url,
                        text=text,
                        score=getattr(item, "score", 0.0),
                        published_date=getattr(item, "published_date", None),
                    )
                )
            except Exception:
                continue
        return results

    async def auto_enrich(self, topic: str, existing_sources: list[str] | None = None) -> list[SearchResult]:
        """Automatically find new sources for a topic, excluding known URLs.

        Useful for periodically enriching articles with fresh information.
        """
        results = await self.research(topic)

        if existing_sources:
            results = [r for r in results if r.url not in existing_sources]

        return results

    async def watch(self, query: str, seen_urls: set[str] | None = None) -> list[SearchResult]:
        """Check for new results matching a query since last check.

        Maintains a set of seen URLs to only return genuinely new results.
        Designed to be called periodically (e.g., via cron or watch command).
        """
        if seen_urls is None:
            seen_urls = set()

        results = await self.research(query, num_results=20)
        new_results = [r for r in results if r.url not in seen_urls]

        # Update seen set
        for r in new_results:
            seen_urls.add(r.url)

        return new_results

    def to_chunks(self, results: list[SearchResult]) -> list[dict[str, Any]]:
        """Convert search results into chunk dicts ready for Ultramemory ingestion."""
        return [
            {
                "text": r.text,
                "source": r.url,
                "title": r.title,
                "metadata": {
                    "type": "web_search",
                    "published_date": r.published_date,
                    "score": r.score,
                },
            }
            for r in results
        ]
