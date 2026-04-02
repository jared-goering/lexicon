"""Connectors for ingesting knowledge from various sources."""

from __future__ import annotations

__all__ = ["ExaConnector", "FileConnector", "RSSConnector", "URLConnector"]


def __getattr__(name: str):
    if name == "FileConnector":
        from ultraknowledge.connectors.files import FileConnector

        return FileConnector
    if name == "RSSConnector":
        from ultraknowledge.connectors.rss import RSSConnector

        return RSSConnector
    if name == "URLConnector":
        from ultraknowledge.connectors.url import URLConnector

        return URLConnector
    if name == "ExaConnector":
        from ultraknowledge.connectors.web_search import ExaConnector

        return ExaConnector
    raise AttributeError(name)
