import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.openai_utils import _normalize_llm_payload


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
