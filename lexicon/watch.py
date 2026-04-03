"""Persistent topic watch mode for recurring research cycles."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lexicon.config import Settings, get_settings
from lexicon.linter import KBLinter, LintReport
from lexicon.research import ResearchAgent, ResearchRun


@dataclass
class WatchEntry:
    """Persisted watch configuration."""

    topic: str
    interval_minutes: int
    created_at: str
    last_run_at: str | None = None


class WatchAgent:
    """Manage and run recurring research watches."""

    def __init__(
        self,
        settings: Settings | None = None,
        research_agent: ResearchAgent | None = None,
        linter: KBLinter | None = None,
        watches_path: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.research_agent = research_agent or ResearchAgent(self.settings)
        self.linter = linter or KBLinter(self.settings)
        self.watches_path = watches_path or (Path.home() / ".lexicon" / "watches.json")

    def list_watches(self) -> list[WatchEntry]:
        data = self._read_watches()
        return [WatchEntry(**item) for item in data.get("watches", [])]

    def upsert_watch(self, topic: str, interval_minutes: int) -> WatchEntry:
        watches = self.list_watches()
        now = datetime.now(timezone.utc).isoformat()
        updated = False
        for watch in watches:
            if watch.topic == topic:
                watch.interval_minutes = interval_minutes
                updated = True
                entry = watch
                break
        else:
            entry = WatchEntry(topic=topic, interval_minutes=interval_minutes, created_at=now)
            watches.append(entry)

        self._write_watches(watches)
        if not updated:
            return entry
        return entry

    def stop_watch(self, topic: str) -> bool:
        watches = self.list_watches()
        remaining = [watch for watch in watches if watch.topic != topic]
        if len(remaining) == len(watches):
            return False
        self._write_watches(remaining)
        return True

    async def run_watch_cycle(
        self,
        topic: str,
        num_results: int = 10,
    ) -> tuple[ResearchRun, LintReport]:
        """Run one research + lint cycle for a watched topic."""
        research_run = await self.research_agent.research(
            topic,
            num_results=num_results,
            compile=True,
        )
        lint_report = await self.linter.lint(stale_days=7)
        self._mark_last_run(topic)
        return research_run, lint_report

    async def watch(self, topic: str, interval_minutes: int = 60, num_results: int = 10) -> None:
        self.upsert_watch(topic, interval_minutes)
        while self._is_active(topic):
            await self.run_watch_cycle(topic, num_results=num_results)
            await asyncio.sleep(interval_minutes * 60)

    def _is_active(self, topic: str) -> bool:
        return any(watch.topic == topic for watch in self.list_watches())

    def _mark_last_run(self, topic: str) -> None:
        watches = self.list_watches()
        now = datetime.now(timezone.utc).isoformat()
        for watch in watches:
            if watch.topic == topic:
                watch.last_run_at = now
                break
        self._write_watches(watches)

    def _read_watches(self) -> dict[str, list[dict[str, str | int | None]]]:
        if not self.watches_path.exists():
            return {"watches": []}
        return json.loads(self.watches_path.read_text(encoding="utf-8"))

    def _write_watches(self, watches: list[WatchEntry]) -> None:
        self.watches_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "watches": [
                {
                    "topic": watch.topic,
                    "interval_minutes": watch.interval_minutes,
                    "created_at": watch.created_at,
                    "last_run_at": watch.last_run_at,
                }
                for watch in watches
            ]
        }
        self.watches_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
