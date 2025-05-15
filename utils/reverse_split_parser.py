
import requests
import logging
from bs4 import BeautifulSoup

def get_reverse_split_handler_from_url(url: str) -> str:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "unknown"

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(separator=" ")

        if "Roundup" in text:
            return "Roundup"
        elif "Cache and Loo" in text or "Cache & Loo" in text:
            return "Cache and Loo"
        else:
            return "unknown"

    except Exception as e:
        logging.error(f "Error fetching split handler from URL: {e}")
        return "unknown"
