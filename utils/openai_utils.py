"""OpenAI client helpers for reverse split parsing."""

import json
import re
import time
import uuid
from datetime import datetime

import requests

from utils.config_utils import (
    OPENAI_API_KEY,
    OPENAI_POLICY_ENABLED,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)
from utils.logging_setup import logger

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

_ALLOWED_POLICIES = {
    "rounded_to_nearest_whole",
    "rounded_up",
    "rounded_down",
    "cash_in_lieu",
    "no_fractional_shares",
    "unclear",
    "not_mentioned",
}


def _clip_notice_text(text: str, max_chars: int = 6000) -> str:
    """Clip notice text while prioritizing reverse-split context."""
    if not text:
        return text
    if len(text) <= max_chars:
        return text

    lowered = text.lower()
    anchors = [
        "fractional shares",
        "fractional share",
        "cash in lieu",
        "rounded up",
        "rounded to the next whole number",
        "rounded to next whole number",
        "rounded down",
        "reverse stock split",
        "reverse split",
        "share consolidation",
        "stock consolidation",
    ]

    start_idx = None
    for phrase in anchors:
        idx = lowered.find(phrase)
        if idx != -1:
            start_idx = idx if start_idx is None else min(start_idx, idx)

    if start_idx is None:
        return text[:max_chars]

    # Include leading context when possible.
    start_idx = max(0, start_idx - 500)
    end_idx = start_idx + max_chars
    if end_idx >= len(text):
        return text[-max_chars:]
    return text[start_idx:end_idx]


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    inline = re.search(r"(\{.*\})", text, re.DOTALL)
    if inline:
        return inline.group(1)
    return None


def _normalize_split_ratio(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    match = re.search(r"(\d+)\s*(?:-|:|/|x|X|for|to)\s*(\d+)", raw)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return raw


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _normalize_policy(value: str | None) -> str:
    if not value:
        return "not_mentioned"
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in _ALLOWED_POLICIES:
        return normalized
    if "cash" in normalized:
        return "cash_in_lieu"
    if "rounded_to_nearest" in normalized:
        return "rounded_to_nearest_whole"
    if "rounded_up" in normalized:
        return "rounded_up"
    if "rounded_down" in normalized:
        return "rounded_down"
    if "no_fractional" in normalized:
        return "no_fractional_shares"
    return "unclear"


def _coerce_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y"}:
            return True
        if lowered in {"false", "no", "n"}:
            return False
    return None


def _normalize_llm_payload(payload: dict) -> dict:
    ticker = payload.get("ticker")
    reverse_split_confirmed = _coerce_bool(payload.get("reverse_split_confirmed"))
    ratio = _normalize_split_ratio(payload.get("split_ratio"))
    effective_date = _normalize_date(payload.get("effective_date"))
    policy = _normalize_policy(payload.get("fractional_share_policy"))

    normalized = {
        "ticker": ticker.upper() if isinstance(ticker, str) and ticker else None,
        "reverse_split_confirmed": reverse_split_confirmed,
        "split_ratio": ratio,
        "effective_date": effective_date,
        "fractional_share_policy": policy,
    }
    return normalized


def extract_reverse_split_details(
    text: str, source_url: str | None = None, ticker: str | None = None
) -> dict | None:
    """Extract structured reverse split details from ``text`` using OpenAI."""
    if not OPENAI_POLICY_ENABLED:
        logger.info("OpenAI policy parsing disabled; skipping LLM parsing.")
        return None

    if not OPENAI_API_KEY:
        logger.info("OpenAI API key not configured; skipping LLM parsing.")
        return None

    if not text:
        logger.warning("No text supplied for OpenAI parsing.")
        return None

    clipped = _clip_notice_text(text, max_chars=6000)
    url_hint = f"Source URL: {source_url}" if source_url else "Source URL: N/A"
    ticker_hint = f"Expected ticker: {ticker}" if ticker else "Expected ticker: N/A"

    system_prompt = (
        "You extract reverse stock split details from financial notices. "
        "The goal is to identify reverse stock splits where fractional shares will be converted to full shares."
        "Return ONLY valid JSON with keys: "
        "ticker, reverse_split_confirmed, split_ratio, effective_date, "
        "fractional_share_policy. "
        "fractional_share_policy must be one of: "
        "rounded_up, rounded_to_nearest_whole, rounded_down, cash_in_lieu, no_fractional_shares, unclear, not_mentioned. "
        "split_ratio should be normalized as 'X-Y' (e.g., 1-10 for 1-for-10). "
        "effective_date should be YYYY-MM-DD. This is the record date, (NOT ANNOUNCEMENT DATE)"
        "Be mindful of the wording to accurately determine whether a full share"
        "will be returned to a trader who would have received a fractional share. "
        "If there is no mention if how fractional shares will be handled then fractional_share_policy MUST be returned as unclear. "
    )
    user_prompt = f"{url_hint}\n{ticker_hint}\n\n" "Notice text:\n" f"{clipped}"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
    }

    call_id = uuid.uuid4().hex[:8]
    openai_log_extra = {"never_dedupe": True}
    start_time = time.monotonic()
    logger.info(
        "OpenAI request started (call_id=%s, model=%s, text_chars=%s, source_url=%s, ticker=%s).",
        call_id,
        OPENAI_MODEL,
        len(clipped),
        source_url or "N/A",
        ticker or "N/A",
        extra=openai_log_extra,
    )
    logger.info(
        "OpenAI request payload (call_id=%s): system_prompt=%s | user_prompt=%s",
        call_id,
        system_prompt,
        user_prompt,
        extra=openai_log_extra,
    )
    try:
        with requests.post(
            OPENAI_CHAT_URL,
            headers=headers,
            json=payload,
            timeout=OPENAI_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            data = response.json()
            request_id = response.headers.get("x-request-id", "unknown")
            status_code = response.status_code
        elapsed = time.monotonic() - start_time
        logger.info(
            "OpenAI request succeeded (call_id=%s, status=%s, elapsed=%.2fs, request_id=%s).",
            call_id,
            status_code,
            elapsed,
            request_id,
            extra=openai_log_extra,
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info(
            "OpenAI raw response content (call_id=%s): %s",
            call_id,
            content,
            extra=openai_log_extra,
        )
    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(
            "OpenAI request failed (call_id=%s, elapsed=%.2fs, error=%s).",
            call_id,
            elapsed,
            e,
            extra=openai_log_extra,
        )
        return None

    json_blob = _extract_json_block(content)
    if not json_blob:
        logger.warning(
            "OpenAI response did not contain JSON (call_id=%s).",
            call_id,
            extra=openai_log_extra,
        )
        return None

    try:
        parsed = json.loads(json_blob)
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to decode OpenAI JSON (call_id=%s, error=%s).",
            call_id,
            e,
            extra=openai_log_extra,
        )
        return None

    return _normalize_llm_payload(parsed)
