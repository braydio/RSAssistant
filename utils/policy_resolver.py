# policy_resolver.py
import requests
import re
import logging

from utils.logging_setup import logger


class SplitPolicyResolver:
    """
    Fetches and analyzes reverse stock split notices from NASDAQ Trader and SEC filings.
    Determines if fractional shares are paid in cash or rounded up.
    """

    NASDAQ_KEYWORDS = [
        "cash in lieu",
        "no fractional shares",
        "rounded up",
        "not issuing fractional shares",
    ]

    SEC_KEYWORDS = [
        "cash in lieu",
        "rounded up",
        "rounded down",
        "fractional shares will not be issued",
        "paid in cash",
    ]

    @staticmethod
    def get_press_release_link_from_nasdaq(html_text):
        """Extract press release link if available in NASDAQ page."""
        match = re.search(
            r'href=\"(https://www\.nasdaq\.com/press-release/[^"]+)\"', html_text
        )
        return match.group(1) if match else None

    @classmethod
    def analyze_nasdaq_notice(cls, nasdaq_url):
        """Analyze a NASDAQ notice for fractional share handling."""
        try:
            res = requests.get(nasdaq_url, timeout=10)
            res.raise_for_status()
            text = res.text.lower()

            policy = cls.detect_policy_from_text(text, cls.NASDAQ_KEYWORDS)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url)
            press_url = cls.get_press_release_link_from_nasdaq(text)

            return {
                "policy": policy,
                "nasdaq_url": nasdaq_url,
                "sec_url": sec_url,
                "press_url": press_url,
            }
        except Exception as e:
            logger.error(f"Error analyzing NASDAQ notice: {e}")
            return None

    @staticmethod
    def get_sec_link_from_nasdaq(url):
        """Extract the SEC filing link from a NASDAQ Trader alert page."""
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            match = re.search(r"href=\"(https://www\.sec\.gov/[^\"]+)\"", res.text)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.warning(f"Failed to retrieve SEC link from NASDAQ: {e}")
            return None

    @staticmethod
    def detect_policy_from_text(text, keyword_list):
        """Scan given text for policy-related keywords."""
        for phrase in keyword_list:
            if phrase in text:
                return phrase.capitalize()
        return "Policy not clearly stated."

    @classmethod
    def analyze_nasdaq_notice(cls, nasdaq_url):
        """Analyze a NASDAQ notice for fractional share handling."""
        try:
            res = requests.get(nasdaq_url, timeout=10)
            res.raise_for_status()
            text = res.text.lower()
            policy = cls.detect_policy_from_text(text, cls.NASDAQ_KEYWORDS)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url)
            return {"policy": policy, "nasdaq_url": nasdaq_url, "sec_url": sec_url}
        except Exception as e:
            logger.error(f"Error analyzing NASDAQ notice: {e}")
            return None

    @classmethod
    def analyze_sec_filing(cls, sec_url):
        """Analyze an SEC filing for fractional share policy."""
        try:
            res = requests.get(sec_url, timeout=10)
            res.raise_for_status()
            text = res.text.lower()
            policy = cls.detect_policy_from_text(text, cls.SEC_KEYWORDS)
            return {"policy": policy, "sec_url": sec_url}
        except Exception as e:
            logger.warning(f"Failed to retrieve or analyze SEC filing: {e}")
            return {"policy": "Unable to retrieve SEC filing.", "sec_url": sec_url}

    @classmethod
    def full_analysis(cls, nasdaq_url):
        """Run full pipeline: from NASDAQ to SEC with policy output."""
        result = cls.analyze_nasdaq_notice(nasdaq_url)
        if result and result.get("sec_url"):
            sec_data = cls.analyze_sec_filing(result["sec_url"])
            result.update({"sec_policy": sec_data["policy"]})
