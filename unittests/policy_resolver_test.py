import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.policy_resolver import SplitPolicyResolver


def test_extract_round_up_snippet():
    text = (
        "The Company's former ADS holders will receive one ordinary share for each "
        "ADS previously held. All resulting fractional shares will be rounded up to "
        "the nearest whole number of shares."
    )
    snippet = SplitPolicyResolver.extract_round_up_snippet(text)
    assert "rounded up" in snippet.lower()


def test_extract_effective_date():
    text = "The reverse stock split will be effective on October 31, 2023."
    assert SplitPolicyResolver.extract_effective_date(text) == "2023-10-31"


def test_analyze_fractional_share_policy_handles_cash_in_lieu():
    text = "Fractional shares, if any, will be settled via cash in lieu payments."
    result = SplitPolicyResolver.analyze_fractional_share_policy(text)
    assert result == "Fractional shares will be paid out in cash."


def test_detect_policy_from_text_handles_cash_in_lieu():
    text = "This notice confirms cash in lieu for fractional shares."
    policy = SplitPolicyResolver.detect_policy_from_text(
        text, SplitPolicyResolver.NASDAQ_KEYWORDS
    )
    assert policy == "Cash in lieu"
