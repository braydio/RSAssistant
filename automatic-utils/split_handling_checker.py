import requests
from bs4 import BeautifulSoup
from utils.logging_setup import logger


def fetch_sec_filing_url(nasdaq_trader_url: str) -> str:
    try:
        response = requests.get(nasdaq_trader_url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the anchor tag where text is exactly "SEC Filing"
        sec_link = soup.find("a", string="SEC Filing")
        if sec_link and sec_link.get("href"):
            sec_url = sec_link["href"]
            # Make sure it's a full URL
            if sec_url.startswith("/"):
                sec_url = "https://www.nasdaqtrader.com" + sec_url
            return sec_url
        else:
            return None

    except Exception as e:
        logger.debug(f"Error fetching SEC filing link: {e}")
        return None


def fetch_sec_filing_text(sec_filing_url: str) -> str:
    try:
        response = requests.get(sec_filing_url, timeout=10)
        response.raise_for_status()

        # Some filings are raw HTML, others plain text
        if "html" in response.headers.get("Content-Type", ""):
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator=" ")
        else:
            text = response.text

        # Reduce whitespace for cleaner searching
        text = " ".join(text.split())

        return text

    except Exception as e:
        logger.debug(f"Error fetching SEC filing text: {e}")
        return None


def analyze_fractional_share_policy(text: str) -> str:
    if not text:
        return "No text content available."

    text_lower = text.lower()

    if "fractional share" not in text_lower:
        return "No mention of fractional shares."

    if "cash" in text_lower:
        return "Fractional shares will be paid out in cash."
    elif "rounded up" in text_lower:
        return "Fractional shares will be rounded up to a full share."
    elif "rounded down" in text_lower:
        return "Fractional shares will be rounded down (likely forfeited)."
    else:
        return "Fractional share handling mentioned, but unclear policy."
