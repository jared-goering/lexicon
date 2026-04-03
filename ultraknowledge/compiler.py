"""Wiki compiler — groups ingested chunks by topic and generates markdown articles."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm

from ultraknowledge.config import Settings, get_settings
from ultraknowledge.ultramemory_client import UltramemoryClient

MANUAL_MARKER = "<!-- manual -->"

SYSTEM_PROMPT = """\
You are a knowledge-base compiler. Given a set of information chunks about a topic,
write a well-structured markdown article. Requirements:
- Clear, factual prose in an encyclopedic tone
- Use ## headings to organize sections
- Cite sources inline as [Source Title](url) where available
- End with a ## Sources section listing all references
- If updating an existing article, preserve its structure and integrate new information
- Never fabricate facts — only use what's provided in the chunks
"""

GROUPING_PROMPT = """\
Given the following chunk summaries, group them into coherent topics.
Return a JSON object where keys are topic slugs (lowercase-hyphenated)
and values are objects with "title" (human-readable) and "chunk_ids" (list of IDs).

Chunks:
{chunk_summaries}
"""


class WikiCompiler:
    """Compiles ingested knowledge chunks into interconnected wiki articles."""

    def __init__(
        self, settings: Settings | None = None, client: UltramemoryClient | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self.client = client or UltramemoryClient(self.settings)

    async def compile_topic(self, topic: str, chunks: list[dict[str, Any]]) -> Path:
        """Compile chunks for a single topic into a markdown article.

        If the article already exists, updates it with new information.
        Respects <!-- manual --> markers to preserve hand-edited sections.
        """
        slug = self._slugify(topic)
        article_path = self.settings.articles_dir / f"{slug}.md"

        existing_content = None
        if article_path.exists():
            existing_content = article_path.read_text(encoding="utf-8")
            if MANUAL_MARKER in existing_content:
                return await self._update_article(article_path, existing_content, chunks)

        chunk_text = self._format_chunks(chunks)
        prompt = f"Topic: {topic}\n\nInformation chunks:\n{chunk_text}"
        if existing_content:
            prompt += f"\n\nExisting article to update:\n{existing_content}"

        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.settings.llm_temperature,
        )
        article_content = response.choices[0].message.content

        # Add metadata header
        header = self._build_header(topic, chunks)
        full_content = f"{header}\n\n{article_content}"
        article_path.write_text(full_content, encoding="utf-8")
        return article_path

    async def recompile_all(self) -> list[Path]:
        """Re-group all chunks by topic and recompile every article."""
        topics = await self._group_by_topic()
        paths = []
        for topic_slug, topic_data in topics.items():
            path = await self.compile_topic(topic_data["title"], topic_data["chunks"])
            paths.append(path)
        return paths

    async def _group_by_topic(self) -> dict[str, Any]:
        """Query Ultramemory for all chunks and group them by detected topic."""
        # Fetch a broad set of memories using a general query
        all_memories = await self.client.search("*", top_k=500, include_source=True)

        if not all_memories:
            return {}

        # Build summaries for the LLM
        chunk_summaries = []
        for i, mem in enumerate(all_memories):
            content = mem.get("content", "")
            category = mem.get("category", "unknown")
            preview = content[:200] + "..." if len(content) > 200 else content
            chunk_summaries.append(f"ID={i} | category={category} | {preview}")

        summaries_text = "\n".join(chunk_summaries)
        prompt = GROUPING_PROMPT.format(chunk_summaries=summaries_text)

        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. No markdown fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            grouping = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        # Map grouped IDs back to actual memory dicts as chunks
        topics: dict[str, Any] = {}
        for slug, data in grouping.items():
            title = data.get("title", slug.replace("-", " ").title())
            chunk_ids = data.get("chunk_ids", [])
            chunks = []
            for cid in chunk_ids:
                if isinstance(cid, int) and 0 <= cid < len(all_memories):
                    mem = all_memories[cid]
                    chunks.append({
                        "text": mem.get("content", ""),
                        "source": mem.get("source_session", "ultramemory"),
                        "id": mem.get("id"),
                    })
            if chunks:
                topics[slug] = {"title": title, "chunks": chunks}

        return topics

    async def _update_article(
        self, path: Path, existing: str, new_chunks: list[dict[str, Any]]
    ) -> Path:
        """Update an article that has manual sections, preserving them."""
        manual_sections = self._extract_manual_sections(existing)
        chunk_text = self._format_chunks(new_chunks)

        prompt = (
            f"Update this article with new information while preserving "
            f"all sections marked with {MANUAL_MARKER}.\n\n"
            f"Existing article:\n{existing}\n\n"
            f"New information:\n{chunk_text}\n\n"
            f"Manual sections to preserve exactly:\n{manual_sections}"
        )

        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.settings.llm_temperature,
        )
        title_match = re.search(r"^title:\s*(.+)$", existing, re.MULTILINE)
        topic = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()
        header = self._build_header(topic, new_chunks)
        full_content = f"{header}\n\n{response.choices[0].message.content}"
        path.write_text(full_content, encoding="utf-8")
        return path

    def _format_chunks(self, chunks: list[dict[str, Any]]) -> str:
        """Format chunks into a readable string for the LLM."""
        parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", chunk.get("content", ""))
            parts.append(f"[Chunk {i}] (source: {source})\n{text}")
        return "\n\n---\n\n".join(parts)

    def _build_header(self, topic: str, chunks: list[dict[str, Any]]) -> str:
        """Build a YAML frontmatter header for the article."""
        now = datetime.now(timezone.utc).isoformat()
        sources = [c.get("source", "unknown") for c in chunks]
        unique_sources = list(dict.fromkeys(sources))  # dedupe preserving order
        source_list = "\n".join(f"  - {s}" for s in unique_sources[:20])
        return (
            f"---\n"
            f"title: {topic}\n"
            f"compiled: {now}\n"
            f"chunks: {len(chunks)}\n"
            f"sources:\n{source_list}\n"
            f"---"
        )

    @staticmethod
    def _extract_manual_sections(content: str) -> str:
        """Extract sections marked with <!-- manual --> from article content."""
        sections = []
        in_manual = False
        current: list[str] = []
        for line in content.splitlines():
            if MANUAL_MARKER in line:
                in_manual = not in_manual
                if not in_manual:
                    sections.append("\n".join(current))
                    current = []
                continue
            if in_manual:
                current.append(line)
        return "\n\n".join(sections)

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert a topic title to a filename-safe slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        return re.sub(r"-+", "-", slug).strip("-")
