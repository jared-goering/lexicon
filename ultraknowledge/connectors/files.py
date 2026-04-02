"""File and folder connector — ingests local documents into the knowledge base."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from ultraknowledge.config import Settings, get_settings

# File types we can ingest directly as text
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".org",
    ".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".csv",
    ".html", ".htm",
    ".sh", ".bash", ".zsh",
    ".tex", ".bib",
}

# Extensions that need special handling (future)
BINARY_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".epub"}


class FileConnector:
    """Ingest files and folders into the knowledge base."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def ingest_file(self, path: str | Path) -> dict[str, Any]:
        """Read a file and return a chunk dict for ingestion.

        Handles text files directly. For PDFs and office docs, extracts
        what text we can (full support planned for future versions).
        """
        path = Path(path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()

        if suffix in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif suffix == ".pdf":
            text = self._extract_pdf(path)
        elif suffix in BINARY_EXTENSIONS:
            text = f"[Binary file: {path.name} — extraction not yet supported for {suffix}]"
        else:
            # Try reading as text, fall back gracefully
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = f"[Could not read file: {path.name}]"

        return {
            "text": text,
            "source": str(path),
            "title": path.stem.replace("-", " ").replace("_", " ").title(),
            "metadata": {
                "type": "file",
                "filename": path.name,
                "extension": suffix,
                "size_bytes": path.stat().st_size,
            },
        }

    def ingest_folder(self, path: str | Path, recursive: bool = True) -> list[dict[str, Any]]:
        """Ingest all supported files in a folder.

        Skips hidden files/directories and common non-content directories
        (node_modules, .git, __pycache__, etc.).
        """
        path = Path(path).resolve()
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}
        chunks = []

        pattern = "**/*" if recursive else "*"
        for file_path in sorted(path.glob(pattern)):
            if not file_path.is_file():
                continue
            if any(part.startswith(".") or part in skip_dirs for part in file_path.relative_to(path).parts):
                continue
            if file_path.suffix.lower() not in TEXT_EXTENSIONS | BINARY_EXTENSIONS:
                continue

            try:
                chunk = self.ingest_file(file_path)
                chunks.append(chunk)
            except Exception:
                continue  # Skip files that can't be read

        return chunks

    def watch_folder(self, path: str | Path) -> None:
        """Watch a folder for changes and ingest new/modified files.

        Placeholder for filesystem watching — will use watchdog or similar.
        For now, this is called periodically by the CLI watch command.
        """
        # TODO: Implement with watchdog for real-time monitoring
        # For now, the CLI watch command calls ingest_folder periodically
        raise NotImplementedError(
            "Real-time folder watching requires the watchdog package. "
            "Use 'uk watch --folder <path>' for polling-based watching."
        )

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from a PDF file. Best-effort with stdlib."""
        try:
            # Try PyPDF2/pypdf if available
            from pypdf import PdfReader

            reader = PdfReader(path)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except ImportError:
            return f"[PDF file: {path.name} — install 'pypdf' for text extraction]"
