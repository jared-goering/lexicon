"""Tests for article export and sharing endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexicon.config import Settings
from lexicon.export import Exporter


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.kb_dir = tmp_path / "kb"
    settings.articles_dir = settings.kb_dir / "articles"
    settings.index_path = settings.kb_dir / "Index.md"
    settings.ensure_dirs()
    return settings


@pytest.fixture
def exporter(tmp_settings: Settings) -> Exporter:
    return Exporter(tmp_settings)


def _write_article(settings: Settings, slug: str, content: str) -> Path:
    path = settings.articles_dir / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_article_parses_frontmatter_sources(exporter: Exporter, tmp_settings: Settings):
    _write_article(
        tmp_settings,
        "transformer-architecture",
        """---
title: Transformer Architecture
compiled: 2026-04-03T00:14:49.733024+00:00
chunks: 6
sources:
  - https://example.com/paper
  - local-ref-123
---

# Transformer Architecture

## Overview

See [[Attention Mechanisms]] for context.
""",
    )

    article = exporter._load_article("transformer-architecture")

    assert article["title"] == "Transformer Architecture"
    assert article["chunks"] == 6
    assert article["sources"] == ["https://example.com/paper", "local-ref-123"]
    assert article["wikilinks"] == ["Attention Mechanisms"]


def test_load_article_extracts_sources_from_body(exporter: Exporter, tmp_settings: Settings):
    _write_article(
        tmp_settings,
        "vector-databases",
        """---
title: Vector Databases
chunks: 4
---

# Vector Databases

Read [the Faiss docs](https://faiss.ai) and https://milvus.io for more.

## Sources

- Internal Note 42
- https://example.com/whitepaper
""",
    )

    article = exporter._load_article("vector-databases")

    assert article["sources"] == [
        "https://faiss.ai",
        "https://milvus.io",
        "https://example.com/whitepaper",
        "Internal Note 42",
    ]


def test_snapshot_and_export_all_generate_html(exporter: Exporter, tmp_settings: Settings):
    _write_article(
        tmp_settings,
        "retrieval-augmented-generation",
        """---
title: Retrieval-Augmented Generation
sources:
  - https://example.com/rag
---

# Retrieval-Augmented Generation

Connects to [[Vector Databases]].
""",
    )

    snapshot = exporter.snapshot_article("retrieval-augmented-generation")
    full_export = exporter.export_all()

    snapshot_html = snapshot.output_path.read_text(encoding="utf-8")
    full_export_html = full_export.output_path.read_text(encoding="utf-8")

    assert "LEXICON" in snapshot_html
    assert "Static article snapshot" in snapshot_html
    assert "Table of Contents" in full_export_html
    assert "Retrieval-Augmented Generation" in full_export_html


def test_export_routes_serve_generated_files(tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from lexicon import server

    _write_article(
        tmp_settings,
        "transformers",
        """---
title: Transformers
sources:
  - https://example.com/attention
---

# Transformers

See [[Self Attention]].
""",
    )

    test_exporter = Exporter(tmp_settings)
    monkeypatch.setattr(server, "settings", tmp_settings)
    monkeypatch.setattr(server, "exporter", test_exporter)

    client = TestClient(server.app)

    export_response = client.post("/api/export", json={"topic": "transformers", "format": "html"})
    assert export_response.status_code == 200
    filename = export_response.json()["filename"]

    download_response = client.get(f"/api/exports/{filename}")
    assert download_response.status_code == 200
    assert "text/html" in download_response.headers["content-type"]

    snapshot_response = client.get("/api/snapshot/transformers")
    assert snapshot_response.status_code == 200
    assert "LEXICON" in snapshot_response.text

    export_all_response = client.post("/api/export-all")
    assert export_all_response.status_code == 200
    assert "text/html" in export_all_response.headers["content-type"]
