"""URL connector — fetches web pages and extracts readable content for ingestion."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ultraknowledge.config import Settings, get_settings
from ultraknowledge.ultramemory_client import UltramemoryClient


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    """Try trafilatura first for high-quality text extraction."""
    try:
        import trafilatura

        text = trafilatura.extract(html, url=url, include_comments=False)
        return text
    except ImportError:
        return None


def _extract_with_readabilipy(html: str) -> tuple[str, str]:
    """Fallback to readabilipy for article extraction."""
    try:
        from readabilipy import simple_json_from_html_string

        article = simple_json_from_html_string(html, use_readability=True)
        title = article.get("title") or ""
        plain_content = article.get("plain_text") or []
        if isinstance(plain_content, list):
            text = "\n\n".join(
                item["text"] for item in plain_content if isinstance(item, dict) and "text" in item
            )
        else:
            text = str(plain_content)
        return title, text
    except ImportError:
        return "", ""


class URLConnector:
    """Fetch URLs, extract readable content, and send to Ultramemory."""

    def __init__(
        self, settings: Settings | None = None, client: UltramemoryClient | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or UltramemoryClient(self.settings)

    async def fetch_and_ingest(self, url: str) -> dict[str, Any]:
        """Fetch a URL, extract readable text, send to Ultramemory, and return metadata."""
        html = await self._fetch(url)
        extracted = self._extract(html, url)

        # Send to Ultramemory for memory extraction and storage
        if extracted["text"].strip():
            session_key = self.client._make_session_key("url")
            result = await self.client.ingest(
                text=extracted["text"],
                session_key=session_key,
                agent_id="uk-url",
            )
            extracted["ultramemory"] = {
                "memories_created": result.get("memories_created", 0),
                "session_key": session_key,
            }

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
        """Extract readable content from HTML. Tries trafilatura first, then readabilipy."""
        title = urlparse(url).netloc
        text = ""

        # Try trafilatura first (higher quality extraction)
        extracted = _extract_with_trafilatura(html, url)
        if extracted:
            text = extracted
        else:
            # Fallback to readabilipy
            rp_title, rp_text = _extract_with_readabilipy(html)
            if rp_title:
                title = rp_title
            text = rp_text

        if not text.strip():
            # Last resort: strip tags naively
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
