"""Async HTTP client for the Ultramemory API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from ultraknowledge.config import Settings, get_settings


class UltramemoryClient:
    """Thin async wrapper around the Ultramemory REST API (localhost:8100)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.ultramemory_url.rstrip("/")

    def _make_session_key(self, source_type: str) -> str:
        return f"uk-{source_type}-{int(time.time())}"

    async def ingest(
        self,
        text: str,
        session_key: str | None = None,
        agent_id: str = "ultraknowledge",
        document_date: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/ingest — extract memories via LLM, embed, and store."""
        payload: dict[str, Any] = {
            "text": text,
            "session_key": session_key or self._make_session_key("ingest"),
            "agent_id": agent_id,
        }
        if document_date:
            payload["document_date"] = document_date

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/ingest", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def ingest_raw(
        self,
        text: str,
        session_key: str | None = None,
        agent_id: str = "ultraknowledge",
        document_date: str | None = None,
        chunk_size: int = 512,
    ) -> dict[str, Any]:
        """POST /api/ingest_raw — chunk and embed without LLM extraction."""
        payload: dict[str, Any] = {
            "text": text,
            "session_key": session_key or self._make_session_key("raw"),
            "agent_id": agent_id,
            "chunk_size": chunk_size,
        }
        if document_date:
            payload["document_date"] = document_date

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.base_url}/api/ingest_raw", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def search(
        self,
        query: str,
        top_k: int = 20,
        include_source: bool = False,
    ) -> list[dict[str, Any]]:
        """POST /api/search — semantic search, returns list of memory dicts."""
        payload = {
            "query": query,
            "top_k": top_k,
            "include_source": include_source,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/api/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])

    async def stats(self) -> dict[str, Any]:
        """GET /api/stats — memory counts and metadata."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/api/stats")
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> dict[str, Any]:
        """GET /api/health — health check."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.base_url}/api/health")
            resp.raise_for_status()
            return resp.json()

    async def entities(self, min_mentions: int = 1) -> list[dict[str, Any]]:
        """GET /api/entities — list entities with mention counts."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/entities",
                params={"min_mentions": min_mentions},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("entities", [])
