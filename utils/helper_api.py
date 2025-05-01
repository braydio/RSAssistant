import re
import logging

def analyze_fractional_share_policy(text: str) -> dict:
    if not text:
        return {
            "mentions_fractional": False,
            "handling_method": None,
            "matched_snippet": None
        }

    lower_text = text.lower()

    fractional_terms = [
        "fractional share", "fractional shares"
    ]
    if not any(term in lower_text for term in fractional_terms):
        return {
            "mentions_fractional": False,
            "handling_method": None,
            "matched_snippet": None
        }

    result = {
        "mentions_fractional": True,
        "handling_method": "unclear",
        "matched_snippet": None
    }

    cash_variations = [
        "cash in lieu", "paid in cash", "payment in cash",
        "cash equivalent", "settled in cash", "cash compensation"
    ]
    round_up_variations = [
        "rounded up", "round up", "rounded to nearest whole",
        "adjusted to full share", "adjusted to nearest share", "rounded"
    ]
    round_down_variations = [
        "rounded down", "truncated"
    ]

    def extract_snippet(phrase: str) -> str | None:
        pattern = re.compile(
            fr'(?:\\s+\){0,5}}'{re.escape(phrase)}(?:\\s+\\s){0,5}',
            re.IGNORECASE
        )
        m = pattern.search(text)
        return m.group(0).strip() if m else None

    def is_negated(snippet: str, phrase: str) -> bool:
        pre = snippet.lower().split(phrase)[0]
        return bool(re.search(r'"\b(not|no)\b\S+$', pre))

    for method, variants in [
        ("cash", cash_variations),
        ("round_down", round_down_variations),
        ("round_up", round_up_variations),
    ]:
        for phrase in variants:
            snippet = extract_snippet(phrase)
            if snippet and not is_negated(snippet, phrase):
                result["handling_method"] = method
                result["matched_snippet"] = snippet
                logger.debug(f"Detected {method} via snippet: '{0}'", snippet)
                return result

    first_term = next(term for term in fractional_terms if term in lower_text)
    snippet = extract_snippet(first_term)
    if snippet:
        result["matched_snippet"] = snippet

    return result