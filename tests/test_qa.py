"""Tests for the Q&A agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexicon.config import Settings
from lexicon.qa import Citation, QAAgent, QAResponse
from lexicon.ultramemory_client import UltramemoryClient


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = settings.kb_dir / "articles"
    settings.index_path = settings.kb_dir / "Index.md"
    settings.ensure_dirs()
    return settings


@pytest.fixture
def mock_client() -> UltramemoryClient:
    client = MagicMock(spec=UltramemoryClient)
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def agent(tmp_settings: Settings, mock_client: UltramemoryClient) -> QAAgent:
    return QAAgent(tmp_settings, client=mock_client)


class TestBuildContext:
    def test_empty_chunks(self, agent: QAAgent):
        result = agent._build_context([])
        assert result == ""

    def test_single_chunk(self, agent: QAAgent):
        chunks = [{"text": "Some info", "source": "article.md"}]
        result = agent._build_context(chunks)
        assert "Some info" in result
        assert "article.md" in result

    def test_multiple_chunks_separated(self, agent: QAAgent):
        chunks = [
            {"text": "First", "source": "a.md"},
            {"text": "Second", "source": "b.md"},
        ]
        result = agent._build_context(chunks)
        assert "First" in result
        assert "Second" in result
        assert "---" in result


class TestExtractCitations:
    def test_deduplicates_sources(self, agent: QAAgent):
        chunks = [
            {"text": "A", "source": "same.md", "title": "Same"},
            {"text": "B", "source": "same.md", "title": "Same"},
        ]
        citations = agent._extract_citations(chunks)
        assert len(citations) == 1

    def test_preserves_order(self, agent: QAAgent):
        chunks = [
            {"text": "A", "source": "first.md", "title": "First"},
            {"text": "B", "source": "second.md", "title": "Second"},
        ]
        citations = agent._extract_citations(chunks)
        assert citations[0].article_title == "First"
        assert citations[1].article_title == "Second"


class TestQAResponse:
    def test_empty_response(self):
        r = QAResponse(answer="No info", needs_research=True, confidence=0.0)
        assert r.needs_research
        assert r.confidence == 0.0
        assert r.suggested_queries == []

    def test_response_with_citations(self):
        r = QAResponse(
            answer="The answer is 42",
            citations=[
                Citation(article_title="Guide", article_path="guide.md", relevance_score=0.9)
            ],
            confidence=0.85,
        )
        assert not r.needs_research
        assert len(r.citations) == 1
        assert r.citations[0].article_title == "Guide"


class TestAsk:
    def test_ask_empty_kb(self, agent: QAAgent):
        """When the KB has no data, the agent should indicate it needs research."""
        response = asyncio.run(agent.ask("What is quantum computing?"))
        assert response.needs_research or "don't have" in response.answer.lower()


class TestAnswerOrResearch:
    def test_research_runs_when_low_confidence_even_with_citations(self, agent: QAAgent):
        agent.ask = AsyncMock(
            side_effect=[
                QAResponse(
                    answer="Partial answer",
                    citations=[Citation(article_title="Guide", article_path="guide.md")],
                    confidence=0.1,
                    needs_research=True,
                ),
                QAResponse(answer="Improved answer", confidence=0.8),
            ]
        )
        agent.research_agent.research = AsyncMock()
        agent._suggest_research = AsyncMock(return_value=[])

        response = asyncio.run(agent.answer_or_research("test question"))

        assert response.answer == "Improved answer"
        agent.research_agent.research.assert_awaited_once_with("test question", num_results=5, compile=True)
