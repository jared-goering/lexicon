"""Configuration via environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """All configuration for ultraknowledge, read from environment variables."""

    # LLM
    llm_model: str = field(
        default_factory=lambda: os.getenv("UK_LLM_MODEL", "gemini/gemini-2.0-flash")
    )
    llm_temperature: float = field(
        default_factory=lambda: float(os.getenv("UK_LLM_TEMPERATURE", "0.3"))
    )

    # Ultramemory — ultraknowledge uses its OWN database, separate from OpenClaw's.
    # Set UK_ULTRAMEMORY_URL to point at an external server, or leave blank to use
    # the embedded engine with a dedicated DB at UK_ULTRAMEMORY_DB_PATH.
    ultramemory_url: str = field(
        default_factory=lambda: os.getenv("UK_ULTRAMEMORY_URL", "")
    )
    ultramemory_db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("UK_ULTRAMEMORY_DB_PATH", os.path.join(str(Path.home()), ".ultraknowledge", "memory.db"))
        )
    )
    ultramemory_collection: str = field(
        default_factory=lambda: os.getenv("UK_ULTRAMEMORY_COLLECTION", "ultraknowledge")
    )

    # Knowledge base output
    kb_dir: Path = field(
        default_factory=lambda: Path(os.getenv("UK_KB_DIR", "./kb"))
    )
    articles_dir: Path = field(init=False)
    index_path: Path = field(init=False)

    # Exa web search
    exa_api_key: str = field(
        default_factory=lambda: os.getenv("EXA_API_KEY", "")
    )

    # Compilation
    compile_frequency_minutes: int = field(
        default_factory=lambda: int(os.getenv("UK_COMPILE_FREQUENCY", "60"))
    )
    max_chunks_per_article: int = field(
        default_factory=lambda: int(os.getenv("UK_MAX_CHUNKS_PER_ARTICLE", "50"))
    )

    # Server
    host: str = field(default_factory=lambda: os.getenv("UK_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("UK_PORT", "8200")))

    def __post_init__(self) -> None:
        self.articles_dir = self.kb_dir / "articles"
        self.index_path = self.kb_dir / "Index.md"

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.articles_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Return a Settings instance from the current environment."""
    return Settings()
