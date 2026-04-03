"""RSS feed connector — monitors feeds and ingests new entries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser

from lexicon.config import Settings, get_settings


@dataclass
class FeedEntry:
    """A single RSS/Atom feed entry."""

    title: str
    url: str
    summary: str
    published: str | None = None
    feed_title: str = ""


@dataclass
class FeedState:
    """Persistent state for tracked feeds."""

    feeds: dict[str, FeedInfo] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        data = {
            url: {
                "title": info.title,
                "last_checked": info.last_checked,
                "seen_ids": list(info.seen_ids),
            }
            for url, info in self.feeds.items()
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> FeedState:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        state = cls()
        for url, info in data.items():
            state.feeds[url] = FeedInfo(
                title=info["title"],
                last_checked=info["last_checked"],
                seen_ids=set(info.get("seen_ids", [])),
            )
        return state


@dataclass
class FeedInfo:
    """Tracking info for a single feed."""

    title: str = ""
    last_checked: str = ""
    seen_ids: set[str] = field(default_factory=set)


class RSSConnector:
    """Monitor RSS/Atom feeds and ingest new entries into the knowledge base."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._state_path = self.settings.kb_dir / ".feed_state.json"
        self.state = FeedState.load(self._state_path)

    def add_feed(self, url: str) -> FeedInfo:
        """Register a new RSS/Atom feed to monitor."""
        feed = feedparser.parse(url)
        title = feed.feed.get("title", url)
        info = FeedInfo(title=title)
        self.state.feeds[url] = info
        self._save()
        return info

    def remove_feed(self, url: str) -> bool:
        """Remove a feed from monitoring."""
        if url in self.state.feeds:
            del self.state.feeds[url]
            self._save()
            return True
        return False

    def list_feeds(self) -> dict[str, FeedInfo]:
        """List all monitored feeds."""
        return self.state.feeds

    def check_feeds(self) -> list[FeedEntry]:
        """Check all registered feeds for new entries.

        Returns entries not previously seen. Updates seen_ids state.
        """
        all_new: list[FeedEntry] = []

        for url, info in self.state.feeds.items():
            new_entries = self._check_single_feed(url, info)
            all_new.extend(new_entries)

        self._save()
        return all_new

    def ingest_new_entries(self) -> list[dict[str, Any]]:
        """Check feeds and return chunks ready for Ultramemory ingestion."""
        entries = self.check_feeds()
        return [
            {
                "text": f"# {entry.title}\n\n{entry.summary}",
                "source": entry.url,
                "title": entry.title,
                "metadata": {
                    "type": "rss",
                    "feed": entry.feed_title,
                    "published": entry.published,
                },
            }
            for entry in entries
        ]

    def _check_single_feed(self, url: str, info: FeedInfo) -> list[FeedEntry]:
        """Parse a single feed and return new entries."""
        feed = feedparser.parse(url)
        new_entries: list[FeedEntry] = []

        for entry in feed.entries:
            entry_id = entry.get("id") or entry.get("link", "")
            if entry_id in info.seen_ids:
                continue

            info.seen_ids.add(entry_id)
            new_entries.append(
                FeedEntry(
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", url),
                    summary=entry.get("summary", entry.get("description", "")),
                    published=entry.get("published"),
                    feed_title=info.title,
                )
            )

        info.last_checked = datetime.now(timezone.utc).isoformat()
        return new_entries

    def _save(self) -> None:
        self.settings.ensure_dirs()
        self.state.save(self._state_path)
