# Contributing to Lexicon

Thanks for your interest in contributing! This guide will get you up and running.

## Development Setup

```bash
git clone https://github.com/jared-goering/lexiconai
cd lexiconai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
```

For local model support (Ollama + sentence-transformers):

```bash
pip install -e '.[local]'
```

## Running Tests

```bash
pytest
```

To run a specific test file:

```bash
pytest tests/test_server.py -v
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format .
```

Key settings (configured in `pyproject.toml`):
- Target: Python 3.10+
- Line length: 100
- Enabled rules: E, F, I, N, W, UP

Please run both commands before submitting a PR.

## Commit Convention

Use clear, descriptive commit messages. We follow a lightweight conventional style:

- `feat:` new features
- `fix:` bug fixes
- `docs:` documentation changes
- `refactor:` code restructuring without behavior changes
- `test:` adding or updating tests
- `chore:` maintenance tasks (deps, CI, config)

Example: `feat: add PDF ingestion support`

## PR Process

1. **Fork and branch** — create a feature branch from `main`.
2. **Keep PRs focused** — one logical change per PR.
3. **Add tests** — if you're fixing a bug or adding a feature, include test coverage.
4. **Run the checks** — make sure `pytest` and `ruff check .` pass.
5. **Fill out the PR template** — describe what changed, why, and how to test it.
6. **Be responsive** — address review feedback promptly.

We use [issue templates](.github/ISSUE_TEMPLATE) for bugs and feature requests, and a [PR template](.github/PULL_REQUEST_TEMPLATE.md) to keep reviews consistent.

## Reporting Issues

Found a bug or have an idea? Open an issue using one of our templates:

- [Bug report](.github/ISSUE_TEMPLATE/bug_report.md)
- [Feature request](.github/ISSUE_TEMPLATE/feature_request.md)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
