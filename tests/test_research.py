"""Tests for research orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ultraknowledge.config import Settings
from ultraknowledge.connectors.web_search import SearchResult
from ultraknowledge.research import ResearchAgent, build_research_document, extract_research_metadata
from ultraknowledge.ultramemory_client import UltramemoryClient


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = settings.kb_dir / "articles"
    settings.index_path = settings.kb_dir / "Index.md"
    settings.ensure_dirs()
    return settings


def test_build_research_document_round_trip():
    result = SearchResult(
        title="Example Source",
        url="https://example.com/source",
        text="Important findings",
        score=0.9,
        published_date="2026-04-01",
    )

    document = build_research_document(result)
    metadata = extract_research_metadata(document)

    assert "Important findings" in document
    assert metadata["title"] == "Example Source"
    assert metadata["url"] == "https://example.com/source"
    assert metadata["published_date"] == "2026-04-01"


def test_research_agent_runs_search_ingest_compile_and_link(tmp_settings: Settings):
    client = MagicMock(spec=UltramemoryClient)
    client._make_session_key.return_value = "uk-research-123"
    client.ingest = AsyncMock(return_value={"memories_created": 2})

    connector = MagicMock()
    connector.research = AsyncMock(
        return_value=[
            SearchResult(
                title="Alpha",
                url="https://example.com/a",
                text="Alpha facts",
                score=0.8,
                published_date="2026-04-01",
            ),
            SearchResult(
                title="Beta",
                url="https://example.com/b",
                text="Beta facts",
                score=0.7,
                published_date="2026-03-31",
            ),
        ]
    )

    compiler = MagicMock()
    compiler.compile_topic = AsyncMock(return_value=tmp_settings.articles_dir / "topic.md")

    linker = MagicMock()
    linker.generate_backlinks.return_value.links_added = 3

    agent = ResearchAgent(
        tmp_settings,
        client=client,
        connector=connector,
        compiler=compiler,
        linker=linker,
    )

    run = asyncio.run(agent.research("test topic", num_results=2, compile=True))

    assert len(run.results) == 2
    assert run.memories_created == 4
    assert run.article_paths == [tmp_settings.articles_dir / "topic.md"]
    assert run.links_added == 3
    assert client.ingest.await_count == 2
    compiler.compile_topic.assert_awaited_once()
    linker.generate_backlinks.assert_called_once()
    linker.rebuild_index.assert_called_once()

    ingest_text = client.ingest.await_args_list[0].kwargs["text"]
    assert "Source Title: Alpha" in ingest_text
    assert "Source URL: https://example.com/a" in ingest_text


def test_research_agent_can_skip_compile(tmp_settings: Settings):
    client = MagicMock(spec=UltramemoryClient)
    client._make_session_key.return_value = "uk-research-123"
    client.ingest = AsyncMock(return_value={"memories_created": 1})

    connector = MagicMock()
    connector.research = AsyncMock(
        return_value=[
            SearchResult(
                title="Alpha",
                url="https://example.com/a",
                text="Alpha facts",
                score=0.8,
            )
        ]
    )

    compiler = MagicMock()
    compiler.compile_topic = AsyncMock()
    linker = MagicMock()

    agent = ResearchAgent(
        tmp_settings,
        client=client,
        connector=connector,
        compiler=compiler,
        linker=linker,
    )

    run = asyncio.run(agent.research("test topic", compile=False))

    assert run.memories_created == 1
    assert run.article_paths == []
    compiler.compile_topic.assert_not_called()
    linker.generate_backlinks.assert_not_called()


def test_research_agent_continues_after_ingest_failure(tmp_settings: Settings):
    client = MagicMock(spec=UltramemoryClient)
    client._make_session_key.return_value = "uk-research-123"
    client.ingest = AsyncMock(side_effect=[RuntimeError("boom"), {"memories_created": 2}])

    connector = MagicMock()
    connector.research = AsyncMock(
        return_value=[
            SearchResult(title="Alpha", url="https://example.com/a", text="Alpha facts", score=0.8),
            SearchResult(title="Beta", url="https://example.com/b", text="Beta facts", score=0.7),
        ]
    )

    compiler = MagicMock()
    compiler.compile_topic = AsyncMock(return_value=tmp_settings.articles_dir / "topic.md")

    linker = MagicMock()
    linker.generate_backlinks.return_value.links_added = 1

    agent = ResearchAgent(
        tmp_settings,
        client=client,
        connector=connector,
        compiler=compiler,
        linker=linker,
    )

    run = asyncio.run(agent.research("test topic", num_results=2, compile=True))

    assert run.memories_created == 2
    assert run.failed_results == ["https://example.com/a"]
    compile_chunks = compiler.compile_topic.await_args.args[1]
    assert len(compile_chunks) == 1
    assert compile_chunks[0]["source"] == "https://example.com/b"
