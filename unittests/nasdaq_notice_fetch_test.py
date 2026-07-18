import unittest
from unittest.mock import patch

from utils.policy_resolver import SplitPolicyResolver


CIIT_NOTICE_URL = (
    "http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-504"
)
CIIT_MOBILE_URL = (
    "https://m.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-504"
)
CIIT_DESKTOP_URL = (
    "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-504"
)
CIIT_PRESS_URL = (
    "https://www.newswire.com/news/"
    "tianci-international-inc-announces-1-for-10-reverse-stock-split"
)


def _valid_notice_html(extra_html=""):
    return f"""
    <html><body>
      <h1>Corporate Actions Alert</h1>
      <h2>ECA2026-504 - Information Regarding the Reverse Stock Split for CIIT</h2>
      <p>Markets Impacted: Nasdaq Capital Market</p>
      <p>Contact Information: Nasdaq Corporate Data Operations</p>
      <p>{'Notice details and trading information. ' * 12}</p>
      {extra_html}
    </body></html>
    """


class _Response:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def raise_for_status(self):
        return None


class NasdaqNoticeFetchTest(unittest.TestCase):
    def test_mobile_url_preserves_notice_id(self):
        self.assertEqual(
            SplitPolicyResolver._nasdaq_mobile_url(CIIT_NOTICE_URL),
            CIIT_MOBILE_URL,
        )

    def test_fetch_prefers_valid_mobile_notice(self):
        html = _valid_notice_html()
        with patch(
            "utils.policy_resolver.requests.get",
            return_value=_Response(html),
        ) as request:
            result, resolved_url = SplitPolicyResolver._fetch_nasdaq_notice_html(
                CIIT_NOTICE_URL
            )

        self.assertEqual(result, html)
        self.assertEqual(resolved_url, CIIT_MOBILE_URL)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], CIIT_MOBILE_URL)

    def test_fetch_rejects_challenge_and_uses_desktop_url(self):
        challenge = """
        <html><body>
          Request unsuccessful. Incapsula incident ID: 123456789
        </body></html>
        """
        valid_html = _valid_notice_html()
        with patch(
            "utils.policy_resolver.requests.get",
            side_effect=[_Response(challenge), _Response(valid_html)],
        ) as request:
            result, resolved_url = SplitPolicyResolver._fetch_nasdaq_notice_html(
                CIIT_NOTICE_URL
            )

        self.assertEqual(result, valid_html)
        self.assertEqual(resolved_url, CIIT_DESKTOP_URL)
        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            [CIIT_MOBILE_URL, CIIT_DESKTOP_URL],
        )

    def test_press_release_link_handles_nested_label(self):
        html = _valid_notice_html(
            f'<a href="{CIIT_PRESS_URL}"><span> Press\nRelease </span></a>'
        )
        result = SplitPolicyResolver.get_press_release_link_from_nasdaq(html)
        self.assertEqual(result, CIIT_PRESS_URL)

    def test_press_release_link_recognizes_distributor_domain(self):
        html = _valid_notice_html(
            f'<a href="{CIIT_PRESS_URL}">Company announcement</a>'
        )
        result = SplitPolicyResolver.get_press_release_link_from_nasdaq(html)
        self.assertEqual(result, CIIT_PRESS_URL)

    def test_sec_link_reuses_supplied_notice_html(self):
        sec_url = "https://www.sec.gov/Archives/edgar/data/123/filing.htm"
        html = _valid_notice_html(f'<a href="{sec_url}">SEC Filing 8-K</a>')
        with patch("utils.policy_resolver.requests.get") as request:
            result = SplitPolicyResolver.get_sec_link_from_nasdaq(
                CIIT_NOTICE_URL,
                ticker="CIIT",
                html_text=html,
                base_url=CIIT_MOBILE_URL,
            )

        self.assertEqual(result, sec_url)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
