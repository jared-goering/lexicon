"""Click CLI — the 'uk' command for managing your knowledge base."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from ultraknowledge.config import get_settings


def run_async(coro):
    """Run an async function from sync Click commands."""
    return asyncio.run(coro)


@click.group()
@click.version_option(package_name="ultraknowledge")
def cli():
    """ultraknowledge — LLM-compiled personal knowledge base.

    Ingest information from URLs, files, and web searches. An LLM compiles
    everything into a browseable wiki of interconnected markdown articles.
    """


@cli.command()
@click.argument("source")
@click.option("--title", "-t", help="Title for the ingested content")
@click.option("--type", "source_type", type=click.Choice(["url", "file", "text", "folder"]), help="Source type (auto-detected if omitted)")
def ingest(source: str, title: str | None, source_type: str | None):
    """Ingest a URL, file, folder, or raw text into the knowledge base.

    Examples:

        uk ingest https://example.com/article

        uk ingest ./paper.pdf

        uk ingest ./research/ --type folder

        uk ingest "Some important fact" --type text --title "Quick note"
    """
    settings = get_settings()

    # Auto-detect source type
    if source_type is None:
        if source.startswith(("http://", "https://")):
            source_type = "url"
        elif Path(source).is_dir():
            source_type = "folder"
        elif Path(source).exists():
            source_type = "file"
        else:
            source_type = "text"

    if source_type == "url":
        from ultraknowledge.connectors.url import URLConnector

        connector = URLConnector(settings)
        chunk = run_async(connector.fetch_and_ingest(source))
        click.echo(f"Ingested: {chunk['title']}")
        click.echo(f"  Source: {source}")
        click.echo(f"  Length: {len(chunk['text'])} chars")

    elif source_type == "file":
        from ultraknowledge.connectors.files import FileConnector

        connector = FileConnector(settings)
        chunk = connector.ingest_file(source)
        click.echo(f"Ingested: {chunk['title']}")
        click.echo(f"  File: {source}")
        click.echo(f"  Length: {len(chunk['text'])} chars")

    elif source_type == "folder":
        from ultraknowledge.connectors.files import FileConnector

        connector = FileConnector(settings)
        chunks = connector.ingest_folder(source)
        click.echo(f"Ingested {len(chunks)} files from {source}")
        for chunk in chunks:
            click.echo(f"  - {chunk['metadata']['filename']}")

    elif source_type == "text":
        chunk = {
            "text": source,
            "source": "manual",
            "title": title or "Quick note",
            "metadata": {"type": "manual"},
        }
        click.echo(f"Ingested: {chunk['title']}")
        click.echo(f"  Length: {len(source)} chars")

    # TODO: Send chunk(s) to Ultramemory


@cli.command()
@click.argument("query")
@click.option("--num", "-n", default=10, help="Number of results")
def research(query: str, num: int):
    """Research a topic via Exa web search and ingest results.

    Example:

        uk research "transformer architecture advances 2025"
    """
    from ultraknowledge.connectors.web_search import ExaConnector

    settings = get_settings()
    connector = ExaConnector(settings)

    click.echo(f"Researching: {query}")
    results = run_async(connector.research(query, num_results=num))

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"\nFound {len(results)} results:\n")
    for i, r in enumerate(results, 1):
        click.echo(f"  {i}. {r.title}")
        click.echo(f"     {r.url}")
        click.echo(f"     Score: {r.score:.3f} | {len(r.text)} chars")
        click.echo()

    # TODO: Ingest results into Ultramemory
    click.echo(f"Results ready for ingestion into knowledge base.")


@cli.command()
@click.argument("question")
def ask(question: str):
    """Ask a question and get an answer from the knowledge base.

    Example:

        uk ask "What are the key differences between GPT-4 and Claude?"
    """
    from ultraknowledge.qa import QAAgent

    settings = get_settings()
    agent = QAAgent(settings)

    click.echo(f"Searching knowledge base...\n")
    response = run_async(agent.answer_or_research(question))

    click.echo(response.answer)

    if response.citations:
        click.echo(f"\n--- Citations ---")
        for c in response.citations:
            click.echo(f"  [{c.article_title}]({c.article_path}) (relevance: {c.relevance_score:.2f})")

    if response.needs_research:
        click.echo(f"\n--- Knowledge gap detected ---")
        click.echo("Suggested research queries:")
        for q in response.suggested_queries:
            click.echo(f"  uk research \"{q}\"")


@cli.command("compile")
@click.option("--topic", "-t", help="Compile a specific topic (default: all)")
def compile_kb(topic: str | None):
    """Trigger wiki compilation from ingested chunks.

    Reads all ingested content from Ultramemory, groups by topic,
    and generates/updates markdown articles.

    Example:

        uk compile

        uk compile --topic "machine learning"
    """
    from ultraknowledge.compiler import WikiCompiler
    from ultraknowledge.linker import AutoLinker

    settings = get_settings()
    compiler = WikiCompiler(settings)
    linker = AutoLinker(settings)

    click.echo("Compiling knowledge base...")
    paths = run_async(compiler.recompile_all())

    click.echo(f"Compiled {len(paths)} articles")
    for p in paths:
        click.echo(f"  - {p.name}")

    click.echo("\nGenerating backlinks...")
    report = linker.generate_backlinks()
    click.echo(f"  Links added: {report.links_added}")
    if report.orphan_articles:
        click.echo(f"  Orphan articles: {', '.join(report.orphan_articles)}")

    click.echo("\nRebuilding index...")
    index_path = linker.rebuild_index()
    click.echo(f"  Index: {index_path}")


@cli.command()
@click.option("--stale-days", default=30, help="Days before an article is considered stale")
def lint(stale_days: int):
    """Run quality checks on the knowledge base.

    Checks for contradictions, stale articles, gaps, and quality issues.

    Example:

        uk lint

        uk lint --stale-days 7
    """
    from ultraknowledge.linter import KBLinter

    settings = get_settings()
    kb_linter = KBLinter(settings)

    click.echo("Linting knowledge base...\n")
    report = run_async(kb_linter.lint(stale_days=stale_days))

    click.echo(report.summary())

    if report.issues:
        click.echo()
        for issue in report.issues:
            icon = {"error": "E", "warning": "W", "info": "I"}[issue.severity]
            article = f" [{issue.article}]" if issue.article else ""
            click.echo(f"  [{icon}] {issue.category}{article}: {issue.message}")
            if issue.details:
                click.echo(f"      {issue.details}")


@cli.command("export")
@click.argument("topic")
@click.option("--format", "-f", "fmt", type=click.Choice(["slides", "report", "briefing"]), default="report", help="Export format")
@click.option("--output", "-o", type=click.Path(), help="Output directory")
def export_article(topic: str, fmt: str, output: str | None):
    """Export an article as slides, report, or briefing.

    Examples:

        uk export "machine learning" --format slides

        uk export "transformer architecture" --format briefing -o ./output
    """
    from ultraknowledge.export import Exporter

    settings = get_settings()
    exp = Exporter(settings)
    output_dir = Path(output) if output else None

    try:
        export_fn = {"slides": exp.to_slides, "report": exp.to_report, "briefing": exp.to_briefing}[fmt]
        result = export_fn(topic, output_dir)
        click.echo(f"Exported: {result.output_path}")
        click.echo(f"  Format: {result.format}")
        click.echo(f"  Words: {result.word_count}")
    except FileNotFoundError:
        click.echo(f"Error: Article not found for topic '{topic}'", err=True)
        sys.exit(1)


@cli.command("serve")
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", "-p", default=None, type=int, help="Port to listen on")
def serve(host: str | None, port: int | None):
    """Start the ultraknowledge web UI and API server.

    Example:

        uk serve

        uk serve --port 9000
    """
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "ultraknowledge.server:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=True,
    )


@cli.command("watch")
@click.option("--folder", type=click.Path(exists=True), help="Watch a folder for new files")
@click.option("--query", help="Watch for new web results matching a query")
@click.option("--interval", default=300, help="Check interval in seconds (default: 300)")
def watch(folder: str | None, query: str | None, interval: int):
    """Watch a folder or search query for new content.

    Periodically checks for new files or search results and ingests them.

    Examples:

        uk watch --folder ~/Documents/research --interval 60

        uk watch --query "LLM agents" --interval 600
    """
    if not folder and not query:
        click.echo("Error: Provide --folder or --query to watch", err=True)
        sys.exit(1)

    click.echo(f"Watching every {interval}s... (Ctrl+C to stop)")

    try:
        while True:
            if folder:
                from ultraknowledge.connectors.files import FileConnector

                connector = FileConnector(get_settings())
                chunks = connector.ingest_folder(folder)
                if chunks:
                    click.echo(f"  Found {len(chunks)} files")
                    # TODO: Send to Ultramemory

            if query:
                from ultraknowledge.connectors.web_search import ExaConnector

                connector = ExaConnector(get_settings())
                results = run_async(connector.research(query, num_results=5))
                if results:
                    click.echo(f"  Found {len(results)} new results for '{query}'")
                    # TODO: Send to Ultramemory

            import time
            time.sleep(interval)

    except KeyboardInterrupt:
        click.echo("\nStopped watching.")


if __name__ == "__main__":
    cli()
