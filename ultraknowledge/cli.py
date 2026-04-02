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

    from ultraknowledge.ultramemory_client import UltramemoryClient

    client = UltramemoryClient(settings)

    if source_type == "url":
        from ultraknowledge.connectors.url import URLConnector

        connector = URLConnector(settings, client=client)
        chunk = run_async(connector.fetch_and_ingest(source))
        click.echo(f"Ingested: {chunk['title']}")
        click.echo(f"  Source: {source}")
        click.echo(f"  Length: {len(chunk['text'])} chars")
        um = chunk.get("ultramemory", {})
        if um:
            click.echo(f"  Memories created: {um.get('memories_created', 0)}")

    elif source_type == "file":
        from ultraknowledge.connectors.files import FileConnector

        connector = FileConnector(settings, client=client)
        chunk = run_async(connector.ingest_file_to_ultramemory(source))
        click.echo(f"Ingested: {chunk['title']}")
        click.echo(f"  File: {source}")
        click.echo(f"  Length: {len(chunk['text'])} chars")
        um = chunk.get("ultramemory", {})
        if um:
            click.echo(f"  Memories created: {um.get('memories_created', 0)}")

    elif source_type == "folder":
        from ultraknowledge.connectors.files import FileConnector

        connector = FileConnector(settings, client=client)
        chunks = run_async(connector.ingest_folder_to_ultramemory(source))
        click.echo(f"Ingested {len(chunks)} files from {source}")
        total_memories = 0
        for chunk in chunks:
            um = chunk.get("ultramemory", {})
            n = um.get("memories_created", 0)
            total_memories += n
            click.echo(f"  - {chunk['metadata']['filename']} ({n} memories)")
        click.echo(f"  Total memories created: {total_memories}")

    elif source_type == "text":
        session_key = client._make_session_key("text")
        result = run_async(client.ingest(
            text=source,
            session_key=session_key,
            agent_id="uk-text",
        ))
        click.echo(f"Ingested: {title or 'Quick note'}")
        click.echo(f"  Length: {len(source)} chars")
        click.echo(f"  Memories created: {result.get('memories_created', 0)}")


@cli.command("search")
@click.argument("query")
@click.option("--num", "-n", default=10, help="Number of results")
def search(query: str, num: int):
    """Search the knowledge base via Ultramemory semantic search.

    Example:

        uk search "transformer architecture"
    """
    from ultraknowledge.ultramemory_client import UltramemoryClient

    settings = get_settings()
    client = UltramemoryClient(settings)

    results = run_async(client.search(query, top_k=num))

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"Found {len(results)} results:\n")
    for i, r in enumerate(results, 1):
        content = r.get("content", "")
        preview = content[:120] + "..." if len(content) > 120 else content
        similarity = r.get("similarity", 0)
        category = r.get("category", "")
        confidence = r.get("confidence", 0)
        click.echo(f"  {i}. [{category}] (sim: {similarity:.3f}, conf: {confidence:.1f})")
        click.echo(f"     {preview}")
        click.echo()


@cli.command()
@click.argument("query")
@click.option("--num-results", "-n", default=10, help="Number of results")
@click.option("--compile/--no-compile", "compile_results", default=True, help="Compile and link after research")
def research(query: str, num_results: int, compile_results: bool):
    """Research a topic via Exa web search and ingest results.

    Example:

        uk research "transformer architecture advances 2025"
    """
    from ultraknowledge.research import ResearchAgent

    settings = get_settings()
    agent = ResearchAgent(settings)

    click.echo(f"Researching: {query}")
    result = run_async(agent.research(query, num_results=num_results, compile=compile_results))

    if not result.results:
        click.echo("No results found.")
        return

    click.echo(f"\nFound {len(result.results)} results:\n")
    for i, r in enumerate(result.results, 1):
        click.echo(f"  {i}. {r.title}")
        click.echo(f"     {r.url}")
        click.echo(f"     Score: {r.score:.3f} | {len(r.text)} chars")
        click.echo()

    click.echo(f"Memories created: {result.memories_created}")
    if result.article_paths:
        click.echo("Compiled articles:")
        for path in result.article_paths:
            click.echo(f"  - {path}")
        click.echo(f"Links added: {result.links_added}")


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

    click.echo("Searching knowledge base...\n")
    response = run_async(agent.answer_or_research(question))

    click.echo(response.answer)

    if response.citations:
        click.echo("\nSources:")
        for c in response.citations:
            click.echo(f"  - [{c.article_title}]({c.article_path})")

    if response.needs_research:
        click.echo("\n--- Knowledge gap detected ---")
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
@click.option("--stale-days", default=7, help="Days before an article is considered stale")
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
            icon = {"error": "E", "warn": "W", "info": "I"}[issue.severity]
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
@click.argument("topic", required=False)
@click.option("--interval", default=60, help="Watch interval in minutes")
@click.option("--list", "list_watches", is_flag=True, help="Show active watches")
@click.option("--stop", "stop_topic", help="Stop watching a topic")
def watch(topic: str | None, interval: int, list_watches: bool, stop_topic: str | None):
    """Watch a topic by rerunning research, compile, and lint on a schedule."""
    from ultraknowledge.watch import WatchAgent

    agent = WatchAgent(get_settings())

    if list_watches:
        watches = agent.list_watches()
        if not watches:
            click.echo("No active watches.")
            return
        for watch_entry in watches:
            last_run = watch_entry.last_run_at or "never"
            click.echo(f"{watch_entry.topic} | every {watch_entry.interval_minutes} min | last run: {last_run}")
        return

    if stop_topic:
        if agent.stop_watch(stop_topic):
            click.echo(f"Stopped watch: {stop_topic}")
        else:
            click.echo(f"No watch found for: {stop_topic}")
        return

    if not topic:
        click.echo("Error: provide a topic, --list, or --stop", err=True)
        sys.exit(1)

    click.echo(f"Watching '{topic}' every {interval} minutes... (Ctrl+C to stop)")
    try:
        run_async(agent.watch(topic, interval_minutes=interval))
    except KeyboardInterrupt:
        click.echo("\nStopped watching.")


if __name__ == "__main__":
    cli()
