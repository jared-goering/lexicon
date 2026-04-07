"""Tests for the Field Theory bookmarks connector."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexicon.config import Settings
from lexicon.connectors.bookmarks import Bookmark, BookmarksConnector, BookmarksState


@pytest.fixture
def tmp_ft_db(tmp_path: Path) -> Path:
    """Create a mock Field Theory bookmarks database."""
    db_path = tmp_path / "bookmarks.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE bookmarks (
        id TEXT PRIMARY KEY,
        tweet_id TEXT NOT NULL,
        url TEXT NOT NULL,
        text TEXT NOT NULL,
        author_handle TEXT,
        author_name TEXT,
        author_profile_image_url TEXT,
        posted_at TEXT,
        bookmarked_at TEXT,
        synced_at TEXT NOT NULL,
        conversation_id TEXT,
        in_reply_to_status_id TEXT,
        quoted_status_id TEXT,
        language TEXT,
        like_count INTEGER,
        repost_count INTEGER,
        reply_count INTEGER,
        quote_count INTEGER,
        bookmark_count INTEGER,
        view_count INTEGER,
        media_count INTEGER DEFAULT 0,
        link_count INTEGER DEFAULT 0,
        links_json TEXT,
        tags_json TEXT,
        ingested_via TEXT,
        categories TEXT,
        primary_category TEXT,
        github_urls TEXT,
        domains TEXT,
        primary_domain TEXT
    )""")
    conn.execute(
        """INSERT INTO bookmarks
        (id, tweet_id, url, text, author_handle, author_name, posted_at,
         bookmarked_at, synced_at, like_count, repost_count, reply_count,
         quote_count, view_count, categories, primary_category, domains,
         primary_domain, links_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "bm_1",
            "111",
            "https://x.com/alice/status/111",
            "Great thread on distributed systems",
            "alice",
            "Alice Smith",
            "2026-04-01T10:00:00Z",
            "2026-04-01T12:00:00Z",
            "2026-04-06T00:00:00Z",
            150,
            30,
            5,
            10,
            50000,
            "research,technique",
            "research",
            "engineering",
            "engineering",
            '["https://example.com/paper"]',
        ),
    )
    conn.execute(
        """INSERT INTO bookmarks
        (id, tweet_id, url, text, author_handle, author_name, posted_at,
         bookmarked_at, synced_at, like_count, repost_count, reply_count,
         quote_count, view_count, categories, primary_category, domains,
         primary_domain, links_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "bm_2",
            "222",
            "https://x.com/bob/status/222",
            "Just shipped our new CLI tool",
            "bob",
            "Bob Jones",
            "2026-04-02T15:00:00Z",
            "2026-04-02T16:00:00Z",
            "2026-04-06T00:00:00Z",
            500,
            100,
            20,
            50,
            200000,
            "launch,tool",
            "launch",
            "devtools",
            "devtools",
            None,
        ),
    )
    conn.execute(
        """INSERT INTO bookmarks
        (id, tweet_id, url, text, author_handle, author_name, posted_at,
         bookmarked_at, synced_at, like_count, repost_count, reply_count,
         quote_count, view_count, categories, primary_category, domains,
         primary_domain, links_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "bm_3",
            "333",
            "https://x.com/carol/status/333",
            "New paper on attention mechanisms in transformers",
            "carol",
            "Carol Lee",
            "2026-04-03T09:00:00Z",
            "2026-04-03T10:00:00Z",
            "2026-04-06T00:00:00Z",
            80,
            20,
            3,
            5,
            30000,
            "research",
            "research",
            "ml",
            "ml",
            None,
        ),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def connector(tmp_path: Path, tmp_ft_db: Path) -> BookmarksConnector:
    """Create a BookmarksConnector pointing at the mock database."""
    settings = Settings(kb_dir=tmp_path / "kb")
    settings.ensure_dirs()
    c = BookmarksConnector(settings)
    c._db_path = tmp_ft_db
    return c


class TestBookmarksState:
    def test_save_and_load(self, tmp_path: Path):
        state = BookmarksState(
            seen_ids={"111", "222"}, last_sync="2026-04-06T00:00:00Z", total_ingested=2
        )
        path = tmp_path / "state.json"
        state.save(path)

        loaded = BookmarksState.load(path)
        assert loaded.seen_ids == {"111", "222"}
        assert loaded.last_sync == "2026-04-06T00:00:00Z"
        assert loaded.total_ingested == 2

    def test_load_missing_file(self, tmp_path: Path):
        state = BookmarksState.load(tmp_path / "nonexistent.json")
        assert state.seen_ids == set()
        assert state.last_sync == ""
        assert state.total_ingested == 0


class TestBookmarksConnector:
    def test_get_total_count(self, connector: BookmarksConnector):
        assert connector.get_total_count() == 3

    def test_get_new_bookmarks_all(self, connector: BookmarksConnector):
        bookmarks = connector.get_new_bookmarks()
        assert len(bookmarks) == 3
        assert all(isinstance(b, Bookmark) for b in bookmarks)

    def test_get_new_bookmarks_dedup(self, connector: BookmarksConnector):
        # Mark one as already seen
        connector.state.seen_ids.add("111")
        bookmarks = connector.get_new_bookmarks()
        assert len(bookmarks) == 2
        tweet_ids = {b.tweet_id for b in bookmarks}
        assert "111" not in tweet_ids
        assert "222" in tweet_ids
        assert "333" in tweet_ids

    def test_get_new_bookmarks_category_filter(self, connector: BookmarksConnector):
        bookmarks = connector.get_new_bookmarks(categories=["research"])
        assert len(bookmarks) == 2
        tweet_ids = {b.tweet_id for b in bookmarks}
        assert "111" in tweet_ids  # research,technique
        assert "333" in tweet_ids  # research

    def test_get_new_bookmarks_category_filter_launch(self, connector: BookmarksConnector):
        bookmarks = connector.get_new_bookmarks(categories=["launch"])
        assert len(bookmarks) == 1
        assert bookmarks[0].tweet_id == "222"

    def test_bookmark_metadata(self, connector: BookmarksConnector):
        bookmarks = connector.get_new_bookmarks()
        alice = next(b for b in bookmarks if b.tweet_id == "111")
        assert alice.author_handle == "alice"
        assert alice.author_name == "Alice Smith"
        assert alice.like_count == 150
        assert alice.view_count == 50000
        assert alice.primary_category == "research"

    def test_ingest_new_bookmarks_updates_state(self, connector: BookmarksConnector):
        chunks = connector.ingest_new_bookmarks()
        assert len(chunks) == 3
        assert connector.state.total_ingested == 3
        assert len(connector.state.seen_ids) == 3

        # Second call should return nothing
        chunks2 = connector.ingest_new_bookmarks()
        assert len(chunks2) == 0

    def test_ingest_chunk_format(self, connector: BookmarksConnector):
        chunks = connector.ingest_new_bookmarks()
        chunk = next(c for c in chunks if "distributed systems" in c["text"])
        assert chunk["source"] == "https://x.com/alice/status/111"
        assert "Alice Smith" in chunk["text"]
        assert chunk["metadata"]["type"] == "bookmark"
        assert chunk["metadata"]["author_handle"] == "alice"
        assert chunk["metadata"]["like_count"] == 150

    def test_ingest_with_category_filter(self, connector: BookmarksConnector):
        chunks = connector.ingest_new_bookmarks(categories=["launch"])
        assert len(chunks) == 1
        assert "shipped" in chunks[0]["text"]

    def test_get_status(self, connector: BookmarksConnector):
        status = connector.get_status()
        assert status["total_in_db"] == 3
        assert status["pending"] == 3
        assert status["total_ingested"] == 0
        assert status["db_exists"] is True

    def test_get_status_after_ingest(self, connector: BookmarksConnector):
        connector.ingest_new_bookmarks()
        status = connector.get_status()
        assert status["total_ingested"] == 3
        assert status["pending"] == 0

    def test_missing_db(self, tmp_path: Path):
        settings = Settings(kb_dir=tmp_path / "kb")
        settings.ensure_dirs()
        c = BookmarksConnector(settings)
        c._db_path = tmp_path / "nonexistent.db"
        assert c.get_total_count() == 0
        status = c.get_status()
        assert status["db_exists"] is False

    def test_links_in_chunk(self, connector: BookmarksConnector):
        chunks = connector.ingest_new_bookmarks()
        alice_chunk = next(c for c in chunks if "distributed systems" in c["text"])
        assert "https://example.com/paper" in alice_chunk["text"]


@pytest.mark.asyncio
class TestAsyncIngestion:
    async def test_async_ingest(self, connector: BookmarksConnector):
        mock_client = MagicMock()
        mock_client._make_session_key = MagicMock(return_value="test-session")
        mock_client.ingest = AsyncMock(return_value={"memories_created": 2})

        mock_compiler = MagicMock()
        mock_compiler.compile_topic = AsyncMock(return_value=Path("/tmp/test.md"))

        mock_linker = MagicMock()
        mock_linker.generate_backlinks = MagicMock()
        mock_linker.rebuild_index = MagicMock()

        result = await connector.async_ingest_new_bookmarks(mock_client, mock_compiler, mock_linker)

        assert result["ingested"] == 3
        assert result["memories_created"] == 6  # 2 per bookmark * 3
        assert len(result["articles"]) == 3
        assert mock_client.ingest.call_count == 3
        assert mock_compiler.compile_topic.call_count == 3
        mock_linker.generate_backlinks.assert_called_once()
        mock_linker.rebuild_index.assert_called_once()
