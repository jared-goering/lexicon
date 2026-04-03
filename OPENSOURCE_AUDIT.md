# Open-Source Release Readiness Audit

**Project:** lexicon (repo directory still named `ultraknowledge`)
**Date:** 2026-04-03
**Auditor:** Claude (automated scan of all tracked files)

---

## 1. Hardcoded Secrets / API Keys

**Verdict: PASS (no real secrets committed)**

All API keys are read from environment variables. No actual key values appear in source.

| File | Line(s) | Detail |
|------|---------|--------|
| `start.sh` | 12-13 | Reads `OPENAI_API_KEY` and `EXA_API_KEY` from env/fallback files — no literal keys |
| `lexicon/config.py` | 45-46 | `os.getenv("EXA_API_KEY", "")` — safe empty default |
| `README.md` | 74, 77 | Placeholder strings `"your-key"` — correct |
| `.gitignore` | 25-27 | Covers `.env`, `.env.local`, `.env*.local` |

**One concern:** `start.sh:12-13` references `~/.openclaw/secrets/` and `~/.openclaw/.env` as fallback paths. "openclaw" is a separate/prior project name leaking into this repo (see also item 2b below).

---

## 2. Stale "ultraknowledge" References

**Verdict: MOSTLY CLEAN — 1 stale brand string + env-var prefix issue**

### 2a. Brand name in HTML export

| File | Line | String |
|------|------|--------|
| `kb/exports/retrieval-augmented-generation-rag-snapshot.html` | 227 | `ULTRAKNOWLEDGE` in `<div class="brand">` |

This is a generated export file. The template that produces it may have been fixed, but this stale artifact remains in the `kb/` directory.

### 2b. `UK_` environment variable prefix

All env vars still use the `UK_` prefix (stands for **U**ltra**K**nowledge):

| File | Lines | Examples |
|------|-------|---------|
| `lexicon/config.py` | 16, 19, 26, 30, 34, 39, 51, 54, 58, 59 | `UK_LLM_MODEL`, `UK_HOST`, `UK_PORT`, `UK_KB_DIR`, etc. |
| `start.sh` | 16-18 | `UK_LLM_MODEL`, `UK_HOST`, `UK_PORT` |
| `README.md` | 140-155 | Configuration table documents all `UK_*` vars |

**Recommendation:** Rename to `LX_` or `LEXICON_` prefix before release, or document that `UK_` is intentional.

### 2c. "openclaw" references (separate project name leak)

| File | Line | String |
|------|------|--------|
| `start.sh` | 12 | `~/.openclaw/secrets/openai-api-key.txt` |
| `start.sh` | 13 | `~/.openclaw/.env` |
| `lexicon/config.py` | 22 | Comment: `separate from OpenClaw's` |
| `lexicon/server.py` | 308 | Error message: `Set it in your environment or ~/.openclaw/.env` |
| `tests/test_config.py` | 10 | Test name: `test_default_ultramemory_db_path_is_isolated_from_openclaw` |

These should all be cleaned up — new users won't know what "openclaw" is.

---

## 3. .gitignore Completeness

**Verdict: PASS**

The `.gitignore` (45 lines) covers:

- Python: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, `dist/`, `build/`, `.eggs/`, `.venv/`
- Env files: `.env`, `.env.local`, `.env*.local`
- IDE: `.idea/`, `.vscode/`, `*.swp`, `*.swo`
- OS: `.DS_Store`, `Thumbs.db`
- Testing: `.pytest_cache/`, `.coverage`, `htmlcov/`
- Linting: `.ruff_cache/`
- Output: `kb/` (user-generated content)

No gaps identified.

---

## 4. XSS Vectors

**Verdict: PASS — one path-traversal bug (not XSS)**

The frontend is well-defended:

| Defense | Location |
|---------|----------|
| `escapeHTML()` utility | `lexicon/static/app.js:1201` — escapes `&`, `<`, `>`, `"` |
| DOMPurify + marked | `lexicon/static/app.js:122` — `DOMPurify.sanitize(marked.parse(...))` |
| Python `html.escape()` | `lexicon/export.py:392, 543, 549, 597` — all export HTML escapes user data |
| Extension `escapeHtml()` | `extension/popup.js:169-173` |

**No unescaped innerHTML assignments found** with user-controlled data.

### PATH TRAVERSAL — `GET /articles/{slug}` (CRITICAL)

| File | Lines | Issue |
|------|-------|-------|
| `lexicon/server.py` | 345-353 | `slug` is used directly in `settings.articles_dir / f"{slug}.md"` with **no sanitization** |

The `DELETE /articles/{slug}` handler at line 356 correctly sanitizes:
```python
safe_slug = Path(slug).name
if safe_slug != slug or ".." in slug:
    raise HTTPException(status_code=400, detail="Invalid slug")
```

But `GET /articles/{slug}` (line 345) and `GET /api/snapshot/{slug}` (line 485) skip this check entirely. A request to `/articles/../../etc/passwd` would read arbitrary files.

**Fix:** Apply the same `Path(slug).name` sanitization from `delete_article` to `get_article` and `snapshot_article_direct`.

---

## 5. README / Docs Gaps

**Verdict: MINOR GAPS**

The `README.md` (222 lines) is solid — install instructions, usage, architecture, config table, API reference, license.

| Gap | Detail |
|-----|--------|
| No security warning | README doesn't mention the server binds to `0.0.0.0` by default (`config.py:58`), meaning it's network-accessible. Should warn users. |
| `start.sh` inconsistency | `start.sh:17` defaults to `UK_HOST=127.0.0.1` (safe) but `config.py:58` defaults to `0.0.0.0` (unsafe). Running via `uk serve` vs `./start.sh` yields different bind behavior. |
| `start.sh:18` port inconsistency | `start.sh` defaults to port `8899`, `config.py:59` defaults to `8200`. Extension hardcodes `8899`. |
| No extension docs | `extension/` directory has no README explaining how to load the unpacked extension. |
| `DESIGN.md` exists | Good — covers architecture. No issues. |

---

## 6. Missing CONTRIBUTING.md

**Verdict: FAIL — not present**

No `CONTRIBUTING.md` file exists. For open-source readiness, add one covering:
- Development setup (`pip install -e ".[dev]"`, `pytest`, `ruff`)
- PR guidelines
- Code style (Ruff config is in `pyproject.toml`)
- Issue reporting

---

## 7. Packaging Issues (pip install flow)

**Verdict: MOSTLY PASS — one concern**

`pyproject.toml` is modern and complete (hatchling backend, entry point `uk = "lexicon.cli:cli"`, 14 dependencies, optional groups).

| Issue | Detail |
|-------|--------|
| Static/template files may not be included in wheel | `lexicon/static/` and `lexicon/templates/` contain HTML/CSS/JS needed at runtime. Hatchling uses implicit discovery but may not include non-`.py` files. Add `[tool.hatch.build.targets.wheel]` config with `packages = ["lexicon"]` and ensure `include` covers `static/**` and `templates/**`. |
| No `py.typed` marker | Minor — only matters if consumers want type-checking. |
| `sentence-transformers>=3.0` is heavy | This pulls PyTorch (~2 GB). Should be documented prominently or moved to an optional dep group. |

---

## 8. Extension Hardcoded Localhost

**Verdict: FAIL**

| File | Line | Value |
|------|------|-------|
| `extension/background.js` | 3 | `const API_BASE = 'http://localhost:8899';` |
| `extension/popup.js` | 3 | `const API_BASE = 'http://localhost:8899';` |
| `extension/manifest.json` | 7 | `"host_permissions": ["http://localhost:8899/*"]` |

Issues:
1. **Port mismatch**: Extension hardcodes `8899`, but `config.py` defaults to `8200`. Only `start.sh` defaults to `8899`. Users running `uk serve` will get a dead extension.
2. **No configurability**: No options page or `chrome.storage` to let users set a custom URL.
3. **HTTP only**: No HTTPS option. Acceptable for localhost but should be documented.

---

## 9. Missing API Auth / Rate Limiting

**Verdict: FAIL**

`lexicon/server.py` exposes 15+ endpoints with **zero authentication** and **zero rate limiting**.

### Endpoints at risk

| Endpoint | Line | Risk |
|----------|------|------|
| `POST /ingest` | 185 | Accepts arbitrary URLs — can trigger unbounded web scraping |
| `POST /research` | 302 | Triggers Exa web searches + LLM calls — costs money |
| `POST /ask` | 278 | Triggers LLM calls — costs money |
| `POST /compile` | 375 | CPU-intensive compilation |
| `DELETE /articles/{slug}` | 356 | **Destructive** — deletes articles |
| `POST /export` | 427 | CPU-intensive, writes to disk |
| `POST /api/export-all` | 496 | Exports entire KB |
| `POST /api/snapshot` | 474 | Generates files |

**No middleware**: No `CORSMiddleware`, no auth dependency, no rate limiter.

**Combined with default `0.0.0.0` bind** (`config.py:58`): anyone on the network can delete articles, trigger expensive LLM calls, and scrape arbitrary URLs through your server.

**Minimum fix for open-source:**
1. Change default host to `127.0.0.1` in `config.py:58`
2. Add optional bearer-token auth (env var `UK_API_TOKEN`)
3. Add rate limiting via `slowapi` or similar
4. Add `CORSMiddleware` with restrictive defaults
5. Document the security model prominently in README

---

## 10. Test Coverage Gaps

**Verdict: PARTIAL — 8 test files, but significant gaps**

### Covered modules (have test files)

| Module | Test file |
|--------|-----------|
| `compiler.py` | `tests/test_compiler.py` |
| `config.py` | `tests/test_config.py` |
| `export.py` | `tests/test_export.py` |
| `linker.py` | `tests/test_linker.py` |
| `qa.py` | `tests/test_qa.py` |
| `research.py` | `tests/test_research.py` |
| `ultramemory_client.py` | `tests/test_ultramemory_client.py` |
| `watch.py` | `tests/test_watch.py` |

### Uncovered modules (NO test files)

| Module | Risk |
|--------|------|
| `server.py` (15+ endpoints) | **HIGH** — no API route tests at all |
| `cli.py` | **MEDIUM** — no CLI integration tests |
| `connectors/rss.py` | **MEDIUM** — RSS parsing untested |
| `connectors/web_search.py` | **LOW** — Exa client wrapper |
| `connectors/url.py` | **LOW** — URL fetching has complex logic |
| `connectors/files.py` | **LOW** — file ingestion |
| `linter.py` | **LOW** — KB quality checker |

The most critical gap is `server.py` — every route (including the path-traversal-vulnerable ones) has zero test coverage.

---

## 11. Anything Embarrassing

### 11a. Port configuration chaos

Three different default ports across the codebase:

| Source | Default Port | Default Host |
|--------|-------------|--------------|
| `config.py:58-59` | `8200` | `0.0.0.0` |
| `start.sh:17-18` | `8899` | `127.0.0.1` |
| `extension/*` | `8899` | `localhost` |

This **will** confuse contributors. Unify to one default.

### 11b. Duplicated user-agent string

| File | Lines |
|------|-------|
| `lexicon/connectors/url.py` | 276, 299 |

Identical 126-char Chrome UA string copy-pasted. Extract to a constant.

### 11c. `start.sh` references another project

Lines 12-13 reference `~/.openclaw/` directories — an unrelated project. Confusing for new contributors.

### 11d. `sentence-transformers` dependency surprise

`pyproject.toml:38` pulls `sentence-transformers>=3.0` as a core dependency. This installs PyTorch (~2 GB). Users running `pip install lexicon` for a "lightweight knowledge base" will be surprised by a multi-GB install. Consider moving to an optional dep group.

### 11e. No `__main__.py`

Users can't run `python -m lexicon`. Adding `lexicon/__main__.py` with `from lexicon.cli import cli; cli()` is a one-liner that improves usability.

### 11f. Version triple-defined

Version `0.1.0` appears in three places with no single source of truth:
- `pyproject.toml:7`
- `lexicon/__init__.py:3`
- `lexicon/server.py:29`

Use `importlib.metadata` or hatchling's version source to keep one canonical location.

---

## Summary Scorecard

| Category | Status | Severity |
|----------|--------|----------|
| 1. Hardcoded secrets | PASS | — |
| 2. Stale naming (`ultraknowledge`, `openclaw`, `UK_`) | FAIL | Medium |
| 3. `.gitignore` completeness | PASS | — |
| 4. XSS vectors | PASS (but path traversal bug) | **Critical** |
| 5. README/docs gaps | WARN | Low |
| 6. Missing `CONTRIBUTING.md` | FAIL | Low |
| 7. Packaging issues | WARN | Low |
| 8. Extension hardcoded localhost | FAIL | Medium |
| 9. Missing API auth/rate limiting | FAIL | **High** |
| 10. Test coverage gaps | FAIL | Medium |
| 11. Embarrassing items | WARN | Low-Medium |

### Blockers for Public Release

1. **Fix path traversal** in `GET /articles/{slug}` and `GET /api/snapshot/{slug}` (`server.py:345, 485`)
2. **Change default bind to `127.0.0.1`** (`config.py:58`) — `0.0.0.0` exposes unauthenticated destructive endpoints to the network
3. **Unify port defaults** — pick `8200` or `8899`, use it everywhere
4. **Clean up `openclaw` references** — confusing to outside contributors
5. **Add at minimum optional token auth** for destructive/expensive endpoints
