"""URL connector — fetches web pages and extracts readable content for ingestion."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from readabilipy import simple_json_from_html_string

from ultraknowledge.config import Settings, get_settings


class URLConnector:
    """Fetch URLs, extract readable content, and prepare for ingestion."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch_and_ingest(self, url: str) -> dict[str, Any]:
        """Fetch a URL, extract readable text, and return a chunk dict.

        Uses readabilipy for article extraction (similar to Firefox Reader View).
        Falls back to raw text if extraction fails.
        """
        html = await self._fetch(url)
        extracted = self._extract(html, url)
        return extracted

    async def fetch_batch(self, urls: list[str]) -> list[dict[str, Any]]:
        """Fetch multiple URLs concurrently."""
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "ultraknowledge/0.1"},
        ) as client:
            results = []
            for url in urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    extracted = self._extract(response.text, url)
                    results.append(extracted)
                except httpx.HTTPError as e:
                    results.append({
                        "text": "",
                        "source": url,
                        "title": f"Error fetching {url}",
                        "metadata": {"type": "url", "error": str(e)},
                    })
            return results

    async def _fetch(self, url: str) -> str:
        """Fetch raw HTML from a URL."""
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "ultraknowledge/0.1"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _extract(self, html: str, url: str) -> dict[str, Any]:
        """Extract readable content from HTML using readabilipy."""
        article = simple_json_from_html_string(html, use_readability=True)

        title = article.get("title") or urlparse(url).netloc
        # readabilipy returns plain_text as a list of dicts with 'text' keys
        plain_content = article.get("plain_text") or []
        if isinstance(plain_content, list):
            text = "\n\n".join(
                item["text"] for item in plain_content if isinstance(item, dict) and "text" in item
            )
        else:
            text = str(plain_content)

        if not text.strip():
            # Fallback: strip tags naively
            import re

            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()[:5000]

        return {
            "text": text,
            "source": url,
            "title": title,
            "metadata": {
                "type": "url",
                "domain": urlparse(url).netloc,
            },
        }
