# utils/on_message_utils.py

import re
import asyncio
from datetime import datetime, timedelta
import requests

from utils.logging_setup import logger
from utils.parsing_utils import (
    alert_channel_message,
    parse_embed_message,
    parse_order_message,
)
from utils.order_exec import schedule_and_execute

from discord import Embed

DISCORD_PRIMARY_CHANNEL = None
DISCORD_SECONDARY_CHANNEL = None


def set_channels(primary_id, secondary_id):
    """Sets primary and secondary channel IDs for use in on_message handling."""
    global DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL
    DISCORD_PRIMARY_CHANNEL = primary_id
    DISCORD_SECONDARY_CHANNEL = secondary_id
    logger.info(
        f"on_message_utils loaded with primary={primary_id}, secondary={secondary_id}"
    )


async def handle_on_message(bot, message):
    """Main on_message event handler."""
    if message.channel.id == DISCORD_PRIMARY_CHANNEL:
        await handle_primary_channel(bot, message)
    elif message.channel.id == DISCORD_SECONDARY_CHANNEL:
        await handle_secondary_channel(bot, message)
    else:
        await bot.process_commands(message)


async def handle_primary_channel(bot, message):
    """Handles messages in the primary channel."""
    if message.content.lower().startswith("manual"):
        logger.warning(f"Manual order detected: {message.content}")
        # manual_order(message.content)  # Future expansion
    elif message.embeds:
        logger.info("Embed message detected.")
        parse_embed_message(message.embeds[0])
    else:
        logger.info("Parsing regular order message.")
        parse_order_message(message.content)


async def handle_secondary_channel(bot, message):
    logger.info(f"Received message on secondary channel: {message.content}")

    result = alert_channel_message(message.content)
    logger.info(f"Alert parser result: {result}")

    if not result or not result.get("reverse_split_confirmed"):
        logger.warning("Message does not confirm reverse split.")
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
            logger.info(
                f"✅ Round-up confirmed for {alert_ticker}. Scheduling autobuy..."
            )
            channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
            if channel:
                await attempt_autobuy(bot, channel, alert_ticker, quantity=1)
        else:
            logger.info(
                f"⛔ No autobuy triggered for {alert_ticker}: round_up_confirmed=False."
            )

    except Exception as e:
        logger.error(f"Exception during policy analysis for {alert_ticker}: {e}")


async def attempt_autobuy(bot, channel, ticker, quantity=1):
    """Attempts autobuy immediately or schedules at next market open."""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, microsecond=0)

    if now.weekday() >= 5:
        logger.warning("Weekend detected. Scheduling for next Monday 9:30AM.")
        days_until_monday = (7 - now.weekday()) % 7 or 7
        execution_time = (now + timedelta(days=days_until_monday)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    elif market_open <= now <= market_close:
        logger.info("Market open now. Executing immediate autobuy.")
        execution_time = now
    else:
        logger.info("Market closed. Scheduling for next market open.")
        execution_time = (now + timedelta(days=1)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )

    await schedule_and_execute(
        ctx=channel,
        action="buy",
        ticker=ticker,
        quantity=quantity,
        broker="all",
        execution_time=execution_time,
    )

    confirmation = f"✅ Autobuy for `{ticker}` scheduled at {execution_time.strftime('%Y-%m-%d %H:%M:%S')}."
    logger.info(confirmation)
    await channel.send(confirmation)


def build_policy_summary(ticker, policy_info, fallback_url):
    """Builds the policy summary message for Discord posting."""
    summary = f"**Reverse Split Alert** for `{ticker}`\n"
    summary += f"[NASDAQ Notice]({policy_info.get('nasdaq_url', fallback_url)})\n"

    if "press_url" in policy_info:
        summary += f"[Press Release]({policy_info['press_url']})\n"
    if "sec_url" in policy_info:
        summary += f"[SEC Filing]({policy_info['sec_url']})\n"

    policy_text = policy_info.get("sec_policy") or policy_info.get("policy")
    summary += f"🧾 **Fractional Share Policy:** {policy_text}"

    return summary


async def post_policy_summary(bot, ticker, summary):
    """Posts the policy summary to the primary channel."""
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await channel.send(summary)
        logger.info(f"Policy summary posted successfully for {ticker}.")
    else:
        logger.error("Primary channel not found to post summary.")


# -------------------------
# OnMessagePolicyResolver
# -------------------------


import re
import requests
from bs4 import BeautifulSoup
from utils.logging_setup import logger
from utils.sec_policy_fetcher import SECPolicyFetcher


class OnMessagePolicyResolver:
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

    sec_fetcher = SECPolicyFetcher()

    @classmethod
    def full_analysis(cls, nasdaq_url):
        try:
            logger.info(f"Starting full_analysis for: {nasdaq_url}")
            ticker = cls.extract_ticker_from_url(nasdaq_url)
            nasdaq_result = cls.analyze_nasdaq_notice(nasdaq_url, ticker=ticker)

            if not nasdaq_result:
                logger.warning("NASDAQ notice analysis failed or returned no result.")
                return None

            if nasdaq_result.get("sec_url"):
                sec_result = cls.analyze_sec_filing(nasdaq_result["sec_url"])
                nasdaq_result.update(sec_result)

            if not nasdaq_result.get("sec_policy") or nasdaq_result["sec_policy"] in [
                "Unable to retrieve SEC filing.",
                "No text content available.",
                "Policy not clearly stated.",
            ]:
                press_url = nasdaq_result.get("press_url")
                if press_url:
                    logger.info(
                        f"Attempting fallback analysis using Press Release at {press_url}"
                    )
                    press_text = cls.fetch_sec_filing_text(press_url)
                    if press_text:
                        press_policy = cls.analyze_fractional_share_policy(press_text)
                        nasdaq_result["sec_policy"] = press_policy
                        logger.info(f"Press Release analysis result: {press_policy}")

                        # 🚨 Immediately update round-up confirmed from PR
                        nasdaq_result["round_up_confirmed"] = cls.is_round_up_policy(
                            press_policy
                        )
                        logger.info(
                            f"Round-up confirmed after press release analysis: {nasdaq_result['round_up_confirmed']}"
                        )
                    else:
                        logger.warning(
                            "Failed to fetch Press Release text for fallback policy analysis."
                        )

            # FINAL fallback, if still no round_up_confirmed
            if "round_up_confirmed" not in nasdaq_result:
                policy_text = nasdaq_result.get("sec_policy") or nasdaq_result.get(
                    "policy"
                )
                nasdaq_result["round_up_confirmed"] = cls.is_round_up_policy(
                    policy_text
                )
                logger.info(
                    f"Final round-up detection result: {nasdaq_result['round_up_confirmed']}"
                )

            logger.info(f"Completed full_analysis for: {nasdaq_url}")
            return nasdaq_result

        except Exception as e:
            logger.error(f"Critical failure during full_analysis: {e}")
            return None

    @staticmethod
    def extract_ticker_from_url(url):
        match = re.search(r"\((.*?)\)", url)
        if match:
            return match.group(1)
        return None

    @classmethod
    def analyze_nasdaq_notice(cls, nasdaq_url, ticker=None):
        try:
            logger.info(f"Analyzing NASDAQ notice at {nasdaq_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()

            text = response.text.lower()
            policy = cls.detect_policy_from_text(text, cls.NASDAQ_KEYWORDS)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url, ticker=ticker)
            press_url = cls.get_press_release_link_from_nasdaq(response.text)

            return {
                "policy": policy,
                "nasdaq_url": nasdaq_url,
                "sec_url": sec_url,
                "press_url": press_url,
            }
        except Exception as e:
            logger.error(f"Error analyzing NASDAQ notice: {e}")
            return None

    @classmethod
    def analyze_sec_filing(cls, sec_url):
        try:
            logger.info(f"Analyzing SEC filing at {sec_url}")
            filing_text = cls.fetch_sec_filing_text(sec_url)
            if filing_text:
                sec_policy = cls.analyze_fractional_share_policy(filing_text)
                return {
                    "sec_policy": sec_policy,
                    "sec_url": sec_url,
                }
            else:
                return {
                    "sec_policy": "Unable to retrieve SEC filing.",
                    "sec_url": sec_url,
                }
        except Exception as e:
            logger.error(f"Failed to retrieve or analyze SEC filing: {e}")
            return {
                "sec_policy": "Unable to retrieve SEC filing.",
                "sec_url": sec_url,
            }

    @staticmethod
    def get_sec_link_from_nasdaq(nasdaq_url, ticker=None):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            links = [
                link["href"]
                for link in soup.find_all("a", href=True)
                if "sec.gov" in link["href"]
            ]

            if not links:
                logger.warning("No SEC Filing links found on NASDAQ page.")
                return None

            # Filter SEC links
            filtered_links = []
            for link in links:
                if "/rules/sro/" in link:
                    logger.info(f"Skipping rules/sro link: {link}")
                    continue
                if ticker and ticker.lower() in link.lower():
                    filtered_links.append(link)
                elif re.search(r"/20\d{2}/", link):
                    filtered_links.append(link)

            if filtered_links:
                logger.info(f"SEC Filing link selected: {filtered_links[0]}")
                return filtered_links[0]

            logger.warning("No valid SEC Filing link after filtering.")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve SEC link from NASDAQ: {e}")
            return None

    @staticmethod
    def get_press_release_link_from_nasdaq(html_text):
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            link = soup.find("a", string="Press Release")
            if link and link.get("href"):
                press_url = link["href"]
                if press_url.startswith("/"):
                    press_url = "https://www.nasdaqtrader.com" + press_url
                logger.info(f"Press Release link found: {press_url}")
                return press_url
            else:
                logger.warning("No Press Release link found on NASDAQ page.")
                return None
        except Exception as e:
            logger.error(f"Error extracting Press Release link: {e}")
            return None

    @staticmethod
    def fetch_sec_filing_text(url):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            if "html" in response.headers.get("Content-Type", ""):
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(separator=" ")
            else:
                text = response.text

            text = " ".join(text.split())
            logger.info(f"Fetched SEC filing text ({len(text)} characters)")
            return text
        except Exception as e:
            logger.error(f"Error fetching SEC filing text: {e}")
            return None

    @staticmethod
    def analyze_fractional_share_policy(text):
        if not text:
            return "No text content available."

        text_lower = text.lower()

        if "fractional share" not in text_lower:
            return "No mention of fractional shares."

        if "cash in lieu" in text_lower or "paid in cash" in text_lower:
            return "Fractional shares will be paid out in cash."

        if "rounded up" in text_lower and not (
            "cash" in text_lower or "cash in lieu" in text_lower
        ):
            return "Fractional shares will be rounded up to a full share."

        if "rounded down" in text_lower:
            return "Fractional shares will be rounded down (likely forfeited)."

        return "Fractional share handling mentioned, but unclear policy."

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for keyword in keywords:
            if keyword in text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()
        logger.warning("No specific policy keywords detected.")
        return "Policy not clearly stated."

    @staticmethod
    def is_round_up_policy(text):
        if not text:
            return False

        text = text.lower()
        return ("round up" in text or "rounded up" in text) and not any(
            bad in text
            for bad in [
                "sold",
                "aggregated",
                "not issued",
                "round down",
                "no fractional",
            ]
        )
