"""Shared utility helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def safe_slug(slug: str) -> str:
    """Validate and sanitize a slug to prevent path traversal.

    Returns the sanitized slug or raises HTTPException(400).
    """
    sanitized = Path(slug).name
    if sanitized != slug or ".." in slug:
        raise HTTPException(status_code=400, detail="Invalid slug")
    return sanitized
