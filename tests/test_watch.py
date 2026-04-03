"""Tests for watch mode orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexicon.config import Settings
from lexicon.linter import KBLinter, LintReport
from lexicon.research import ResearchAgent, ResearchRun
from lexicon.watch import WatchAgent


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = settings.kb_dir / "articles"
    settings.index_path = settings.kb_dir / "Index.md"
    settings.ensure_dirs()
    return settings


def test_watch_agent_persists_list_and_stop(tmp_settings: Settings, tmp_path: Path):
    agent = WatchAgent(
        tmp_settings,
        research_agent=MagicMock(spec=ResearchAgent),
        linter=MagicMock(spec=KBLinter),
        watches_path=tmp_path / "watches.json",
    )

    agent.upsert_watch("llm agents", interval_minutes=60)
    agent.upsert_watch("llm agents", interval_minutes=30)
    agent.upsert_watch("vector dbs", interval_minutes=15)

    watches = agent.list_watches()
    assert len(watches) == 2
    assert watches[0].topic == "llm agents"
    assert watches[0].interval_minutes == 30

    assert agent.stop_watch("llm agents")
    assert not agent.stop_watch("missing topic")
    remaining = agent.list_watches()
    assert [watch.topic for watch in remaining] == ["vector dbs"]


def test_run_watch_cycle_runs_research_lint_and_updates_last_run(tmp_settings: Settings, tmp_path: Path):
    research_agent = MagicMock(spec=ResearchAgent)
    research_agent.research = AsyncMock(
        return_value=ResearchRun(topic="llm", num_results=10, compiled=True)
    )
    linter = MagicMock(spec=KBLinter)
    linter.lint = AsyncMock(return_value=LintReport())

    agent = WatchAgent(
        tmp_settings,
        research_agent=research_agent,
        linter=linter,
        watches_path=tmp_path / "watches.json",
    )
    agent.upsert_watch("llm", interval_minutes=60)

    research_run, lint_report = asyncio.run(agent.run_watch_cycle("llm"))

    assert research_run.topic == "llm"
    assert isinstance(lint_report, LintReport)
    research_agent.research.assert_awaited_once_with("llm", num_results=10, compile=True)
    linter.lint.assert_awaited_once_with(stale_days=7)
    assert agent.list_watches()[0].last_run_at is not None


def test_watch_loop_runs_until_watch_is_removed(tmp_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agent = WatchAgent(
        tmp_settings,
        research_agent=MagicMock(spec=ResearchAgent),
        linter=MagicMock(spec=KBLinter),
        watches_path=tmp_path / "watches.json",
    )

    async def fake_run_watch_cycle(topic: str, num_results: int = 10):
        agent.stop_watch(topic)
        return ResearchRun(topic=topic, num_results=num_results, compiled=True), LintReport()

    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(agent, "run_watch_cycle", fake_run_watch_cycle)
    monkeypatch.setattr("lexicon.watch.asyncio.sleep", sleep_mock)

    asyncio.run(agent.watch("llm", interval_minutes=1))

    assert sleep_mock.await_count == 1
    assert agent.list_watches() == []
