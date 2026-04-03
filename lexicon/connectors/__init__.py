"""Connectors for ingesting knowledge from various sources."""

from __future__ import annotations

__all__ = ["ExaConnector", "FileConnector", "RSSConnector", "URLConnector"]


def __getattr__(name: str):
    if name == "FileConnector":
        from lexicon.connectors.files import FileConnector

        return FileConnector
    if name == "RSSConnector":
        from lexicon.connectors.rss import RSSConnector

        return RSSConnector
    if name == "URLConnector":
        from lexicon.connectors.url import URLConnector

        return URLConnector
    if name == "ExaConnector":
        from lexicon.connectors.web_search import ExaConnector

        return ExaConnector
    raise AttributeError(name)
