"""Derives a filesystem-safe project slug from a question."""

import re

_NON_SLUG_CHARS_RE = re.compile(r"[^a-z0-9]+")
_MAX_LENGTH = 50
_FALLBACK_SLUG = "question"


def slugify(text: str) -> str:
    slug = _NON_SLUG_CHARS_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:_MAX_LENGTH].rstrip("-") or _FALLBACK_SLUG


def unique_slug(base_slug: str, existing: set[str]) -> str:
    """Disambiguate a fresh project's slug against already-used ones.

    Only used when starting a new project (no explicit --project given) —
    continuing an existing project always names it explicitly instead.
    """
    if base_slug not in existing:
        return base_slug

    suffix = 2
    while f"{base_slug}-{suffix}" in existing:
        suffix += 1
    return f"{base_slug}-{suffix}"
