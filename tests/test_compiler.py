"""Tests for the wiki compiler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ultraknowledge.compiler import WikiCompiler
from ultraknowledge.config import Settings
from ultraknowledge.ultramemory_client import UltramemoryClient


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Create settings pointing to a temporary directory."""
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
def compiler(tmp_settings: Settings, mock_client: UltramemoryClient) -> WikiCompiler:
    return WikiCompiler(tmp_settings, client=mock_client)


class TestSlugify:
    def test_basic_slug(self, compiler: WikiCompiler):
        assert compiler._slugify("Machine Learning") == "machine-learning"

    def test_special_characters(self, compiler: WikiCompiler):
        assert compiler._slugify("What's New in AI?") == "whats-new-in-ai"

    def test_multiple_spaces(self, compiler: WikiCompiler):
        assert compiler._slugify("too   many   spaces") == "too-many-spaces"

    def test_leading_trailing_hyphens(self, compiler: WikiCompiler):
        assert compiler._slugify("--leading-and-trailing--") == "leading-and-trailing"


class TestFormatChunks:
    def test_single_chunk(self, compiler: WikiCompiler):
        chunks = [{"text": "Hello world", "source": "test.md"}]
        result = compiler._format_chunks(chunks)
        assert "Hello world" in result
        assert "test.md" in result

    def test_multiple_chunks(self, compiler: WikiCompiler):
        chunks = [
            {"text": "First chunk", "source": "a.md"},
            {"text": "Second chunk", "source": "b.md"},
        ]
        result = compiler._format_chunks(chunks)
        assert "First chunk" in result
        assert "Second chunk" in result
        assert "---" in result  # separator


class TestBuildHeader:
    def test_header_contains_title(self, compiler: WikiCompiler):
        header = compiler._build_header("Test Topic", [])
        assert "title: Test Topic" in header

    def test_header_has_frontmatter_delimiters(self, compiler: WikiCompiler):
        header = compiler._build_header("Test", [])
        assert header.startswith("---")
        assert header.endswith("---")


class TestExtractManualSections:
    def test_no_manual_sections(self, compiler: WikiCompiler):
        content = "# Hello\n\nSome content\n"
        assert compiler._extract_manual_sections(content) == ""

    def test_single_manual_section(self, compiler: WikiCompiler):
        content = "# Hello\n<!-- manual -->\nKeep this\n<!-- manual -->\nOther content"
        result = compiler._extract_manual_sections(content)
        assert "Keep this" in result

    def test_multiple_manual_sections(self, compiler: WikiCompiler):
        content = (
            "<!-- manual -->\nSection 1\n<!-- manual -->\n"
            "Auto content\n"
            "<!-- manual -->\nSection 2\n<!-- manual -->"
        )
        result = compiler._extract_manual_sections(content)
        assert "Section 1" in result
        assert "Section 2" in result
