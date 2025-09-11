"""Parser for secondary channel reverse split alerts.

This module extracts tickers and URLs from Discord messages announcing
reverse stock splits. It coordinates with :mod:`on_message_utils` to
analyze NASDAQ notices or press releases and post summaries back to the
server. Fallback logic now handles press releases such as GlobeNewswire
articles that previously produced no notice.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Dict

from utils.on_message_utils import (
    OnMessagePolicyResolver,
    attempt_autobuy,
    build_policy_summary,
    post_policy_summary,
)

logger = logging.getLogger(__name__)


def alert_channel_message(message: str) -> Dict[str, Optional[str]]:
    """Parse a secondary channel message for reverse split details.

    Parameters
    ----------
    message:
        Raw Discord message content.

    Returns
    -------
    dict
        Mapping containing ``ticker``, ``url`` and a boolean flag
        ``reverse_split_confirmed``.
    """

    url_match = re.search(r"(https?://\S+)", message)
    url = url_match.group(1) if url_match else None

    reverse_split_confirmed = any(
        kw in message.lower()
        for kw in [
            "reverse stock split",
            "1-for-",
            "effective date of reverse stock split",
            "authority to implement a reverse stock split",
        ]
    )

    ticker_match = re.search(r"\((?:NASDAQ|OTC):\s*([A-Z]+)\)", message)
    ticker = ticker_match.group(1) if ticker_match else None

    if not ticker:
        inline_match = re.search(r"\b([A-Z]{2,6})\b", message)
        if inline_match:
            ticker = inline_match.group(1)

    return {
        "ticker": ticker,
        "url": url,
        "reverse_split_confirmed": reverse_split_confirmed,
    }


async def handle_secondary_channel(bot, message) -> None:
    """Entry point for secondary channel processing."""

    logger.info(f"Received message on secondary channel: {message.content}")

    result = alert_channel_message(message.content)
    logger.info(f"Alert parser result: {result}")

    if (
        not result
        or not isinstance(result, dict)
        or not result.get("reverse_split_confirmed")
    ):
        logger.warning("Message does not confirm reverse split or result malformed.")
        return

    alert_ticker = result.get("ticker")
    alert_url = result.get("url")

    if not alert_url or not alert_ticker:
        logger.error("Missing ticker or URL in parsed alert.")
        return

    try:
        logger.info(f"Calling OnMessagePolicyResolver.full_analysis for {alert_url}")
        policy_info = OnMessagePolicyResolver.full_analysis(alert_url)

        if not policy_info:
            logger.info("Falling back to press release analysis")
            policy_info = analyze_press_release(alert_url)
            if not policy_info:
                logger.warning(f"No data returned for {alert_ticker}.")
                return

        summary = build_policy_summary(alert_ticker, policy_info, alert_url)
        await post_policy_summary(bot, alert_ticker, summary)

        if policy_info.get("round_up_confirmed"):
            logger.info(f"Round-up confirmed for {alert_ticker}. Scheduling autobuy...")
            await attempt_autobuy(bot, message.channel, alert_ticker, quantity=1)

    except Exception as e:  # pragma: no cover - log unexpected failures
        logger.error(f"Exception during policy analysis for {alert_ticker}: {e}")


def analyze_press_release(url: str) -> Optional[Dict[str, str]]:
    """Return basic policy info from a press release URL.

    Attempts to fetch the article text and extract the fractional share
    policy and effective date. Returns a dictionary compatible with
    :func:`build_policy_summary` or ``None`` if processing fails.
    """

    try:
        body_text = OnMessagePolicyResolver.resolver.fetch_body_text(url)
        if not body_text:
            return None

        policy = OnMessagePolicyResolver.resolver.analyze_fractional_share_policy(
            body_text
        )
        effective_date = OnMessagePolicyResolver.resolver.extract_effective_date(
            body_text
        )
        snippet = OnMessagePolicyResolver.resolver.extract_round_up_snippet(body_text)
        return {
            "press_url": url,
            "policy": policy,
            "effective_date": effective_date,
            "body_text": body_text,
            "round_up_confirmed": bool(
                isinstance(policy, str) and "rounded up" in policy.lower()
            ),
            "snippet": snippet,
        }
    except Exception as exc:  # pragma: no cover - log unexpected failures
        logger.error(f"Press release analysis failed for {url}: {exc}")
        return None

