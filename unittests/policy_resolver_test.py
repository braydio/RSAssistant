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


def test_analyze_fractional_share_policy_handles_cache_and_loo():
    text = "Fractional shares, if any, will be settled via cache and loo payments."
    result = SplitPolicyResolver.analyze_fractional_share_policy(text)
    assert result == "Fractional shares will be paid out in cash."


def test_detect_policy_from_text_handles_cache_and_loo():
    text = "This notice confirms cache and loo for fractional shares."
    policy = SplitPolicyResolver.detect_policy_from_text(
        text, SplitPolicyResolver.NASDAQ_KEYWORDS
    )
    assert policy == "Cash in lieu"


def test_detect_policy_prioritizes_round_up_over_no_fractional():
    text = (
        "No fractional shares will be issued, and any fractional entitlement will "
        "be rounded up to the nearest whole share."
    )
    policy = SplitPolicyResolver.detect_policy_from_text(
        text, SplitPolicyResolver.NASDAQ_KEYWORDS
    )
    assert policy == "Rounded up"


def test_extract_main_text_prefers_primary_content():
    html = """
    <html>
      <body>
        <nav>Navigation links</nav>
        <article>
          <h1>Reverse Split Notice</h1>
          <p>The company announced a 1-for-10 reverse stock split.</p>
        </article>
        <footer>Footer text</footer>
      </body>
    </html>
    """
    text = SplitPolicyResolver._extract_main_text(html)
    assert "Reverse Split Notice" in text
    assert "Navigation links" not in text
