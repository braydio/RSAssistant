"""Utility helpers for normalizing corporate action phrases."""

from __future__ import annotations

import re
from typing import Iterable

# Known transcription or OCR variants of "cash in lieu" that appear in filings.
# These cover common mishearings such as "cache and loo".
_CASH_IN_LIEU_PATTERNS: Iterable[re.Pattern[str]] = (
    re.compile(r"\bca(?:sh|che)\s+(?:and|n)\s+loo\b", re.IGNORECASE),
    re.compile(r"\bca(?:sh|che)\s+(?:and|n)\s+lieu\b", re.IGNORECASE),
    re.compile(r"\bcache\s+in\s+lieu\b", re.IGNORECASE),
    re.compile(r"\bcash\s+in\s+loo\b", re.IGNORECASE),
    re.compile(r"\bcache\s+in\s+loo\b", re.IGNORECASE),
)


def normalize_cash_in_lieu_phrases(text: str) -> str:
    """Replace known variants of "cash in lieu" with the canonical phrase.

    Args:
        text: Raw text that may contain transcription errors.

    Returns:
        The text with all recognized variants replaced by "cash in lieu".
    """

    if not text:
        return text

    normalized = text
    for pattern in _CASH_IN_LIEU_PATTERNS:
        normalized = pattern.sub("cash in lieu", normalized)
    return normalized
