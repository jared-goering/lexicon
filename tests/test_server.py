"""Integration tests for the FastAPI server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_token(monkeypatch):
    """Ensure LEXICON_API_TOKEN is unset by default."""
    monkeypatch.delenv("LEXICON_API_TOKEN", raising=False)


@pytest.fixture()
def _mock_deps():
    """Mock heavy dependencies so we can test routing/validation without real backends."""
    with (
        patch("lexicon.server.um_client") as mock_um,
        patch("lexicon.server.compiler"),
        patch("lexicon.server.linker") as mock_linker,
        patch("lexicon.server.linter"),
        patch("lexicon.server.exporter"),
        patch("lexicon.server.research_agent"),
        patch("lexicon.server.qa"),
        patch("lexicon.server.url_connector"),
    ):
        mock_um.search = AsyncMock(return_value=[])
        mock_um.stats = AsyncMock(return_value={"total_memories": 0})
        mock_linker.scan_articles.return_value = {}
        yield


@pytest.fixture()
def client(_mock_deps, tmp_path, monkeypatch):
    """Create a TestClient with an isolated KB directory."""
    articles_dir = tmp_path / "kb" / "articles"
    articles_dir.mkdir(parents=True)

    # Patch settings so file-based endpoints use the temp dir
    from lexicon.server import app, settings

    original_kb = settings.kb_dir
    original_articles = settings.articles_dir
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = articles_dir

    yield TestClient(app, raise_server_exceptions=False)

    settings.kb_dir = original_kb
    settings.articles_dir = original_articles


# ── Read endpoints ──────────────────────────────────────────────────────


class TestReadEndpoints:
    def test_topics_returns_200(self, client):
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        assert "topics" in resp.json()

    def test_stats_returns_200(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "article_count" in data

    def test_processing_returns_200(self, client):
        resp = client.get("/api/processing")
        assert resp.status_code == 200
        assert "processing" in resp.json()

    def test_graph_returns_200(self, client):
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data


# ── Path traversal protection ───────────────────────────────────────────


class TestPathTraversal:
    def test_get_article_path_traversal(self, client):
        """Traversal attempt must not succeed — 400 or 404 are both safe."""
        resp = client.get("/api/articles/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    def test_get_article_dotdot_literal(self, client):
        """Literal '..' in slug must be rejected."""
        resp = client.get("/api/articles/..%2Fetc")
        assert resp.status_code in (400, 404)

    def test_snapshot_path_traversal(self, client):
        resp = client.get("/api/snapshot/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    def test_delete_article_path_traversal(self, client):
        resp = client.delete("/api/articles/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 401, 404)


# ── Validation ──────────────────────────────────────────────────────────


class TestValidation:
    def test_ingest_empty_body(self, client):
        resp = client.post("/api/ingest", json={})
        # Empty body with no url/text should return 400 (app-level)
        # FastAPI returns 400 for our explicit check
        assert resp.status_code == 400

    def test_ingest_missing_body(self, client):
        resp = client.post("/api/ingest")
        assert resp.status_code == 422


# ── Auth ────────────────────────────────────────────────────────────────


class TestAuth:
    @pytest.fixture()
    def authed_client(self, _mock_deps, tmp_path, monkeypatch):
        """Client with LEXICON_API_TOKEN set."""
        monkeypatch.setenv("LEXICON_API_TOKEN", "test-secret-token")

        # Re-import to pick up the token — settings is a cached singleton,
        # so we patch it directly.
        from lexicon.server import app, settings

        original_token = settings.api_token
        original_articles = settings.articles_dir
        original_kb = settings.kb_dir
        settings.api_token = "test-secret-token"
        articles_dir = tmp_path / "kb" / "articles"
        articles_dir.mkdir(parents=True)
        settings.kb_dir = tmp_path / "kb"
        settings.articles_dir = articles_dir

        yield TestClient(app, raise_server_exceptions=False)

        settings.api_token = original_token
        settings.articles_dir = original_articles
        settings.kb_dir = original_kb

    def test_write_endpoint_requires_token(self, authed_client):
        """Write endpoints without token should return 401."""
        resp = authed_client.post("/api/ingest", json={"url": "https://example.com"})
        assert resp.status_code == 401

    def test_write_endpoint_with_valid_token(self, authed_client):
        """Write endpoints with valid token should not return 401."""
        resp = authed_client.post(
            "/api/ingest",
            json={"text": "hello"},
            headers={"Authorization": "Bearer test-secret-token"},
        )
        # Should not be 401 — may be 400/422/500 depending on mocks, but auth passed
        assert resp.status_code != 401

    def test_read_endpoints_work_without_token(self, authed_client):
        """Read endpoints should work even when LEXICON_API_TOKEN is set."""
        for path in ["/api/topics", "/api/stats", "/api/processing", "/api/graph"]:
            resp = authed_client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
