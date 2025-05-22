import re
import logging

logger = logging.getLogger(__name__)

def alert_channel_message(message: str):
    """
    Parses secondary channel messages to detect reverse split announcements and extract key info.
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


async def handle_secondary_channel(bot, message):
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
            logger.warning(f"No data returned for {alert_ticker}.")
            return

        summary = build_policy_summary(alert_ticker, policy_info, alert_url)
        await post_policy_summary(bot, alert_ticker, summary)

        if policy_info.get("round_up_confirmed"):
            logger.info(f"Round-up confirmed for {alert_ticker}. Scheduling autobuy...")
            await attempt_autobuy(bot, message.channel, alert_ticker, quantity=1)

    except Exception as e:
        logger.error(f"Exception during policy analysis for {alert_ticker}: {e}")