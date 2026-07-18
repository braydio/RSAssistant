import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import openai_utils


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self._data = data or {}
        self.status_code = status_code
        self.headers = {"x-request-id": "req_test"}
        self.closed = False

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise openai_utils.requests.HTTPError(response=self)

    def close(self):
        self.closed = True


def _structured_response(payload):
    return {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(payload)}],
            }
        ]
    }


class OpenAIUtilsTest(unittest.TestCase):
    def test_normalize_llm_payload(self):
        payload = {
            "ticker": "abc",
            "reverse_split_confirmed": "true",
            "new_shares": 1,
            "old_shares": 10,
            "effective_date": "October 31, 2023",
            "record_date": "2023-10-27",
            "fractional_share_policy": "rounded_to_nearest_whole",
            "evidence": {"fractional_share_policy": "rounded to nearest"},
        }
        result = openai_utils._normalize_llm_payload(payload)
        self.assertEqual(result["ticker"], "ABC")
        self.assertIs(result["reverse_split_confirmed"], True)
        self.assertEqual(result["split_ratio"], "1-10")
        self.assertEqual(result["effective_date"], "2023-10-31")
        self.assertEqual(result["record_date"], "2023-10-27")
        self.assertEqual(
            result["fractional_share_policy"], "rounded_to_nearest_whole"
        )

    def test_normalize_rejects_invalid_date_and_ratio(self):
        result = openai_utils._normalize_llm_payload(
            {
                "split_ratio": "approximately ten",
                "effective_date": "soon",
                "fractional_share_policy": "invented-policy",
            }
        )
        self.assertIsNone(result["split_ratio"])
        self.assertIsNone(result["effective_date"])
        self.assertEqual(result["fractional_share_policy"], "unclear")

    def test_hallucinated_evidence_removes_unsupported_facts(self):
        details = openai_utils._normalize_llm_payload(
            {
                "ticker": "ABC",
                "reverse_split_confirmed": True,
                "new_shares": 1,
                "old_shares": 10,
                "effective_date": "2026-10-31",
                "record_date": None,
                "fractional_share_policy": "rounded_up",
                "evidence": {
                    "ticker": "ABC",
                    "reverse_split": "reverse stock split",
                    "ratio": "1-for-10",
                    "effective_date": "effective October 31, 2026",
                    "record_date": None,
                    "fractional_share_policy": "rounded up to a whole share",
                },
            }
        )
        result = openai_utils._validate_evidence_against_text(
            details, "ABC announced a reverse stock split."
        )
        self.assertEqual(result["ticker"], "ABC")
        self.assertTrue(result["reverse_split_confirmed"])
        self.assertIsNone(result["split_ratio"])
        self.assertIsNone(result["effective_date"])
        self.assertEqual(result["fractional_share_policy"], "unclear")
        self.assertEqual(
            {error["field"] for error in result["evidence_validation_errors"]},
            {"ratio", "effective_date", "fractional_share_policy"},
        )

    def test_clip_notice_text_includes_multiple_relevant_passages(self):
        text = (
            "Issuer ABC announced a transaction. "
            + ("x" * 6500)
            + " Reverse stock split effective date is October 31, 2026. "
            + ("y" * 2000)
            + " Fractional shares will be rounded up."
        )
        clipped = openai_utils._clip_notice_text(text, max_chars=6000)
        self.assertIn("Issuer ABC", clipped)
        self.assertIn("reverse stock split", clipped.lower())
        self.assertIn("fractional shares", clipped.lower())
        self.assertLessEqual(len(clipped), 6000)

    @patch.object(openai_utils, "OPENAI_API_KEY", "test-key")
    @patch.object(openai_utils, "OPENAI_POLICY_ENABLED", True)
    @patch.object(openai_utils.requests, "post")
    def test_extract_uses_responses_schema_without_storage(self, post):
        model_payload = {
            "ticker": "ABC",
            "reverse_split_confirmed": True,
            "new_shares": 1,
            "old_shares": 10,
            "effective_date": "2026-10-31",
            "record_date": "2026-10-27",
            "fractional_share_policy": "rounded_up",
            "evidence": {
                "ticker": "ABC",
                "reverse_split": "1-for-10 reverse stock split",
                "ratio": "1-for-10",
                "effective_date": "effective October 31, 2026",
                "record_date": "record date October 27, 2026",
                "fractional_share_policy": "rounded up to the next whole share",
            },
        }
        post.return_value = FakeResponse(_structured_response(model_payload))

        notice = (
            "ABC announced a 1-for-10 reverse stock split, effective October 31, "
            "2026, for holders as of the record date October 27, 2026. Fractional "
            "shares will be rounded up to the next whole share."
        )
        result = openai_utils.extract_reverse_split_details(notice, ticker="ABC")

        self.assertEqual(result["split_ratio"], "1-10")
        request = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], openai_utils.OPENAI_RESPONSES_URL)
        self.assertIs(request["json"]["store"], False)
        self.assertTrue(request["json"]["text"]["format"]["strict"])
        self.assertNotIn("temperature", request["json"])
        self.assertIn(
            "one contiguous substring", request["json"]["instructions"]
        )

    @patch.object(openai_utils.time, "sleep")
    @patch.object(openai_utils.requests, "post")
    def test_transient_failure_is_retried(self, post, sleep):
        post.side_effect = [
            FakeResponse(status_code=429),
            FakeResponse(status_code=200),
        ]
        response = openai_utils._post_openai_request({}, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
