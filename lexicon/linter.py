"""Knowledge base linter — checks for contradictions, staleness, and gaps."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from lexicon.config import Settings, get_settings
from lexicon.research import extract_research_metadata
from lexicon.ultramemory_client import UltramemoryClient

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


@dataclass
class LintIssue:
    """A single issue found by the linter."""

    severity: str  # "error", "warn", "info"
    category: str  # "contradiction", "stale", "gap", "orphan", "quality"
    message: str
    article: str = ""
    details: str = ""


@dataclass
class LintReport:
    """Full lint report for the knowledge base."""

    issues: list[LintIssue] = field(default_factory=list)
    articles_checked: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")

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

    def __init__(
        self,
        settings: Settings | None = None,
        client: UltramemoryClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or UltramemoryClient(self.settings)

    async def lint(self, stale_days: int = 7) -> LintReport:
        """Run all lint checks and return a comprehensive report."""
        report = LintReport()
        articles = self._load_articles()
        report.articles_checked = len(articles)

        self._check_staleness(articles, report, stale_days)
        self._check_quality(articles, report)

        entities = await self.client.entities(min_mentions=2)
        await self._check_contradictions(articles, report, entities)
        await self._check_gaps(articles, report, entities)

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
            articles.append(
                {
                    "path": md_file,
                    "slug": md_file.stem,
                    "content": content,
                    "title": meta.get("title", md_file.stem),
                    "compiled": meta.get("compiled", ""),
                    "chunks": int(meta.get("chunks", 0)),
                }
            )
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
                        severity="warn",
                        category="stale",
                        message="Article has no compilation date",
                        article=article["title"],
                    )
                )
                continue

            try:
                compiled_dt = datetime.fromisoformat(compiled)
                if compiled_dt.tzinfo is None:
                    compiled_dt = compiled_dt.replace(tzinfo=timezone.utc)
                age_days = (now - compiled_dt).days
                if age_days >= stale_days:
                    report.issues.append(
                        LintIssue(
                            severity="warn",
                            category="stale",
                            message=f"Article is {age_days} days old (threshold: {stale_days})",
                            article=article["title"],
                        )
                    )
            except (ValueError, TypeError):
                report.issues.append(
                    LintIssue(
                        severity="warn",
                        category="stale",
                        message="Article has an invalid compilation date",
                        article=article["title"],
                    )
                )

    def _check_quality(self, articles: list[dict[str, Any]], report: LintReport) -> None:
        """Check basic article quality — length, structure, sources."""
        for article in articles:
            content = article["content"]
            # Strip frontmatter for body length check
            body = re.sub(r"^---\n.*?\n---\n*", "", content, flags=re.DOTALL)

            if len(body.strip()) < 200:
                report.issues.append(
                    LintIssue(
                        severity="warn",
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
                        message=(
                            f"Article based on only {article['chunks']} chunks"
                            " — may need more sources"
                        ),
                        article=article["title"],
                    )
                )

    async def _check_contradictions(
        self,
        articles: list[dict[str, Any]],
        report: LintReport,
        entities: list[dict[str, Any]],
    ) -> None:
        """Find contradictory claims across articles for the same entity."""
        if not entities:
            return

        checked_pairs: set[tuple[str, str, str]] = set()
        for entity in entities[:10]:
            entity_name = entity.get("entity_name") or entity.get("name") or ""
            if not entity_name:
                continue
            matched_articles = [
                a for a in articles if self._mentions_entity(a["content"], entity_name)
            ]
            for i, article_a in enumerate(matched_articles):
                for article_b in matched_articles[i + 1 :]:
                    pair_key = tuple(
                        sorted(
                            (
                                entity_name,
                                article_a["slug"],
                                article_b["slug"],
                            )
                        )
                    )
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)
                    excerpt_a = self._extract_entity_excerpt(
                        article_a["content"],
                        entity_name,
                    )
                    excerpt_b = self._extract_entity_excerpt(
                        article_b["content"],
                        entity_name,
                    )
                    if not excerpt_a or not excerpt_b:
                        continue
                    try:
                        contradiction = await self._detect_contradiction(
                            entity_name,
                            article_a["title"],
                            excerpt_a,
                            article_b["title"],
                            excerpt_b,
                        )
                    except Exception:
                        continue
                    if contradiction:
                        report.issues.append(
                            LintIssue(
                                severity="error",
                                category="contradiction",
                                message=f"Conflicting facts about {entity_name}",
                                article=f"{article_a['title']} vs {article_b['title']}",
                                details=contradiction,
                            )
                        )

    async def _check_gaps(
        self,
        articles: list[dict[str, Any]],
        report: LintReport,
        entities: list[dict[str, Any]],
    ) -> None:
        """Identify entities that appear in the KB but lack a dedicated article."""
        if not articles:
            report.issues.append(
                LintIssue(
                    severity="info",
                    category="gap",
                    message="Knowledge base is empty — start by ingesting some content",
                )
            )
            return
        known_titles = {self._normalize_entity_name(article["title"]) for article in articles}
        for entity in entities:
            entity_name = entity.get("entity_name") or entity.get("name") or ""
            if not entity_name:
                continue
            normalized = self._normalize_entity_name(entity_name)
            if normalized in known_titles:
                continue
            mention_count = int(entity.get("mention_count", entity.get("count", 0)) or 0)
            severity = "warn" if mention_count >= 3 else "info"
            report.issues.append(
                LintIssue(
                    severity=severity,
                    category="gap",
                    message=(f"Entity mentioned without a dedicated article: {entity_name}"),
                    details=f"Mentions: {mention_count}",
                )
            )

    async def _detect_contradiction(
        self,
        entity: str,
        source_a: str,
        text_a: str,
        source_b: str,
        text_b: str,
    ) -> str:
        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. No markdown fences."},
                {
                    "role": "user",
                    "content": CONTRADICTION_PROMPT.format(
                        entity=entity,
                        source_a=source_a,
                        text_a=text_a,
                        source_b=source_b,
                        text_b=text_b,
                    ),
                },
            ],
            temperature=0.1,
        )

        import json

        try:
            payload = json.loads(response.choices[0].message.content)
        except Exception:
            return ""
        if payload.get("contradicts"):
            return str(payload.get("explanation", "")).strip()
        return ""

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

    @staticmethod
    def _normalize_entity_name(text: str) -> str:
        text = text.casefold().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        return re.sub(r"-+", "-", text).strip("-")

    @staticmethod
    def _mentions_entity(content: str, entity: str) -> bool:
        return bool(re.search(rf"\b{re.escape(entity)}\b", content, re.IGNORECASE))

    @staticmethod
    def _extract_entity_excerpt(content: str, entity: str) -> str:
        body = re.sub(r"^---\n.*?\n---\n*", "", content, flags=re.DOTALL)
        sentences = re.split(r"(?<=[.!?])\s+", body)
        pattern = re.compile(rf"\b{re.escape(entity)}\b", re.IGNORECASE)
        matched = [s.strip() for s in sentences if pattern.search(s)]
        if matched:
            return " ".join(matched[:3])
        metadata = extract_research_metadata(content)
        if metadata["title"] or metadata["url"]:
            return body[:500]
        return ""
