"""Export articles as slides (Marp), reports, and briefings using Jinja2 templates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ultraknowledge.config import Settings, get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ExportResult:
    """Result of an export operation."""

    output_path: Path
    format: str
    topic: str
    word_count: int


class Exporter:
    """Export knowledge base articles into various output formats."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(default_for_string=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def to_slides(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a Marp slide deck.

        Reads the article, splits by headings into slides, and renders
        through the Marp markdown template.
        """
        article = self._load_article(topic)
        template = self.env.get_template("slides.md.j2")

        sections = self._split_sections(article["body"])
        rendered = template.render(
            title=article["title"],
            sections=sections,
            sources=article.get("sources", []),
        )

        output = self._output_path(topic, "slides.md", output_dir)
        output.write_text(rendered, encoding="utf-8")
        return ExportResult(
            output_path=output,
            format="slides",
            topic=topic,
            word_count=len(rendered.split()),
        )

    def to_report(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a structured report with executive summary."""
        article = self._load_article(topic)
        template = self.env.get_template("report.md.j2")

        rendered = template.render(
            title=article["title"],
            body=article["body"],
            compiled=article.get("compiled", ""),
            sources=article.get("sources", []),
            chunk_count=article.get("chunks", 0),
        )

        output = self._output_path(topic, "report.md", output_dir)
        output.write_text(rendered, encoding="utf-8")
        return ExportResult(
            output_path=output,
            format="report",
            topic=topic,
            word_count=len(rendered.split()),
        )

    def to_briefing(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a concise briefing document.

        Designed for quick consumption — key facts, bullet points, and
        a short narrative summary.
        """
        article = self._load_article(topic)
        template = self.env.get_template("briefing.md.j2")

        rendered = template.render(
            title=article["title"],
            body=article["body"],
            compiled=article.get("compiled", ""),
        )

        output = self._output_path(topic, "briefing.md", output_dir)
        output.write_text(rendered, encoding="utf-8")
        return ExportResult(
            output_path=output,
            format="briefing",
            topic=topic,
            word_count=len(rendered.split()),
        )

    def _load_article(self, topic: str) -> dict[str, Any]:
        """Load an article by topic slug and parse its content."""
        import re

        slug = re.sub(r"[^\w\s-]", "", topic.lower().strip())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")

        article_path = self.settings.articles_dir / f"{slug}.md"
        if not article_path.exists():
            raise FileNotFoundError(f"Article not found: {slug}.md")

        content = article_path.read_text(encoding="utf-8")

        # Parse frontmatter
        meta: dict[str, Any] = {}
        body = content
        fm_match = re.match(r"^---\n(.*?)\n---\n*", content, re.DOTALL)
        if fm_match:
            body = content[fm_match.end():]
            for line in fm_match.group(1).splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()

        return {
            "title": meta.get("title", topic),
            "body": body.strip(),
            "compiled": meta.get("compiled", ""),
            "chunks": meta.get("chunks", 0),
            "sources": [],  # TODO: Parse sources from frontmatter list
        }

    def _split_sections(self, body: str) -> list[dict[str, str]]:
        """Split article body into sections by ## headings for slides."""
        import re

        sections: list[dict[str, str]] = []
        parts = re.split(r"^(##\s+.+)$", body, flags=re.MULTILINE)

        # First part before any heading
        if parts[0].strip():
            sections.append({"heading": "", "content": parts[0].strip()})

        # Heading + content pairs
        for i in range(1, len(parts), 2):
            heading = parts[i].lstrip("#").strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append({"heading": heading, "content": content})

        return sections

    def _output_path(self, topic: str, suffix: str, output_dir: Path | None) -> Path:
        """Build the output file path."""
        import re

        slug = re.sub(r"[^\w\s-]", "", topic.lower().strip())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")

        base = output_dir or (self.settings.kb_dir / "exports")
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{slug}-{suffix}"
