"""lexicon — LLM-compiled personal knowledge base engine."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexiconai")
except PackageNotFoundError:
    __version__ = "0.1.0"
