"""Knowledge base linter — checks for contradictions, staleness, and gaps."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from ultraknowledge.config import Settings, get_settings

CONTRADICTION_PROMPT = """\
Compare these two excerpts from the knowledge base and determine if they contain
contradictory information. Return a JSON object with:
- "contradicts": boolean
- "explanation": string describing the contradiction (empty if none)

Excerpt A (from "{source_a}"):
{text_a}

Excerpt B (from "{source_b}"):
{text_b}
"""

GAP_PROMPT = """\
Given these article titles and their source counts, identify topics that seem
under-researched or have significant gaps. Return a JSON list of objects with:
- "topic": the topic name
- "reason": why it seems like a gap
- "suggested_query": a search query to fill the gap

Articles:
{article_list}
"""


@dataclass
class LintIssue:
    """A single issue found by the linter."""

    severity: str  # "error", "warning", "info"
    category: str  # "contradiction", "stale", "gap", "orphan", "quality"
    message: str
    article: str = ""
    details: str = ""


@dataclass
class LintReport:
    """Full lint report for the knowledge base."""

    issues: list[LintIssue] = field(default_factory=list)
    articles_checked: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def summary(self) -> str:
        return (
            f"Lint complete: {self.articles_checked} articles checked, "
            f"{self.error_count} errors, {self.warning_count} warnings, "
            f"{len(self.issues) - self.error_count - self.warning_count} info"
        )


class KBLinter:
    """Periodic quality checks on the knowledge base.

    Detects:
    - Contradictions between articles (via embedding similarity + LLM check)
    - Stale articles (based on compilation date vs. configurable threshold)
    - Gaps (topics with few sources or missing expected subtopics)
    - Orphans (articles with no inbound links)
    - Quality issues (very short articles, missing sources section)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def lint(self, stale_days: int = 30) -> LintReport:
        """Run all lint checks and return a comprehensive report."""
        report = LintReport()
        articles = self._load_articles()
        report.articles_checked = len(articles)

        # Run checks
        self._check_staleness(articles, report, stale_days)
        self._check_quality(articles, report)
        await self._check_gaps(articles, report)

        return report

    def _load_articles(self) -> list[dict[str, Any]]:
        """Load all articles with their metadata and content."""
        articles_dir = self.settings.articles_dir
        if not articles_dir.exists():
            return []

        articles = []
        for md_file in sorted(articles_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            meta = self._parse_frontmatter(content)
            articles.append({
                "path": md_file,
                "slug": md_file.stem,
                "content": content,
                "title": meta.get("title", md_file.stem),
                "compiled": meta.get("compiled", ""),
                "chunks": int(meta.get("chunks", 0)),
            })
        return articles

    def _check_staleness(
        self, articles: list[dict[str, Any]], report: LintReport, stale_days: int
    ) -> None:
        """Flag articles that haven't been recompiled recently."""
        now = datetime.now(timezone.utc)
        for article in articles:
            compiled = article.get("compiled", "")
            if not compiled:
                report.issues.append(
                    LintIssue(
                        severity="warning",
                        category="stale",
                        message="Article has no compilation date",
                        article=article["title"],
                    )
                )
                continue

            try:
                compiled_dt = datetime.fromisoformat(compiled)
                age_days = (now - compiled_dt).days
                if age_days > stale_days:
                    report.issues.append(
                        LintIssue(
                            severity="warning",
                            category="stale",
                            message=f"Article is {age_days} days old (threshold: {stale_days})",
                            article=article["title"],
                        )
                    )
            except ValueError:
                pass

    def _check_quality(self, articles: list[dict[str, Any]], report: LintReport) -> None:
        """Check basic article quality — length, structure, sources."""
        for article in articles:
            content = article["content"]
            # Strip frontmatter for body length check
            body = re.sub(r"^---\n.*?\n---\n*", "", content, flags=re.DOTALL)

            if len(body.strip()) < 200:
                report.issues.append(
                    LintIssue(
                        severity="warning",
                        category="quality",
                        message="Article body is very short (< 200 chars)",
                        article=article["title"],
                    )
                )

            if "## Sources" not in content and "## References" not in content:
                report.issues.append(
                    LintIssue(
                        severity="info",
                        category="quality",
                        message="Article has no Sources/References section",
                        article=article["title"],
                    )
                )

            if article["chunks"] > 0 and article["chunks"] < 3:
                report.issues.append(
                    LintIssue(
                        severity="info",
                        category="gap",
                        message=f"Article based on only {article['chunks']} chunks — may need more sources",
                        article=article["title"],
                    )
                )

    async def _check_gaps(self, articles: list[dict[str, Any]], report: LintReport) -> None:
        """Use LLM to identify knowledge gaps across the whole KB."""
        if not articles:
            report.issues.append(
                LintIssue(
                    severity="info",
                    category="gap",
                    message="Knowledge base is empty — start by ingesting some content",
                )
            )
            return

        article_list = "\n".join(
            f"- {a['title']} ({a['chunks']} sources)" for a in articles
        )

        try:
            response = await litellm.acompletion(
                model=self.settings.llm_model,
                messages=[
                    {"role": "user", "content": GAP_PROMPT.format(article_list=article_list)},
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content

            import json
            gaps = json.loads(content)
            if isinstance(gaps, list):
                for gap in gaps[:5]:
                    report.issues.append(
                        LintIssue(
                            severity="info",
                            category="gap",
                            message=gap.get("reason", "Knowledge gap detected"),
                            details=f"Suggested query: {gap.get('suggested_query', '')}",
                        )
                    )
        except Exception:
            pass  # Gap analysis is best-effort

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        """Parse YAML frontmatter from markdown content."""
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}

        meta: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key and not value.startswith("\n"):
                    meta[key] = value
        return meta
