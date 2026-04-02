"""Tests for the Ultramemory HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ultraknowledge.config import Settings
from ultraknowledge.ultramemory_client import UltramemoryClient


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    s.ultramemory_url = "http://localhost:8100"
    return s


@pytest.fixture
def client(settings: Settings) -> UltramemoryClient:
    return UltramemoryClient(settings)


class TestSessionKey:
    def test_format(self, client: UltramemoryClient):
        key = client._make_session_key("url")
        assert key.startswith("uk-url-")
        # Timestamp part should be numeric
        ts = key.split("-", 2)[2]
        assert ts.isdigit()


class TestIngest:
    @pytest.mark.asyncio
    async def test_ingest_sends_correct_payload(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={"memories": [{"id": "m1", "content": "test"}], "count": 1},
            request=httpx.Request("POST", "http://localhost:8100/api/ingest"),
        )

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            result = await client.ingest(
                "Hello world", session_key="test-session", agent_id="test"
            )

        assert result["count"] == 1
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "http://localhost:8100/api/ingest"
        payload = call_kwargs[1]["json"]
        assert payload["text"] == "Hello world"
        assert payload["session_key"] == "test-session"
        assert payload["agent_id"] == "test"


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={
                "results": [
                    {"id": "m1", "content": "result 1", "similarity": 0.9, "category": "fact"},
                ],
                "count": 1,
            },
            request=httpx.Request("POST", "http://localhost:8100/api/search"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            results = await client.search("test query", top_k=5)

        assert len(results) == 1
        assert results[0]["content"] == "result 1"
        assert results[0]["similarity"] == 0.9

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={"results": [], "count": 0},
            request=httpx.Request("POST", "http://localhost:8100/api/search"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            results = await client.search("nonexistent")

        assert results == []


class TestStats:
    @pytest.mark.asyncio
    async def test_stats(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={"total": 42, "current": 40, "superseded": 2},
            request=httpx.Request("GET", "http://localhost:8100/api/stats"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            stats = await client.stats()

        assert stats["total"] == 42


class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={"status": "ok", "memories": 100, "source_chunks": 50, "version": "0.2.1"},
            request=httpx.Request("GET", "http://localhost:8100/api/health"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            health = await client.health()

        assert health["status"] == "ok"


class TestEntities:
    @pytest.mark.asyncio
    async def test_entities(self, client: UltramemoryClient):
        mock_response = httpx.Response(
            200,
            json={"entities": [{"entity_name": "Python", "mention_count": 5}], "count": 1},
            request=httpx.Request("GET", "http://localhost:8100/api/entities"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            entities = await client.entities()

        assert len(entities) == 1
        assert entities[0]["entity_name"] == "Python"
