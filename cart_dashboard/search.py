"""Plain text search: every word of the query must appear, case does not matter."""

from __future__ import annotations

import re

import pandas as pd


def words(query: str) -> list[str]:
    return query.lower().split()


def contains_all(texts: pd.Series, query: str) -> pd.Series:
    """True where the text contains every word of ``query`` (all True for an empty query)."""
    lower = texts.fillna("").astype(str).str.lower()
    hit = pd.Series(True, index=texts.index)
    for word in words(query):
        hit &= lower.str.contains(word, regex=False)
    return hit


def highlight(markdown: str, query: str) -> str:
    """Wrap the query words in <mark>, leaving `code` spans alone."""
    found = sorted(set(words(query)), key=len, reverse=True)
    if not found:
        return markdown
    pattern = re.compile("|".join(re.escape(w) for w in found), re.IGNORECASE)
    parts = markdown.split("`")
    for i in range(0, len(parts), 2):  # even parts are outside code spans
        parts[i] = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", parts[i])
    return "`".join(parts)
