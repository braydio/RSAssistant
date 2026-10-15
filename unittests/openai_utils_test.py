import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.openai_utils import _clip_notice_text, _normalize_llm_payload


def test_normalize_llm_payload():
    payload = {
        "ticker": "abc",
        "reverse_split_confirmed": "true",
        "split_ratio": "1 for 10",
        "effective_date": "October 31, 2023",
        "fractional_share_policy": "Rounded to nearest whole",
    }
    result = _normalize_llm_payload(payload)
    assert result["ticker"] == "ABC"
    assert result["reverse_split_confirmed"] is True
    assert result["split_ratio"] == "1-10"
    assert result["effective_date"] == "2023-10-31"
    assert result["fractional_share_policy"] == "rounded_to_nearest_whole"


def test_clip_notice_text_prefers_fractional_section():
    text = ("x" * 7000) + " Fractional shares will be rounded up to the nearest whole."
    clipped = _clip_notice_text(text, max_chars=6000)
    assert "fractional shares" in clipped.lower()
    assert len(clipped) <= 6000


def test_normalize_llm_payload_accepts_hyphenated_policy_values():
    payload = {
        "ticker": "ptle",
        "reverse_split_confirmed": True,
        "split_ratio": "1-for-80",
        "effective_date": "2026-02-24",
        "fractional_share_policy": "rounded-up",
    }
    result = _normalize_llm_payload(payload)
    assert result["fractional_share_policy"] == "rounded_up"


def test_clip_notice_text_prefers_share_consolidation_section():
    text = ("x" * 7000) + " The Share Consolidation will be rounded up to the next whole number."
    clipped = _clip_notice_text(text, max_chars=6000)
    lower = clipped.lower()
    assert "share consolidation" in lower or "rounded up" in lower
    assert len(clipped) <= 6000


class OpenAILogRedactionTest(unittest.TestCase):
    def test_prompt_and_response_not_logged(self):
        from unittest import mock
        from utils import openai_utils

        secret = "SECRET-NOTICE-BODY-123"
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = {
            "choices": [{"message": {"content": "SECRET-LLM-OUTPUT {}"}}]
        }
        response.headers = {}
        response.status_code = 200
        with mock.patch.object(openai_utils, "OPENAI_POLICY_ENABLED", True), \
            mock.patch.object(openai_utils, "OPENAI_API_KEY", "k"), \
            mock.patch.object(openai_utils.requests, "post", return_value=response), \
            self.assertLogs(openai_utils.logger, level="DEBUG") as logs:
            openai_utils.extract_reverse_split_details(secret, ticker="ABC")
        joined = "\n".join(logs.output)
        self.assertNotIn(secret, joined)
        self.assertNotIn("SECRET-LLM-OUTPUT", joined)
