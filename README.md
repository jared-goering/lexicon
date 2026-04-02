# ultraknowledge

**An LLM-compiled personal knowledge base engine.**

You feed it information. An LLM compiles it into a wiki. You don't write the articles — the LLM does.

Inspired by [Andrej Karpathy's vision of LLM Knowledge Bases](https://x.com/karpathy/status/1881417542127geon) — the idea that LLMs should actively compile, organize, and maintain your personal knowledge, not just retrieve it.

## The Key Idea

Most knowledge tools make _you_ do the organizing. You tag, you file, you link. ultraknowledge flips this: you throw information at it (URLs, PDFs, search results, notes), and an LLM compiles everything into a browseable wiki of interconnected markdown articles — with backlinks, an index, citations, and source tracking.

The wiki is the output, not the input.

## How It Works

```
                    ┌─────────────────────────────────┐
                    │         Your Information         │
                    │  URLs · PDFs · Text · Searches   │
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────┐
                    │          Ultramemory             │
                    │   Embedding · Entity Extraction  │
                    │   Semantic Search · Fact Store    │
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────┐
                    │        Wiki Compiler (LLM)       │
                    │   Group by topic · Write .md     │
                    │   Update articles · Cite sources  │
                    └──────────────┬──────────────────┘
                                   │
                          ┌────────┼────────┐
                          ▼        ▼        ▼
                      articles/  Index.md  [[backlinks]]
                      *.md       (auto)    (auto)
```

## Features

### Phase 2

- **Research Mode** — `uk research "topic"` searches Exa, ingests results into Ultramemory, compiles findings into wiki articles, and rebuilds links
- **Watch Mode** — `uk watch "topic" --interval 60` runs recurring research, compilation, and linting with watch state stored in `~/.ultraknowledge/watches.json`
- **Q&A fallback research** — `uk ask "question"` automatically triggers web research when the KB has no relevant matches, then retries with formatted citations
- **Real lint checks** — `uk lint` reports staleness, contradiction risks, and entity coverage gaps with `info`, `warn`, and `error` severities

- **Ingest anything** — URLs, PDFs, text files, folders, RSS feeds, web search results
- **LLM-compiled wiki** — Articles are written and updated by an LLM, not by you
- **Auto-linking** — Entity mentions become `[[wikilinks]]`, index is rebuilt automatically
- **Active research** — Search the web via [Exa](https://exa.ai) and ingest results directly
- **Q&A with citations** — Ask questions, get answers grounded in your knowledge base
- **Quality linting** — Periodic checks for contradictions, staleness, and gaps
- **Export** — Generate slide decks (Marp), reports, and briefings from any topic
- **Provider flexible** — Works with Gemini, Claude, GPT, Ollama (local), or any LiteLLM-supported model
- **CLI + API + Web UI** — Use however you prefer

## Quickstart

### Install

```bash
pip install ultraknowledge
```

### Set up

```bash
# Required: an LLM provider (default: Gemini Flash via LiteLLM)
export GEMINI_API_KEY="your-key"

# Optional: Exa for web research
export EXA_API_KEY="your-key"

# Optional: use a different model
export UK_LLM_MODEL="anthropic/claude-sonnet-4-20250514"  # or "ollama/llama3" for local
```

### Use

```bash
# Ingest a URL
uk ingest https://arxiv.org/abs/2401.12345

# Ingest a folder of notes
uk ingest ./research-notes/ --type folder

# Research a topic and auto-compile it
uk research "transformer architecture advances 2025" --num-results 10

# Run ongoing research every hour
uk watch "transformer architecture advances 2025" --interval 60

# List or stop recurring watches
uk watch --list
uk watch --stop "transformer architecture advances 2025"

# Compile the wiki from everything ingested
uk compile

# Ask a question; if the KB is empty on that topic, research runs automatically
uk ask "What are the key differences between attention mechanisms?"

# Check knowledge base quality
uk lint --stale-days 7

# Export a topic as slides
uk export "attention mechanisms" --format slides

# Start the web UI
uk serve
```

### Web UI

```bash
uk serve
# Open http://localhost:8200
```

The web UI provides a dashboard, search, Q&A chat, and article browser. Full API docs at `/docs`.

## Architecture

| Component | Purpose |
|-----------|---------|
| **Ultramemory** | Semantic memory backend — embedding, entity/fact extraction, search |
| **Wiki Compiler** | LLM groups chunks by topic, writes/updates markdown articles |
| **Auto-Linker** | Scans articles for entity overlap, generates `[[backlinks]]` and `Index.md` |
| **Connectors** | Exa web search, URL fetch, file/folder ingest, RSS feeds |
| **Q&A Agent** | Searches KB → LLM synthesizes answer with citations |
| **Linter** | Checks for contradictions, staleness, gaps |
| **Exporter** | Renders articles as slides (Marp), reports, briefings |
| **Server** | FastAPI — dashboard, API, web UI |

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `UK_LLM_MODEL` | `gemini/gemini-2.0-flash` | LiteLLM model string |
| `UK_LLM_TEMPERATURE` | `0.3` | LLM temperature for article generation |
| `UK_ULTRAMEMORY_URL` | empty | Optional Ultramemory server URL; leave unset to use the embedded engine |
| `UK_ULTRAMEMORY_DB_PATH` | `~/.ultraknowledge/memory.db` | Embedded Ultramemory database path |
| `UK_KB_DIR` | `./kb` | Output directory for the wiki |
| `UK_COMPILE_FREQUENCY` | `60` | Auto-compile interval in minutes |
| `EXA_API_KEY` | — | Exa API key for web research |
| `UK_HOST` | `0.0.0.0` | Server host |
| `UK_PORT` | `8200` | Server port |

## CLI Reference

```
uk ingest <source>      Ingest a URL, file, folder, or text
uk research <query>     Search Exa, ingest to Ultramemory, compile, and link
uk ask <question>       Ask with grounded citations and auto-research fallback
uk compile              Compile wiki from ingested chunks
uk lint                 Report staleness, contradictions, and coverage gaps
uk export <topic>       Export as slides/report/briefing
uk serve                Start web UI + API server
uk watch <topic>        Run recurring research, compile, and lint cycles
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard |
| `/ingest` | POST | Ingest URL or text |
| `/search` | POST | Semantic search |
| `/ask` | POST | Q&A with citations |
| `/research` | POST | Web research via Exa |
| `/articles` | GET | List all articles |
| `/articles/{slug}` | GET | Read an article |
| `/compile` | POST | Trigger compilation |
| `/lint` | POST | Run quality checks |
| `/export` | POST | Export an article |

## Using with Local Models

ultraknowledge works great with local models via Ollama:

```bash
pip install ultraknowledge[local]
export UK_LLM_MODEL="ollama/llama3"
uk serve
```

## Manual Edits

Articles support manual sections that survive recompilation. Wrap your edits in `<!-- manual -->` markers:

```markdown
## LLM-Generated Section

This content will be updated by the compiler.

<!-- manual -->
## My Notes

This section is preserved across recompilations.
<!-- manual -->
```

## Development

```bash
git clone https://github.com/ultraknowledge/ultraknowledge
cd ultraknowledge
pip install -e ".[dev]"
pytest
```

## License

MIT
