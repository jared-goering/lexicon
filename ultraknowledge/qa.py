"""Q&A agent — searches the knowledge base and synthesizes answers with citations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import litellm

from ultraknowledge.config import Settings, get_settings
from ultraknowledge.research import ResearchAgent, extract_research_metadata
from ultraknowledge.ultramemory_client import UltramemoryClient

QA_SYSTEM_PROMPT = """\
You are a knowledge-base assistant. Answer the user's question using ONLY the
provided context from the knowledge base. Requirements:
- Be accurate and concise
- Cite your sources using [Article Title](path) format
- If the context doesn't contain enough information, say so clearly
- Never fabricate information not present in the context
- If multiple sources disagree, note the disagreement
"""

RESEARCH_PROMPT = """\
The knowledge base doesn't have enough information to fully answer this question.
Based on the partial context below, suggest 2-3 specific search queries that would
help fill the gap. Return as a JSON list of strings.

Question: {question}
Partial context: {context}
"""


@dataclass
class QAResponse:
    """A Q&A response with answer and supporting citations."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    needs_research: bool = False
    suggested_queries: list[str] = field(default_factory=list)


@dataclass
class Citation:
    """A citation to a knowledge base article."""

    article_title: str
    article_path: str
    relevance_score: float = 0.0
    excerpt: str = ""


class QAAgent:
    """Search the knowledge base and synthesize answers with citations."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: UltramemoryClient | None = None,
        research_agent: ResearchAgent | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or UltramemoryClient(self.settings)
        self.research_agent = research_agent or ResearchAgent(self.settings, client=self.client)

    async def ask(self, question: str) -> QAResponse:
        """Answer a question using the knowledge base.

        Searches Ultramemory for relevant chunks, finds corresponding articles,
        and uses the LLM to synthesize an answer with citations.
        """
        # Search for relevant chunks
        chunks = await self._search(question)

        if not chunks:
            return QAResponse(
                answer="I don't have any information about this topic in the knowledge base.",
                needs_research=True,
                confidence=0.0,
            )

        # Build context from chunks and their source articles
        context = self._build_context(chunks)
        citations = self._extract_citations(chunks)

        # Synthesize answer
        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            temperature=0.2,
        )
        answer = response.choices[0].message.content

        # Estimate confidence based on chunk relevance scores
        scores = [c.get("score", 0.5) for c in chunks]
        confidence = sum(scores) / len(scores) if scores else 0.0

        return QAResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            needs_research=confidence < 0.3,
        )

    async def answer_or_research(self, question: str) -> QAResponse:
        """Answer from KB, auto-researching when nothing relevant exists yet."""
        response = await self.ask(question)

        if not response.citations:
            await self.research_agent.research(question, num_results=5, compile=True)
            response = await self.ask(question)

        if response.needs_research:
            queries = await self._suggest_research(question, response.answer)
            response.suggested_queries = queries

        return response

    async def _search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search Ultramemory for chunks relevant to the query."""
        results = await self.client.search(query, top_k=limit, include_source=True)
        # Map Ultramemory result fields to the format expected by _build_context/_extract_citations
        chunks = []
        for r in results:
            text = r.get("content", "")
            metadata = extract_research_metadata(text)
            chunks.append({
                "text": text,
                "source": metadata["url"] or r.get("source_session", "ultramemory"),
                "title": metadata["title"] or r.get("category", "Knowledge Base"),
                "score": r.get("similarity", 0.0),
                "url": metadata["url"] or r.get("source_session", "ultramemory"),
            })
        return chunks

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Format chunks into context for the LLM."""
        parts = []
        for chunk in chunks:
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            parts.append(f"[From: {source}]\n{text}")
        return "\n\n---\n\n".join(parts)

    def _extract_citations(self, chunks: list[dict[str, Any]]) -> list[Citation]:
        """Extract citation info from search result chunks."""
        seen: set[str] = set()
        citations = []
        for chunk in chunks:
            source = chunk.get("source", "")
            if source in seen:
                continue
            seen.add(source)
            citations.append(
                Citation(
                    article_title=chunk.get("title", source),
                    article_path=chunk.get("url", source),
                    relevance_score=chunk.get("score", 0.0),
                    excerpt=chunk.get("text", "")[:200],
                )
            )
        return citations

    async def _suggest_research(self, question: str, partial_answer: str) -> list[str]:
        """Use LLM to suggest research queries when KB info is insufficient."""
        response = await litellm.acompletion(
            model=self.settings.llm_model,
            messages=[
                {
                    "role": "user",
                    "content": RESEARCH_PROMPT.format(question=question, context=partial_answer),
                },
            ],
            temperature=0.5,
        )
        content = response.choices[0].message.content

        # Parse JSON list from response
        import json

        try:
            queries = json.loads(content)
            if isinstance(queries, list):
                return [str(q) for q in queries[:5]]
        except json.JSONDecodeError:
            pass

        return [question]  # fallback: use the original question
