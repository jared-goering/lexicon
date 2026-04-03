"""Client for Ultramemory — uses embedded engine by default (own DB), or HTTP if configured."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from lexicon.config import Settings, get_settings


class UltramemoryClient:
    """Wraps Ultramemory.  Embedded mode (default) uses MemoryEngine directly
    with lexicon's own database.  Remote mode talks to an HTTP server.

    Embedded is preferred — no separate server needed, fully isolated DB.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._remote_url = self.settings.ultramemory_url.rstrip("/") if self.settings.ultramemory_url else ""
        self._engine = None  # lazy-init for embedded mode

    @property
    def is_remote(self) -> bool:
        return bool(self._remote_url)

    def _get_engine(self):
        """Lazy-init the embedded MemoryEngine with lexicon's own DB."""
        if self._engine is None:
            from ultramemory.engine import MemoryEngine

            db_path = str(self.settings.ultramemory_db_path)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            model = os.getenv("UK_LLM_MODEL", None)
            self._engine = MemoryEngine(db_path=db_path, model_name=model)
        return self._engine

    def _make_session_key(self, source_type: str) -> str:
        return f"uk-{source_type}-{int(time.time())}"

    @staticmethod
    def _normalize_ingest_result(result: dict[str, Any]) -> dict[str, Any]:
        """Normalize ingest responses across embedded and remote modes."""
        memories = result.get("memories", [])
        count = result.get("count")
        if count is None:
            count = result.get("memories_created")
        if count is None:
            count = len(memories)

        normalized = dict(result)
        normalized["count"] = count
        normalized["memories_created"] = count
        return normalized

    # ── Ingest ───────────────────────────────────────────────────────────

    async def ingest(
        self,
        text: str,
        session_key: str | None = None,
        agent_id: str = "lexicon",
        document_date: str | None = None,
    ) -> dict[str, Any]:
        """Ingest text — extract memories via LLM, embed, store."""
        sk = session_key or self._make_session_key("ingest")

        if self.is_remote:
            import httpx

            payload: dict[str, Any] = {"text": text, "session_key": sk, "agent_id": agent_id}
            if document_date:
                payload["document_date"] = document_date
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self._remote_url}/api/ingest", json=payload)
                resp.raise_for_status()
                return self._normalize_ingest_result(resp.json())

        engine = self._get_engine()
        memories = await asyncio.to_thread(
            engine.ingest,
            text=text,
            session_key=sk,
            agent_id=agent_id,
            document_date=document_date,
        )
        return self._normalize_ingest_result({"memories": memories})

    async def ingest_raw(
        self,
        text: str,
        session_key: str | None = None,
        agent_id: str = "lexicon",
        document_date: str | None = None,
        chunk_size: int = 512,
    ) -> dict[str, Any]:
        """Store text without LLM extraction (chunk + embed only)."""
        sk = session_key or self._make_session_key("raw")

        if self.is_remote:
            import httpx

            payload: dict[str, Any] = {"text": text, "session_key": sk, "agent_id": agent_id, "chunk_size": chunk_size}
            if document_date:
                payload["document_date"] = document_date
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{self._remote_url}/api/ingest_raw", json=payload)
                resp.raise_for_status()
                return self._normalize_ingest_result(resp.json())

        # Embedded: use ingest (no raw-only mode in engine, ingest does extraction)
        engine = self._get_engine()
        memories = await asyncio.to_thread(
            engine.ingest,
            text=text,
            session_key=sk,
            agent_id=agent_id,
            document_date=document_date,
        )
        return self._normalize_ingest_result({"memories": memories})

    # ── Media ingest ─────────────────────────────────────────────────────

    async def ingest_media(
        self,
        file_path: str,
        session_key: str | None = None,
        agent_id: str = "lexicon",
    ) -> dict[str, Any]:
        """Ingest a media file (image/audio/video) via the engine's multimodal pipeline."""
        sk = session_key or self._make_session_key("media")

        if self.is_remote:
            import httpx

            async with httpx.AsyncClient(timeout=180.0) as client:
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        f"{self._remote_url}/api/ingest_media",
                        files={"file": f},
                        data={"session_key": sk, "agent_id": agent_id},
                    )
                resp.raise_for_status()
                return resp.json()

        engine = self._get_engine()
        result = await asyncio.to_thread(
            engine.ingest_media,
            file_path=file_path,
            session_key=sk,
            agent_id=agent_id,
        )
        return result

    # ── Search ───────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 20,
        include_source: bool = False,
    ) -> list[dict[str, Any]]:
        """Semantic search, returns list of memory dicts."""
        if self.is_remote:
            import httpx

            payload = {"query": query, "top_k": top_k, "include_source": include_source}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self._remote_url}/api/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", [])

        engine = self._get_engine()
        return await asyncio.to_thread(engine.search, query=query, top_k=top_k)

    # ── Stats / Health / Entities ────────────────────────────────────────

    async def stats(self) -> dict[str, Any]:
        """Memory counts and metadata."""
        if self.is_remote:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._remote_url}/api/stats")
                resp.raise_for_status()
                return resp.json()

        engine = self._get_engine()
        return await asyncio.to_thread(engine.get_stats)

    async def health(self) -> dict[str, Any]:
        """Health check."""
        if self.is_remote:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._remote_url}/api/health")
                resp.raise_for_status()
                return resp.json()

        engine = self._get_engine()
        stats = await asyncio.to_thread(engine.get_stats)
        return {"status": "ok", "mode": "embedded", "total_memories": stats.get("total_memories", 0)}

    async def entities(self, min_mentions: int = 1) -> list[dict[str, Any]]:
        """List entities with mention counts."""
        if self.is_remote:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._remote_url}/api/entities",
                    params={"min_mentions": min_mentions},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("entities", [])

        engine = self._get_engine()
        return await asyncio.to_thread(engine.list_entities, min_mentions=min_mentions)
