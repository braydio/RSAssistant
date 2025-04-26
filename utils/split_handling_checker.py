import requests
from bs4 import BeautifulSoup


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
        print(f"Error fetching SEC filing link: {e}")
        return None
