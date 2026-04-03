"""Tests for settings and config defaults."""

from __future__ import annotations

from pathlib import Path

from lexicon.config import Settings


def test_default_ultramemory_db_path_is_under_lexicon_dir():
    settings = Settings()
    expected = Path.home() / ".lexicon" / "memory.db"
    assert settings.ultramemory_db_path == expected
    assert ".ultramemory" not in str(settings.ultramemory_db_path)
