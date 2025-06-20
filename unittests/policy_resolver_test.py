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
