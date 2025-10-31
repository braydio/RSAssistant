import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import helper_api


def test_analyze_fractional_share_policy_detects_cache_and_loo():
    text = "Fractional shares will be satisfied via cache and loo consideration."
    result = helper_api.analyze_fractional_share_policy(text)
    assert result["mentions_fractional"] is True
    assert result["handling_method"] == "cash"
    assert "cash in lieu" in result["matched_snippet"].lower()


def test_analyze_fractional_share_policy_handles_missing_fractional_reference():
    text = "The company will pay cache and loo for odd lots."
    result = helper_api.analyze_fractional_share_policy(text)
    assert result["mentions_fractional"] is False
    assert result["handling_method"] is None
    assert result["matched_snippet"] is None
