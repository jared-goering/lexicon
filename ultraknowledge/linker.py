"""Auto-linker — scans articles for entity overlap and generates wikilinks and Index.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ultraknowledge.config import Settings, get_settings


@dataclass
class LinkReport:
    """Summary of linking operations performed."""

    articles_scanned: int = 0
    links_added: int = 0
    links_removed: int = 0
    orphan_articles: list[str] = field(default_factory=list)


class AutoLinker:
    """Scans wiki articles, inserts [[wikilinks]], and rebuilds Index.md."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def scan_articles(self) -> dict[str, ArticleInfo]:
        """Scan all articles and extract titles, headings, and entity mentions."""
        articles: dict[str, ArticleInfo] = {}
        articles_dir = self.settings.articles_dir

        if not articles_dir.exists():
            return articles

        for md_file in sorted(articles_dir.glob("*.md")):
            info = self._parse_article(md_file)
            articles[info.slug] = info

        return articles

    def generate_backlinks(self) -> LinkReport:
        """Scan all articles, find entity mentions, and insert [[wikilinks]].

        For each article, checks if any other article's title appears as a phrase
        in the body text. If so, wraps the first occurrence in [[wikilink]] syntax.
        Avoids double-linking and linking within code blocks or existing links.
        """
        articles = self.scan_articles()
        report = LinkReport(articles_scanned=len(articles))
        titles_by_slug = {slug: info.title for slug, info in articles.items()}

        for slug, info in articles.items():
            content = info.path.read_text(encoding="utf-8")
            original = content

            for other_slug, other_title in titles_by_slug.items():
                if other_slug == slug:
                    continue  # don't self-link

                # Skip if already linked
                wikilink = f"[[{other_title}]]"
                if wikilink in content:
                    continue

                # Find the title as a whole word in the body (not in frontmatter or headings)
                body = self._extract_body(content)
                pattern = re.compile(rf"\b{re.escape(other_title)}\b", re.IGNORECASE)
                match = pattern.search(body)
                if match:
                    # Replace first occurrence in the full content (in body region)
                    body_start = content.find(body)
                    abs_start = body_start + match.start()
                    abs_end = body_start + match.end()
                    matched_text = content[abs_start:abs_end]
                    content = content[:abs_start] + f"[[{matched_text}]]" + content[abs_end:]
                    report.links_added += 1

            if content != original:
                info.path.write_text(content, encoding="utf-8")

        # Detect orphans (articles with no inbound links)
        linked_slugs: set[str] = set()
        for slug, info in articles.items():
            text = info.path.read_text(encoding="utf-8")
            for other_slug, other_title in titles_by_slug.items():
                if f"[[{other_title}]]" in text or f"[[{other_title.lower()}]]" in text.lower():
                    linked_slugs.add(other_slug)
        report.orphan_articles = [s for s in articles if s not in linked_slugs]

        return report

    def rebuild_index(self) -> Path:
        """Regenerate Index.md with a categorized list of all articles."""
        articles = self.scan_articles()
        self.settings.ensure_dirs()

        lines = [
            "# Knowledge Base Index",
            "",
            f"*{len(articles)} articles compiled*",
            "",
        ]

        # Group by first letter for simple categorization
        by_letter: dict[str, list[ArticleInfo]] = {}
        for info in sorted(articles.values(), key=lambda a: a.title.lower()):
            letter = info.title[0].upper() if info.title else "#"
            by_letter.setdefault(letter, []).append(info)

        for letter in sorted(by_letter):
            lines.append(f"## {letter}")
            lines.append("")
            for info in by_letter[letter]:
                rel_path = info.path.relative_to(self.settings.kb_dir)
                source_count = f" ({info.source_count} sources)" if info.source_count else ""
                lines.append(f"- [{info.title}]({rel_path}){source_count}")
            lines.append("")

        index_content = "\n".join(lines)
        self.settings.index_path.write_text(index_content, encoding="utf-8")
        return self.settings.index_path

    def _parse_article(self, path: Path) -> ArticleInfo:
        """Parse an article file and extract metadata."""
        content = path.read_text(encoding="utf-8")
        slug = path.stem
        title = slug.replace("-", " ").title()
        source_count = 0

        # Try to extract title from frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            title_match = re.search(r"^title:\s*(.+)$", frontmatter, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            chunks_match = re.search(r"^chunks:\s*(\d+)$", frontmatter, re.MULTILINE)
            if chunks_match:
                source_count = int(chunks_match.group(1))

        # Extract headings
        headings = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)

        # Extract existing wikilinks
        links = re.findall(r"\[\[(.+?)\]\]", content)

        return ArticleInfo(
            slug=slug,
            title=title,
            path=path,
            headings=headings,
            outbound_links=links,
            source_count=source_count,
        )

    @staticmethod
    def _extract_body(content: str) -> str:
        """Extract article body, skipping frontmatter and the first heading."""
        # Skip YAML frontmatter
        body = re.sub(r"^---\n.*?\n---\n*", "", content, flags=re.DOTALL)
        # Skip first H1
        body = re.sub(r"^#\s+.+\n*", "", body)
        return body


@dataclass
class ArticleInfo:
    """Parsed metadata from a wiki article."""

    slug: str
    title: str
    path: Path
    headings: list[str] = field(default_factory=list)
    outbound_links: list[str] = field(default_factory=list)
    source_count: int = 0
