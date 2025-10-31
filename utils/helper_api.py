"""Helper functions for interpreting fractional share handling text."""

from __future__ import annotations

import logging
import re
from typing import Dict, Iterable, Optional

from utils.text_normalization import normalize_cash_in_lieu_phrases

logger = logging.getLogger(__name__)


def _extract_snippet(text: str, phrase: str, window: int = 12) -> Optional[str]:
    """Return a snippet around ``phrase`` within ``text``."""

    pattern = re.compile(
        rf"(?:\b\w+\b\s+){{0,{window}}}{re.escape(phrase)}(?:\s+\b\w+\b){{0,{window}}}",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _is_negated(snippet: str, phrase: str) -> bool:
    """Return True if ``snippet`` negates the presence of ``phrase``."""

    preceding = snippet.lower().split(phrase)[0]
    return bool(re.search(r"\b(no|not)\b\s*$", preceding))


def analyze_fractional_share_policy(text: str) -> Dict[str, Optional[str]]:
    """Classify how fractional shares are handled in ``text``.

    Args:
        text: Source text describing a corporate action.

    Returns:
        A dictionary describing whether fractional shares are mentioned and the
        inferred handling method.
    """

    default_response: Dict[str, Optional[str]] = {
        "mentions_fractional": False,
        "handling_method": None,
        "matched_snippet": None,
    }

    if not text:
        return default_response

    normalized_text = normalize_cash_in_lieu_phrases(text)
    lower_text = normalized_text.lower()
    fractional_terms = ("fractional share", "fractional shares")

    if not any(term in lower_text for term in fractional_terms):
        return default_response

    result: Dict[str, Optional[str]] = {
        "mentions_fractional": True,
        "handling_method": "unclear",
        "matched_snippet": None,
    }

    detection_map: Dict[str, Iterable[str]] = {
        "cash": (
            "cash in lieu",
            "paid in cash",
            "payment in cash",
            "cash equivalent",
            "settled in cash",
            "cash compensation",
        ),
        "round_down": ("rounded down", "truncated"),
        "round_up": (
            "rounded up",
            "round up",
            "rounded to nearest whole",
            "adjusted to full share",
            "adjusted to nearest share",
            "rounded",
        ),
    }

    for method, phrases in detection_map.items():
        for phrase in phrases:
            snippet = _extract_snippet(normalized_text, phrase)
            if snippet and not _is_negated(snippet, phrase):
                result["handling_method"] = method
                result["matched_snippet"] = snippet
                logger.debug("Detected %s via snippet: %s", method, snippet)
                return result

    first_term = next(term for term in fractional_terms if term in lower_text)
    snippet = _extract_snippet(normalized_text, first_term)
    if snippet:
        result["matched_snippet"] = snippet

    return result
