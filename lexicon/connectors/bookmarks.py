"""Field Theory bookmarks connector — syncs X/Twitter bookmarks into the knowledge base."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lexicon.config import Settings, get_settings


@dataclass
class Bookmark:
    """A single X/Twitter bookmark from the Field Theory database."""

    tweet_id: str
    url: str
    text: str
    author_handle: str | None = None
    author_name: str | None = None
    posted_at: str | None = None
    bookmarked_at: str | None = None
    like_count: int = 0
    repost_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    categories: str | None = None
    primary_category: str | None = None
    domains: str | None = None
    primary_domain: str | None = None
    links_json: str | None = None


@dataclass
class BookmarksState:
    """Persistent state tracking which bookmarks have been ingested."""

    seen_ids: set[str] = field(default_factory=set)
    last_sync: str = ""
    total_ingested: int = 0

    def save(self, path: Path) -> None:
        data = {
            "seen_ids": sorted(self.seen_ids),
            "last_sync": self.last_sync,
            "total_ingested": self.total_ingested,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> BookmarksState:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            seen_ids=set(data.get("seen_ids", [])),
            last_sync=data.get("last_sync", ""),
            total_ingested=data.get("total_ingested", 0),
        )


def _ft_db_path() -> Path:
    """Return the path to the Field Theory bookmarks database."""
    data_dir = os.getenv("FT_DATA_DIR", os.path.expanduser("~/.ft-bookmarks"))
    return Path(data_dir) / "bookmarks.db"


class BookmarksConnector:
    """Sync X/Twitter bookmarks from Field Theory CLI into the knowledge base."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._state_path = self.settings.kb_dir / ".bookmarks_state.json"
        self.state = BookmarksState.load(self._state_path)
        self._db_path = _ft_db_path()

    def _open_db(self) -> sqlite3.Connection:
        """Open the FT database in read-only mode."""
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Field Theory database not found at {self._db_path}. "
                "Install ft CLI and run 'ft sync' first."
            )
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_total_count(self) -> int:
        """Return total number of bookmarks in the FT database."""
        try:
            conn = self._open_db()
        except FileNotFoundError:
            return 0
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM bookmarks").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_new_bookmarks(self, categories: list[str] | None = None) -> list[Bookmark]:
        """Return bookmarks not yet ingested, optionally filtered by category."""
        conn = self._open_db()
        try:
            rows = conn.execute("SELECT * FROM bookmarks ORDER BY bookmarked_at DESC").fetchall()
        finally:
            conn.close()

        new_bookmarks: list[Bookmark] = []
        for row in rows:
            tweet_id = row["tweet_id"]
            if tweet_id in self.state.seen_ids:
                continue

            # Category filter
            if categories:
                row_cats = (row["categories"] or "").lower()
                if not any(c.lower() in row_cats for c in categories):
                    continue

            new_bookmarks.append(
                Bookmark(
                    tweet_id=tweet_id,
                    url=row["url"],
                    text=row["text"],
                    author_handle=row["author_handle"],
                    author_name=row["author_name"],
                    posted_at=row["posted_at"],
                    bookmarked_at=row["bookmarked_at"],
                    like_count=row["like_count"] or 0,
                    repost_count=row["repost_count"] or 0,
                    reply_count=row["reply_count"] or 0,
                    quote_count=row["quote_count"] or 0,
                    view_count=row["view_count"] or 0,
                    categories=row["categories"],
                    primary_category=row["primary_category"],
                    domains=row["domains"],
                    primary_domain=row["primary_domain"],
                    links_json=row["links_json"],
                )
            )

        return new_bookmarks

    def _bookmark_to_chunk(self, bm: Bookmark) -> dict[str, Any]:
        """Convert a single bookmark to an ingestion chunk."""
        author = bm.author_name or bm.author_handle or "Unknown"
        handle = f" (@{bm.author_handle})" if bm.author_handle else ""

        # Build rich text
        lines = [f"# {author}{handle}\n", bm.text]
        if bm.links_json:
            try:
                links = json.loads(bm.links_json)
                if links:
                    lines.append("\nLinks: " + ", ".join(links))
            except (json.JSONDecodeError, TypeError):
                pass

        engagement = []
        if bm.like_count:
            engagement.append(f"{bm.like_count} likes")
        if bm.repost_count:
            engagement.append(f"{bm.repost_count} reposts")
        if bm.view_count:
            engagement.append(f"{bm.view_count:,} views")
        if engagement:
            lines.append(f"\nEngagement: {', '.join(engagement)}")

        return {
            "text": "\n".join(lines),
            "source": bm.url,
            "title": f"{author}: {bm.text[:80]}",
            "metadata": {
                "type": "bookmark",
                "author_handle": bm.author_handle,
                "author_name": bm.author_name,
                "posted_at": bm.posted_at,
                "bookmarked_at": bm.bookmarked_at,
                "categories": bm.categories,
                "primary_category": bm.primary_category,
                "primary_domain": bm.primary_domain,
                "like_count": bm.like_count,
                "repost_count": bm.repost_count,
                "view_count": bm.view_count,
            },
        }

    def ingest_new_bookmarks(self, categories: list[str] | None = None) -> list[dict[str, Any]]:
        """Get new bookmarks and return chunks ready for Ultramemory ingestion."""
        bookmarks = self.get_new_bookmarks(categories=categories)
        chunks: list[dict[str, Any]] = []

        for bm in bookmarks:
            chunks.append(self._bookmark_to_chunk(bm))
            self.state.seen_ids.add(bm.tweet_id)

        self.state.last_sync = datetime.now(timezone.utc).isoformat()
        self.state.total_ingested += len(chunks)
        self._save()
        return chunks

    async def async_ingest_new_bookmarks(
        self,
        um_client: Any,
        compiler: Any,
        linker: Any,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Full ingestion flow: read new bookmarks, ingest to Ultramemory, compile, update state."""
        bookmarks = self.get_new_bookmarks(categories=categories)
        if not bookmarks:
            return {"ingested": 0, "memories_created": 0, "articles": []}

        total_memories = 0
        chunks: list[dict[str, Any]] = []

        for bm in bookmarks:
            chunk = self._bookmark_to_chunk(bm)
            chunks.append(chunk)

            session_key = um_client._make_session_key("bookmark")
            result = await um_client.ingest(
                text=chunk["text"],
                session_key=session_key,
                agent_id="uk-bookmarks",
            )
            total_memories += result.get("memories_created", 0)
            self.state.seen_ids.add(bm.tweet_id)

        # Compile articles from ingested bookmarks
        article_paths: list[str] = []
        for chunk in chunks:
            try:
                path = await compiler.compile_topic(chunk["title"], [chunk])
                article_paths.append(str(path))
            except Exception:
                pass  # Compilation is best-effort

        if article_paths:
            linker.generate_backlinks()
            linker.rebuild_index()

        self.state.last_sync = datetime.now(timezone.utc).isoformat()
        self.state.total_ingested += len(bookmarks)
        self._save()

        return {
            "ingested": len(bookmarks),
            "memories_created": total_memories,
            "articles": article_paths,
        }

    def sync(self) -> int:
        """Run 'ft sync' subprocess first, then return count of new bookmarks."""
        self.run_ft_sync()
        new = self.get_new_bookmarks()
        return len(new)

    def run_ft_sync(self) -> str:
        """Run 'ft sync' subprocess to pull latest bookmarks from X/Twitter."""
        result = subprocess.run(
            ["ft", "sync"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ft sync failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def get_status(self) -> dict[str, Any]:
        """Return current sync status for the API."""
        pending = 0
        try:
            pending = len(self.get_new_bookmarks())
        except FileNotFoundError:
            pass

        total_in_db = self.get_total_count()

        return {
            "last_sync": self.state.last_sync or None,
            "total_ingested": self.state.total_ingested,
            "total_in_db": total_in_db,
            "pending": pending,
            "db_path": str(self._db_path),
            "db_exists": self._db_path.exists(),
        }

    def _save(self) -> None:
        self.settings.ensure_dirs()
        self.state.save(self._state_path)
