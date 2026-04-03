"""Export articles as markdown, HTML, PDF, and shareable snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lexicon.config import Settings, get_settings

try:
    import yaml
except ImportError:  # pragma: no cover - optional fallback
    yaml = None

TEMPLATES_DIR = Path(__file__).parent / "templates"

EXPORT_STYLE = """
:root {
  color-scheme: light;
  --bg: #f5f3ef;
  --surface: rgba(255, 252, 248, 0.96);
  --surface-strong: #fffaf4;
  --text: #1a1a1a;
  --muted: #6b6b6b;
  --border: #e5e2dc;
  --accent-1: #e8913a;
  --accent-2: #3a8fe8;
  --accent-3: #6b3ae8;
  --accent-4: #3ae89b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at top left, rgba(232, 145, 58, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(58, 143, 232, 0.08), transparent 24%),
    var(--bg);
  color: var(--text);
  line-height: 1.7;
}
.shell {
  width: min(920px, calc(100vw - 32px));
  margin: 32px auto 56px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: 0 24px 60px rgba(26, 26, 26, 0.08);
  overflow: hidden;
}
.hero {
  padding: 28px 32px 24px;
  border-bottom: 1px solid var(--border);
  background:
    linear-gradient(135deg, rgba(232, 145, 58, 0.14), rgba(58, 143, 232, 0.08)),
    var(--surface-strong);
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: "JetBrains Mono", "SFMono-Regular", ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: 0.22em;
  color: var(--muted);
  text-transform: uppercase;
}
.brand-dots {
  display: inline-grid;
  grid-template-columns: repeat(2, 8px);
  gap: 4px;
}
.brand-dots span {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: block;
}
.hero h1 {
  margin: 16px 0 8px;
  font-size: clamp(28px, 4vw, 42px);
  line-height: 1.15;
}
.meta,
.eyebrow,
.pill,
.toc a {
  font-family: "JetBrains Mono", "SFMono-Regular", ui-monospace, monospace;
}
.meta {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.content {
  padding: 32px;
}
.section {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid var(--border);
}
.section:first-child {
  border-top: 0;
  margin-top: 0;
  padding-top: 0;
}
.eyebrow {
  display: block;
  margin-bottom: 14px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.prose h1, .prose h2, .prose h3, .prose h4 { line-height: 1.25; margin: 1.35em 0 0.55em; }
.prose h1 { font-size: 1.95rem; }
.prose h2 { font-size: 1.45rem; }
.prose h3 { font-size: 1.15rem; }
.prose p { margin: 0.85em 0; }
.prose ul, .prose ol { margin: 0.85em 0; padding-left: 1.4em; }
.prose li { margin: 0.3em 0; }
.prose code {
  font-family: "JetBrains Mono", "SFMono-Regular", ui-monospace, monospace;
  font-size: 0.9em;
  background: #f7f4ee;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.12em 0.35em;
}
.prose pre {
  overflow-x: auto;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fcfaf6;
}
.prose pre code {
  border: 0;
  padding: 0;
  background: transparent;
}
.prose blockquote {
  margin: 1em 0;
  padding-left: 1em;
  border-left: 3px solid var(--border);
  color: var(--muted);
}
.prose a {
  color: var(--accent-2);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.prose table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
}
.prose th, .prose td {
  border: 1px solid var(--border);
  padding: 0.65em 0.8em;
  text-align: left;
}
.prose th {
  background: #faf7f1;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.prose hr {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 2em 0;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid rgba(58, 143, 232, 0.2);
  border-radius: 999px;
  background: rgba(58, 143, 232, 0.08);
  color: var(--accent-2);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-decoration: none;
}
.pill.wikilink-static {
  border-style: dashed;
}
.sources {
  margin: 0;
  padding-left: 1.2em;
}
.sources li + li {
  margin-top: 0.45em;
}
.toc {
  display: grid;
  gap: 10px;
}
.toc a {
  color: var(--text);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-decoration: none;
}
.toc a:hover {
  color: var(--accent-1);
}
.toc-item {
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.56);
}
.kb-article + .kb-article {
  margin-top: 36px;
}
.kb-article-title {
  margin: 0 0 16px;
  font-size: 28px;
}
@media print {
  body { background: #ffffff; }
  .shell { width: 100%; margin: 0; }
  .card { box-shadow: none; border: 0; }
}
@media (max-width: 640px) {
  .shell { width: min(100vw - 20px, 920px); margin: 12px auto 28px; }
  .hero, .content { padding: 22px 18px; }
}
"""


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
        """Export a topic as a Marp slide deck."""
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
        return self._result(output, "slides", topic, rendered)

    def to_report(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a structured markdown report."""
        article = self._load_article(topic)
        rendered = self._render_report_markdown(article)

        output = self._output_path(topic, "report.md", output_dir)
        output.write_text(rendered, encoding="utf-8")
        return self._result(output, "report", topic, rendered)

    def to_briefing(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a concise briefing document."""
        article = self._load_article(topic)
        template = self.env.get_template("briefing.md.j2")

        rendered = template.render(
            title=article["title"],
            body=article["body"],
            compiled=article.get("compiled", ""),
        )

        output = self._output_path(topic, "briefing.md", output_dir)
        output.write_text(rendered, encoding="utf-8")
        return self._result(output, "briefing", topic, rendered)

    def to_html(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as a styled HTML report."""
        article = self._load_article(topic)
        report_markdown = self._render_report_markdown(article)
        report_html = self._markdown_to_html(report_markdown, link_wikilinks=False)
        document = self._build_document(
            title=f"{article['title']} Report",
            subtitle="Structured export",
            meta=f"{article.get('chunks', 0)} sources",
            content_html=f'<section class="section prose">{report_html}</section>',
        )

        output = self._output_path(topic, "report.html", output_dir)
        output.write_text(document, encoding="utf-8")
        return self._result(output, "html", topic, report_markdown)

    def to_pdf(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a topic as PDF, or fall back to styled HTML when no PDF backend exists."""
        article = self._load_article(topic)
        report_markdown = self._render_report_markdown(article)
        report_html = self._markdown_to_html(report_markdown, link_wikilinks=False)
        document = self._build_document(
            title=f"{article['title']} Report",
            subtitle="Portable document export",
            meta=f"{article.get('chunks', 0)} sources",
            content_html=f'<section class="section prose">{report_html}</section>',
        )

        pdf_output = self._output_path(topic, "report.pdf", output_dir)
        if self._write_pdf(document, pdf_output):
            return self._result(pdf_output, "pdf", topic, report_markdown)

        html_output = self._output_path(topic, "report.html", output_dir)
        html_output.write_text(document, encoding="utf-8")
        return self._result(html_output, "html_report", topic, report_markdown)

    def snapshot_article(self, topic: str, output_dir: Path | None = None) -> ExportResult:
        """Export a self-contained static snapshot of an article."""
        article = self._load_article(topic)
        article_html = self._markdown_to_html(article["body"], link_wikilinks=False)

        sections: list[str] = [f'<section class="section prose">{article_html}</section>']
        if article["sources"]:
            sections.append(
                '<section class="section"><span class="eyebrow">Sources</span>'
                f'{self._render_source_list(article["sources"])}</section>'
            )
        if article["related_topics"]:
            sections.append(
                '<section class="section"><span class="eyebrow">Related Topics</span>'
                f'{self._render_topic_pills(article["related_topics"])}</section>'
            )
        if article["wikilinks"]:
            sections.append(
                '<section class="section"><span class="eyebrow">Wikilinks</span>'
                f'{self._render_topic_pills(article["wikilinks"], css_class="pill wikilink-static")}</section>'
            )

        document = self._build_document(
            title=article["title"],
            subtitle="Static article snapshot",
            meta=f"{article.get('chunks', 0)} compiled sources",
            content_html="".join(sections),
        )

        output = self._output_path(topic, "snapshot.html", output_dir)
        output.write_text(document, encoding="utf-8")
        return self._result(output, "snapshot", topic, article["body"])

    def export_all(self, output_dir: Path | None = None) -> ExportResult:
        """Export the full knowledge base as a single self-contained HTML page."""
        articles = [self._load_article(path.stem) for path in sorted(self.settings.articles_dir.glob("*.md"))]
        toc_items = []
        article_sections = []
        total_words = 0

        for article in articles:
            anchor = self._anchor_id(article["slug"])
            toc_items.append(
                f'<a class="toc-item" href="#{anchor}">{escape(article["title"])}</a>'
            )
            article_sections.append(
                f'<article class="kb-article" id="{anchor}">'
                f'<span class="eyebrow">Article</span>'
                f'<h2 class="kb-article-title">{escape(article["title"])}</h2>'
                f'<div class="prose">{self._markdown_to_html(article["body"], link_wikilinks=False)}</div>'
                f'{self._render_article_meta_sections(article)}'
                "</article>"
            )
            total_words += len(article["body"].split())

        empty_state = '<p class="meta">No articles compiled yet.</p>' if not articles else ""
        document = self._build_document(
            title="Lexicon Full Export",
            subtitle="Entire knowledge base snapshot",
            meta=f"{len(articles)} articles",
            content_html=(
                '<section class="section">'
                '<span class="eyebrow">Table of Contents</span>'
                f'<nav class="toc">{"".join(toc_items) or empty_state}</nav>'
                '</section>'
                f'<section class="section">{"".join(article_sections) or empty_state}</section>'
            ),
        )

        output = (output_dir or self._exports_dir()) / "lexicon-full-export.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        return ExportResult(
            output_path=output,
            format="html",
            topic="full-kb",
            word_count=total_words,
        )

    def _load_article(self, topic: str) -> dict[str, Any]:
        """Load an article by topic slug and parse its content."""
        slug = self._slugify(topic)
        article_path = self.settings.articles_dir / f"{slug}.md"
        if not article_path.exists():
            raise FileNotFoundError(f"Article not found: {slug}.md")

        content = article_path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        body = content
        fm_match = re.match(r"^---\n(.*?)\n---\n*", content, re.DOTALL)
        if fm_match:
            body = content[fm_match.end():]
            meta = self._parse_frontmatter(fm_match.group(1))

        title = str(meta.get("title") or self._title_from_body(body) or topic)
        sources = self._normalize_sources(meta.get("sources"), body)
        wikilinks = self._extract_wikilinks(body)

        return {
            "slug": slug,
            "title": title,
            "body": body.strip(),
            "compiled": meta.get("compiled", ""),
            "chunks": self._coerce_int(meta.get("chunks")),
            "sources": sources,
            "wikilinks": wikilinks,
            "related_topics": wikilinks,
        }

    def _split_sections(self, body: str) -> list[dict[str, str]]:
        """Split article body into sections by ## headings for slides."""
        sections: list[dict[str, str]] = []
        parts = re.split(r"^(##\s+.+)$", body, flags=re.MULTILINE)

        if parts and parts[0].strip():
            sections.append({"heading": "", "content": parts[0].strip()})

        for i in range(1, len(parts), 2):
            heading = parts[i].lstrip("#").strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append({"heading": heading, "content": content})

        return sections

    def _render_report_markdown(self, article: dict[str, Any]) -> str:
        template = self.env.get_template("report.md.j2")
        return template.render(
            title=article["title"],
            body=article["body"],
            compiled=article.get("compiled", ""),
            sources=article.get("sources", []),
            chunk_count=article.get("chunks", 0),
        )

    def _write_pdf(self, html_document: str, output_path: Path) -> bool:
        try:
            from weasyprint import HTML

            HTML(string=html_document).write_pdf(str(output_path))
            return True
        except Exception:
            pass

        try:
            import pdfkit

            pdfkit.from_string(html_document, str(output_path))
            return True
        except Exception:
            return False

    def _build_document(self, title: str, subtitle: str, meta: str, content_html: str) -> str:
        return (
            "<!DOCTYPE html>"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title>"
            f"<style>{EXPORT_STYLE}</style>"
            "</head><body>"
            '<div class="shell"><div class="card">'
            '<header class="hero">'
            '<div class="brand">'
            '<span class="brand-dots">'
            '<span style="background:var(--accent-1)"></span>'
            '<span style="background:var(--accent-2)"></span>'
            '<span style="background:var(--accent-3)"></span>'
            '<span style="background:var(--accent-4)"></span>'
            "</span> LEXICON</div>"
            f"<h1>{escape(title)}</h1>"
            f'<div class="meta">{escape(subtitle)} · {escape(meta)}</div>'
            "</header>"
            f'<main class="content">{content_html}</main>'
            "</div></div></body></html>"
        )

    def _render_article_meta_sections(self, article: dict[str, Any]) -> str:
        parts: list[str] = []
        if article["sources"]:
            parts.append(
                '<section class="section"><span class="eyebrow">Sources</span>'
                f'{self._render_source_list(article["sources"])}</section>'
            )
        if article["wikilinks"]:
            parts.append(
                '<section class="section"><span class="eyebrow">Wikilinks</span>'
                f'{self._render_topic_pills(article["wikilinks"], css_class="pill wikilink-static")}</section>'
            )
        return "".join(parts)

    def _render_source_list(self, sources: list[str]) -> str:
        items = "".join(f"<li>{self._source_to_html(source)}</li>" for source in sources)
        return f'<ol class="sources">{items}</ol>'

    def _render_topic_pills(self, topics: list[str], css_class: str = "pill") -> str:
        pills = "".join(f'<span class="{css_class}">[[{escape(topic)}]]</span>' for topic in topics)
        return f'<div class="chips">{pills}</div>'

    def _source_to_html(self, source: str) -> str:
        if self._looks_like_url(source):
            href = escape(source, quote=True)
            return f'<a href="{href}">{escape(source)}</a>'
        return escape(source)

    def _markdown_to_html(self, markdown_text: str, *, link_wikilinks: bool) -> str:
        source = markdown_text or ""
        source = self._replace_wikilinks(source, link_wikilinks)

        try:
            import markdown

            return markdown.markdown(
                source,
                extensions=["extra", "sane_lists", "tables", "fenced_code"],
            )
        except Exception:
            return self._basic_markdown_to_html(markdown_text, link_wikilinks=link_wikilinks)

    def _basic_markdown_to_html(self, markdown_text: str, *, link_wikilinks: bool) -> str:
        # Sanitize user content — _inline_markdown calls html.escape() on
        # each text fragment, and code blocks are escaped explicitly below.
        lines = markdown_text.splitlines()
        blocks: list[str] = []
        list_buffer: list[str] = []
        paragraph: list[str] = []
        in_code = False
        code_lines: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                text = " ".join(part.strip() for part in paragraph if part.strip())
                if text:
                    blocks.append(f"<p>{self._inline_markdown(text, link_wikilinks=link_wikilinks)}</p>")
                paragraph.clear()

        def flush_list() -> None:
            if list_buffer:
                items = "".join(
                    f"<li>{self._inline_markdown(item, link_wikilinks=link_wikilinks)}</li>"
                    for item in list_buffer
                )
                blocks.append(f"<ul>{items}</ul>")
                list_buffer.clear()

        for raw_line in lines:
            line = raw_line.rstrip()

            if line.startswith("```"):
                flush_paragraph()
                flush_list()
                if in_code:
                    code_html = escape("\n".join(code_lines))
                    blocks.append(f"<pre><code>{code_html}</code></pre>")
                    code_lines.clear()
                    in_code = False
                else:
                    in_code = True
                continue

            if in_code:
                code_lines.append(raw_line)
                continue

            if not line.strip():
                flush_paragraph()
                flush_list()
                continue

            heading = re.match(r"^(#{1,4})\s+(.*)$", line)
            if heading:
                flush_paragraph()
                flush_list()
                level = len(heading.group(1))
                blocks.append(
                    f"<h{level}>{self._inline_markdown(heading.group(2).strip(), link_wikilinks=link_wikilinks)}</h{level}>"
                )
                continue

            bullet = re.match(r"^[-*]\s+(.*)$", line)
            if bullet:
                flush_paragraph()
                list_buffer.append(bullet.group(1).strip())
                continue

            paragraph.append(line)

        flush_paragraph()
        flush_list()

        if in_code:
            code_html = escape("\n".join(code_lines))
            blocks.append(f"<pre><code>{code_html}</code></pre>")

        return "".join(blocks)

    def _inline_markdown(self, text: str, *, link_wikilinks: bool) -> str:
        text = escape(text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        text = self._replace_wikilinks(text, link_wikilinks)
        return text

    def _replace_wikilinks(self, text: str, link_wikilinks: bool) -> str:
        if link_wikilinks:
            return re.sub(
                r"\[\[([^\]]+)\]\]",
                lambda match: (
                    f'<a class="wikilink" href="#/article/{self._slugify(match.group(1))}">{escape(match.group(1))}</a>'
                ),
                text,
            )
        return re.sub(
            r"\[\[([^\]]+)\]\]",
            lambda match: f'<span class="pill wikilink-static">[[{escape(match.group(1))}]]</span>',
            text,
        )

    def _parse_frontmatter(self, frontmatter: str) -> dict[str, Any]:
        if yaml is not None:
            loaded = yaml.safe_load(frontmatter) or {}
            if isinstance(loaded, dict):
                return loaded

        meta: dict[str, Any] = {}
        current_list_key: str | None = None
        for raw_line in frontmatter.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            list_item = re.match(r"^\s*-\s+(.*)$", line)
            if list_item and current_list_key:
                meta.setdefault(current_list_key, []).append(list_item.group(1).strip())
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                meta[key] = value
                current_list_key = None
            else:
                meta[key] = []
                current_list_key = key
        return meta

    def _normalize_sources(self, frontmatter_sources: Any, body: str) -> list[str]:
        sources: list[str] = []

        if isinstance(frontmatter_sources, list):
            sources.extend(str(item).strip() for item in frontmatter_sources if str(item).strip())
        elif isinstance(frontmatter_sources, str) and frontmatter_sources.strip():
            sources.append(frontmatter_sources.strip())

        sources.extend(self._extract_body_sources(body))
        return self._dedupe_preserve_order(sources)

    def _extract_body_sources(self, body: str) -> list[str]:
        found: list[str] = []

        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body):
            target = match.group(1).strip()
            if target:
                found.append(target)

        for match in re.finditer(r"https?://[^\s)>\]]+", body):
            found.append(match.group(0).rstrip(".,;"))

        sources_section = re.search(
            r"^##\s+Sources\s*$([\s\S]+?)(?=^##\s|\Z)",
            body,
            flags=re.MULTILINE,
        )
        if sources_section:
            for line in sources_section.group(1).splitlines():
                bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
                if bullet:
                    item = bullet.group(1).strip()
                    if item:
                        found.append(item)

        return found

    def _extract_wikilinks(self, body: str) -> list[str]:
        return self._dedupe_preserve_order(match.group(1).strip() for match in re.finditer(r"\[\[([^\]]+)\]\]", body))

    def _title_from_body(self, body: str) -> str | None:
        match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    def _output_path(self, topic: str, suffix: str, output_dir: Path | None) -> Path:
        slug = self._slugify(topic)
        base = output_dir or self._exports_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{slug}-{suffix}"

    def _exports_dir(self) -> Path:
        return self.settings.kb_dir / "exports"

    def _result(self, path: Path, export_format: str, topic: str, rendered: str) -> ExportResult:
        return ExportResult(
            output_path=path,
            format=export_format,
            topic=topic,
            word_count=len(rendered.split()),
        )

    def _slugify(self, topic: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", topic.lower().strip())
        return re.sub(r"[\s_]+", "-", slug).strip("-")

    def _anchor_id(self, value: str) -> str:
        return re.sub(r"[^a-z0-9-]", "", self._slugify(value))

    def _coerce_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _looks_like_url(self, value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    def _dedupe_preserve_order(self, values: Any) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result
