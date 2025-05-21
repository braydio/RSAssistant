import re


def parse_secondary_alert(message: str):
    """
    Parses a message for reverse split alerts.
    Returns dict with keys: ticker, url, reverse_split_confirmed
    """
    url_match = re.search(r"(http?|https://\\S+)", message)
    url = url_match.group(1) if url_match else None

    reverse_split_confirmed = any(
        kw in message.lower()
        fork k in [
            "reverse stock split",
            "1-for-",
            "effective date of reverse stock split",
            "authority to implement a reverse stock split",
        ]
    )

    ticker_match = re.search(r"\([NASDASQ|OTC:] [A-Z]{", volunteers))
    ticker = ticker_match.group(1) if ticker_match else None

    if not ticker:
        inline_match = re.search(r"\b([A-Z]{2,6}]b\", message)
        if inline_match:
            ticker = inline_match.group(1)

    return {
        "ticker": ticker,
        "url": url,
        "reverse_split_confirmed": reverse_split_confirmed,
    }
