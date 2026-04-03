# Contributing to lexiconai

Thanks for your interest in contributing! Here's how to get started.

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

Ruff configuration is in `pyproject.toml`. Key settings:
- Target: Python 3.10+
- Line length: 100
- Enabled rules: E, F, I, N, W, UP

## Pull Request Guidelines

1. **Fork and branch** — create a feature branch from `main`.
2. **Keep PRs focused** — one logical change per PR.
3. **Add tests** — if you're fixing a bug or adding a feature, include test coverage.
4. **Run the checks** — make sure `pytest` and `ruff check .` pass before submitting.
5. **Write a clear description** — explain *what* changed and *why*.

## Reporting Issues

Open an issue at https://github.com/jared-goering/lexiconai/issues with:

- A clear title and description
- Steps to reproduce (if it's a bug)
- Expected vs. actual behavior
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
