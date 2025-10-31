"""Helpers for classifying reverse split handling policies from web pages."""

import logging

import requests
from bs4 import BeautifulSoup


def get_reverse_split_handler_from_url(url: str) -> str:
    """Return the detected fractional share policy from the provided URL."""

    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "unknown"

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(separator=" ")
        text_lower = text.lower()

        if "roundup" in text_lower or "round up" in text_lower:
            return "Roundup"
        if "cash in lieu" in text_lower:
            return "Cash in lieu"
        return "unknown"

    except Exception as e:
        logging.error(f"Error fetching split handler from URL: {e}")
        return "unknown"
