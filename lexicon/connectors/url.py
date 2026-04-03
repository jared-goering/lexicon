"""URL connector — fetches web pages and extracts readable content for ingestion."""

from __future__ import annotations

import re as _re
from typing import Any
from urllib.parse import urlparse

import httpx

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

# Matches twitter.com and x.com tweet URLs
_TWEET_RE = _re.compile(
    r"^https?://(?:(?:www\.)?(?:twitter|x)\.com)/(\w+)/status/(\d+)"
)

from lexicon.config import Settings, get_settings
from lexicon.ultramemory_client import UltramemoryClient


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

    # Pattern for t.co shortened URLs
    _TCO_RE = _re.compile(r"https?://t\.co/\w+")

    async def _resolve_tco_links(self, text: str) -> list[dict[str, str]]:
        """Resolve t.co shortened URLs and return their final destinations."""
        tco_urls = self._TCO_RE.findall(text)
        resolved = []
        if not tco_urls:
            return resolved
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                for tco in tco_urls[:5]:  # cap at 5 links
                    try:
                        resp = await client.head(tco, follow_redirects=True)
                        final = str(resp.url)
                        # Skip links back to twitter/x.com (self-referential)
                        parsed = urlparse(final)
                        if parsed.netloc.replace("www.", "") not in ("twitter.com", "x.com"):
                            resolved.append({"short": tco, "url": final})
                    except httpx.HTTPError:
                        pass
        except httpx.HTTPError:
            pass
        return resolved

    async def _fetch_tweet(self, url: str) -> dict[str, Any] | None:
        """Extract tweet content using fxtwitter API (handles tweets, threads, and X articles).

        Falls back to oembed if fxtwitter is unavailable.
        If the tweet is mostly links, resolves t.co URLs and fetches linked pages.
        """
        m = _TWEET_RE.match(url)
        if not m:
            return None
        author = m.group(1)
        tweet_id = m.group(2)

        # Try fxtwitter API first — it returns full article content for X articles
        fx_data = await self._fetch_via_fxtwitter(author, tweet_id)
        if fx_data:
            return fx_data

        # Fallback to oembed
        oembed_url = f"https://publish.twitter.com/oembed?url={url}&omit_script=true"
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(oembed_url)
                resp.raise_for_status()
                data = resp.json()
            html_block = data.get("html", "")
            raw_text = _re.sub(r"<[^>]+>", " ", html_block)
            raw_text = _re.sub(r"\s+", " ", raw_text).strip()
            author_name = data.get("author_name", author)

            # Check if tweet is mostly a link
            content_only = self._TCO_RE.sub("", raw_text).strip()
            content_only = _re.sub(r"—\s*.+$", "", content_only).strip()

            resolved = []
            linked_texts = []
            linked_title = None
            if len(content_only) < 80:
                resolved = await self._resolve_tco_links(html_block)
                for link in resolved:
                    try:
                        page_html = await self._fetch(link["url"])
                        page_data = self._extract(page_html, link["url"])
                        if page_data["text"].strip() and len(page_data["text"]) > 100:
                            linked_texts.append(
                                f"Linked article from {link['url']}:\n\n"
                                f"Title: {page_data['title']}\n\n"
                                f"{page_data['text']}"
                            )
                            if not linked_title and page_data["title"] != urlparse(link["url"]).netloc:
                                linked_title = page_data["title"]
                    except Exception:
                        pass

            parts = [f"Tweet by @{author_name}:\n\n{raw_text}"]
            if linked_texts:
                parts.extend(linked_texts)
            text = "\n\n---\n\n".join(parts)
            title = linked_title or f"Tweet by @{author_name}"

            return {
                "text": text,
                "source": url,
                "title": title,
                "metadata": {
                    "type": "tweet",
                    "domain": urlparse(url).netloc,
                    "author": author_name,
                    "linked_urls": [l["url"] for l in resolved],
                },
            }
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    async def _fetch_via_fxtwitter(self, author: str, tweet_id: str) -> dict[str, Any] | None:
        """Use fxtwitter API to get tweet + X article content (no auth required)."""
        api_url = f"https://api.fxtwitter.com/{author}/status/{tweet_id}"
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Lexicon/1.0)"},
            ) as client:
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()
            tweet = data.get("tweet", {})
            if not tweet:
                return None

            author_name = tweet.get("author", {}).get("name", author)
            tweet_text = tweet.get("text", "").strip()
            source_url = f"https://x.com/{author}/status/{tweet_id}"

            # Check for X article (long-form content)
            article = tweet.get("article")
            if article:
                article_title = article.get("title", "")
                # Extract plain text from article content blocks
                blocks = article.get("content", {}).get("blocks", [])
                article_parts = []
                for block in blocks:
                    block_text = block.get("text", "").strip()
                    if not block_text or block_text == " ":
                        continue
                    btype = block.get("type", "unstyled")
                    if btype.startswith("header-"):
                        level = btype.replace("header-", "")
                        prefix = {"one": "# ", "two": "## ", "three": "### "}.get(level, "## ")
                        article_parts.append(f"{prefix}{block_text}")
                    elif btype in ("unordered-list-item",):
                        article_parts.append(f"- {block_text}")
                    elif btype in ("ordered-list-item",):
                        article_parts.append(f"• {block_text}")
                    else:
                        article_parts.append(block_text)
                article_body = "\n\n".join(article_parts)

                title = article_title or f"X Article by @{author_name}"
                text = f"X Article by @{author_name}: {article_title}\n\n{article_body}"
                if tweet_text:
                    text = f"Tweet by @{author_name}: {tweet_text}\n\n---\n\n{text}"

                return {
                    "text": text,
                    "source": source_url,
                    "title": title,
                    "metadata": {
                        "type": "x_article",
                        "domain": "x.com",
                        "author": author_name,
                        "article_id": article.get("id", ""),
                    },
                }

            # Regular tweet (no article)
            if tweet_text:
                return {
                    "text": f"Tweet by @{author_name}:\n\n{tweet_text}",
                    "source": source_url,
                    "title": f"Tweet by @{author_name}",
                    "metadata": {
                        "type": "tweet",
                        "domain": "x.com",
                        "author": author_name,
                    },
                }
            return None
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    # Domains that are JS-rendered and useless to scrape raw HTML from
    _JS_ONLY_DOMAINS = {"twitter.com", "x.com", "www.twitter.com", "www.x.com"}

    async def fetch_and_ingest(self, url: str) -> dict[str, Any]:
        """Fetch a URL, extract readable text, send to Ultramemory, and return metadata."""
        # Special handling for tweets (JS-rendered, need oembed/fxtwitter)
        tweet_data = await self._fetch_tweet(url)
        if tweet_data:
            extracted = tweet_data
        elif urlparse(url).netloc.replace("www.", "") in ("twitter.com", "x.com"):
            # Tweet extraction failed — don't fall back to scraping JS shell
            return {
                "text": "",
                "source": url,
                "title": "Tweet (extraction failed)",
                "metadata": {"type": "tweet", "error": "Could not extract tweet content via fxtwitter or oembed"},
                "ultramemory": {"memories_created": 0, "session_key": ""},
            }
        else:
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
            headers={"User-Agent": _USER_AGENT},
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
            headers={"User-Agent": _USER_AGENT},
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
