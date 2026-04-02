"""Tests for the auto-linker."""

from __future__ import annotations

from pathlib import Path

import pytest

from ultraknowledge.config import Settings
from ultraknowledge.linker import AutoLinker


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = settings.kb_dir / "articles"
    settings.index_path = settings.kb_dir / "Index.md"
    settings.ensure_dirs()
    return settings


@pytest.fixture
def linker(tmp_settings: Settings) -> AutoLinker:
    return AutoLinker(tmp_settings)


def _write_article(articles_dir: Path, slug: str, title: str, body: str) -> Path:
    """Helper to write a test article with frontmatter."""
    path = articles_dir / f"{slug}.md"
    content = f"---\ntitle: {title}\nchunks: 5\n---\n\n# {title}\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


class TestScanArticles:
    def test_empty_directory(self, linker: AutoLinker, tmp_settings: Settings):
        articles = linker.scan_articles()
        assert articles == {}

    def test_single_article(self, linker: AutoLinker, tmp_settings: Settings):
        _write_article(tmp_settings.articles_dir, "machine-learning", "Machine Learning", "ML is great.")
        articles = linker.scan_articles()
        assert "machine-learning" in articles
        assert articles["machine-learning"].title == "Machine Learning"

    def test_multiple_articles(self, linker: AutoLinker, tmp_settings: Settings):
        _write_article(tmp_settings.articles_dir, "topic-a", "Topic A", "Content A")
        _write_article(tmp_settings.articles_dir, "topic-b", "Topic B", "Content B")
        articles = linker.scan_articles()
        assert len(articles) == 2


class TestGenerateBacklinks:
    def test_creates_wikilinks(self, linker: AutoLinker, tmp_settings: Settings):
        _write_article(
            tmp_settings.articles_dir,
            "neural-networks",
            "Neural Networks",
            "Neural networks are used in Deep Learning systems.",
        )
        _write_article(
            tmp_settings.articles_dir,
            "deep-learning",
            "Deep Learning",
            "Deep learning uses Neural Networks for feature learning.",
        )

        report = linker.generate_backlinks()
        assert report.links_added > 0

        # Check that wikilinks were inserted
        nn_content = (tmp_settings.articles_dir / "neural-networks.md").read_text()
        dl_content = (tmp_settings.articles_dir / "deep-learning.md").read_text()
        assert "[[Deep Learning]]" in nn_content or "[[deep learning]]" in nn_content.lower()
        assert "[[Neural Networks]]" in dl_content or "[[neural networks]]" in dl_content.lower()

    def test_no_self_links(self, linker: AutoLinker, tmp_settings: Settings):
        _write_article(
            tmp_settings.articles_dir,
            "recursion",
            "Recursion",
            "Recursion is when Recursion calls itself.",
        )
        report = linker.generate_backlinks()
        assert report.links_added == 0


class TestRebuildIndex:
    def test_empty_index(self, linker: AutoLinker, tmp_settings: Settings):
        path = linker.rebuild_index()
        content = path.read_text()
        assert "# Knowledge Base Index" in content
        assert "0 articles" in content

    def test_index_lists_articles(self, linker: AutoLinker, tmp_settings: Settings):
        _write_article(tmp_settings.articles_dir, "alpha", "Alpha Topic", "Content")
        _write_article(tmp_settings.articles_dir, "beta", "Beta Topic", "Content")
        path = linker.rebuild_index()
        content = path.read_text()
        assert "Alpha Topic" in content
        assert "Beta Topic" in content
        assert "2 articles" in content
