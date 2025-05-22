# utils/on_message_utils.py

import re
import requests
from bs4 import BeautifulSoup
from utils.sec_policy_fetcher import SECPolicyFetcher

import asyncio
from datetime import datetime, timedelta
from utils.logging_setup import logger
from utils.parsing_utils import (
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
            "1-for-",  # e.g., "1-for-15"
            "effective date of reverse stock split",
            "authority to implement a reverse stock split",
        ]
    )

    # Primary ticker pattern: (NASDAQ: TICKER)
    ticker_match = re.search(r"\((?:NASDAQ|OTC):\s*([A-Z]+)\)", message)
    ticker = ticker_match.group(1) if ticker_match else None

    # Secondary fallback: Try inline all-caps ticker (1-6 chars)
    if not ticker:
        inline_match = re.search(r"\b([A-Z]{2,6})\b", message)
        if inline_match:
            ticker = inline_match.group(1)

    return {
        "ticker": ticker,
        "url": url,
        "reverse_split_confirmed": reverse_split_confirmed,
    }


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


async def attempt_autobuy(bot, channel, ticker, quantity=1):
    """attempts autobuy immediately or schedules at next market open."""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, microsecond=0)

    if now.weekday() >= 5:
        logger.warning("weekend detected. scheduling for next monday 9:30am.")
        days_until_monday = (7 - now.weekday()) % 7 or 7
        execution_time = (now + timedelta(days=days_until_monday)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
    elif market_open <= now <= market_close:
        logger.info("market open now. executing immediate autobuy.")
        execution_time = now
    else:
        logger.info("market closed. scheduling for next market open.")
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

    confirmation = f"✅ autobuy for `{ticker}` scheduled at {execution_time.strftime('%y-%m-%d %h:%m:%s')}."
    logger.info(confirmation)
    await channel.send(confirmation)


def build_policy_summary(ticker, policy_info, fallback_url):
    """builds the policy summary message for discord posting."""
    summary = f"**reverse split alert** for `{ticker}`\n"
    summary += f"[nasdaq notice]({policy_info.get('nasdaq_url', fallback_url)})\n"

    if "press_url" in policy_info:
        summary += f"[press release]({policy_info['press_url']})\n"
    if "sec_url" in policy_info:
        summary += f"[sec filing]({policy_info['sec_url']})\n"

    policy_text = policy_info.get("sec_policy") or policy_info.get("policy")
    context_snippet = policy_info.get("sec_context")

    summary += f"🧾 **fractional share policy:** {policy_text}"

    if context_snippet:
        summary += f"\n\n📄 **context snippet:**\n> {context_snippet.strip()}"

    return summary


async def post_policy_summary(bot, ticker, summary):
    """posts the policy summary to the primary channel."""
    channel = bot.get_channel(discord_primary_channel)
    if channel:
        await channel.send(summary)
        logger.info(f"policy summary posted successfully for {ticker}.")
    else:
        logger.error("primary channel not found to post summary.")


# -------------------------
# onmessagepolicyresolver
# -------------------------


class onmessagepolicyresolver:
    nasdaq_keywords = [
        "cash in lieu",
        "no fractional shares",
        "rounded up",
        "not issuing fractional shares",
    ]

    sec_keywords = [
        "cash in lieu",
        "rounded up",
        "rounded down",
        "fractional shares will not be issued",
        "paid in cash",
    ]

    sec_fetcher = secpolicyfetcher()

    @classmethod
    def full_analysis(cls, nasdaq_url):
        try:
            logger.info(f"starting full_analysis for: {nasdaq_url}")
            ticker = cls.extract_ticker_from_url(nasdaq_url)
            nasdaq_result = cls.analyze_nasdaq_notice(nasdaq_url, ticker=ticker)

            if not nasdaq_result:
                logger.warning("nasdaq notice analysis failed or returned no result.")
                return none

            if nasdaq_result.get("sec_url"):
                sec_result = cls.analyze_sec_filing(nasdaq_result["sec_url"])
                nasdaq_result.update(sec_result)

            if not nasdaq_result.get("sec_policy") or nasdaq_result["sec_policy"] in [
                "unable to retrieve sec filing.",
                "no text content available.",
                "policy not clearly stated.",
            ]:
                press_url = nasdaq_result.get("press_url")
                if press_url:
                    logger.info(
                        f"attempting fallback analysis using press release at {press_url}"
                    )
                    press_text = cls.fetch_sec_filing_text(press_url)
                    if press_text:
                        press_policy = cls.analyze_fractional_share_policy(press_text)
                        nasdaq_result["sec_policy"] = press_policy
                        logger.info(f"press release analysis result: {press_policy}")

                        # 🚨 immediately update round-up confirmed from pr
                        nasdaq_result["round_up_confirmed"] = cls.is_round_up_policy(
                            press_policy
                        )
                        logger.info(
                            f"round-up confirmed after press release analysis: {nasdaq_result['round_up_confirmed']}"
                        )
                    else:
                        logger.warning(
                            "failed to fetch press release text for fallback policy analysis."
                        )

            # final fallback, if still no round_up_confirmed
            if "round_up_confirmed" not in nasdaq_result:
                policy_text = nasdaq_result.get("sec_policy") or nasdaq_result.get(
                    "policy"
                )
                nasdaq_result["round_up_confirmed"] = cls.is_round_up_policy(
                    policy_text
                )
                logger.info(
                    f"final round-up detection result: {nasdaq_result['round_up_confirmed']}"
                )

            logger.info(f"completed full_analysis for: {nasdaq_url}")
            return nasdaq_result

        except exception as e:
            logger.error(f"critical failure during full_analysis: {e}")
            return none

    @staticmethod
    def extract_ticker_from_url(url):
        match = re.search(r"\((.*?)\)", url)
        if match:
            return match.group(1)
        return none

    @classmethod
    def analyze_nasdaq_notice(cls, nasdaq_url, ticker=none):
        try:
            logger.info(f"analyzing nasdaq notice at {nasdaq_url}")
            headers = {
                "user-agent": "mozilla/5.0 (windows nt 10.0; win64; x64) applewebkit/537.36 (khtml, like gecko) chrome/112.0.0.0 safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()

            text = response.text.lower()
            policy = cls.detect_policy_from_text(text, cls.nasdaq_keywords)
            sec_url = cls.get_sec_link_from_nasdaq(nasdaq_url, ticker=ticker)
            press_url = cls.get_press_release_link_from_nasdaq(response.text)

            return {
                "policy": policy,
                "nasdaq_url": nasdaq_url,
                "sec_url": sec_url,
                "press_url": press_url,
            }
        except exception as e:
            logger.error(f"error analyzing nasdaq notice: {e}")
            return none

    @classmethod
    def analyze_sec_filing(cls, sec_url):
        try:
            logger.info(f"analyzing sec filing at {sec_url}")
            filing_text = cls.fetch_sec_filing_text(sec_url)
            if filing_text:
                result = cls.analyze_fractional_share_policy(filing_text)
                sec_policy = result["summary"]
                sec_context = result["context"]

                return {
                    "sec_policy": sec_policy,
                    "sec_url": sec_url,
                    "sec_context": sec_context,
                }
            else:
                return {
                    "sec_policy": "unable to retrieve sec filing.",
                    "sec_url": sec_url,
                }
        except exception as e:
            logger.error(f"failed to retrieve or analyze sec filing: {e}")
            return {
                "sec_policy": "unable to retrieve sec filing.",
                "sec_url": sec_url,
            }

    @staticmethod
    def get_sec_link_from_nasdaq(nasdaq_url, ticker=none):
        """
        parses a nasdaq alert page and extracts a valid sec filing url.
        now also supports quotemedia-based sec filings.
        """
        try:
            headers = {
                "user-agent": "mozilla/5.0 (windows nt 10.0; win64; x64) applewebkit/537.36 (khtml, like gecko) chrome/112.0.0.0 safari/537.36"
            }
            response = requests.get(nasdaq_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = beautifulsoup(response.text, "html.parser")

            links = soup.find_all("a", href=true)
            sec_links = []

            for link in links:
                href = link["href"]
                # handle sec.gov and quotemedia-based filings
                if "sec.gov" in href or "quotemedia.com/data/downloadfiling" in href:
                    if "/rules/sro/" in href:
                        logger.info(f"skipping rules/sro link: {href}")
                        continue
                    if ticker and ticker.lower() in href.lower():
                        sec_links.append(href)
                    elif re.search(r"/20\d{2}/", href) or "formtype=" in href:
                        sec_links.append(href)

            if sec_links:
                logger.info(f"sec filing link selected: {sec_links[0]}")
                return sec_links[0]

            logger.warning("no valid sec or quotemedia filing link after filtering.")
            return none

        except exception as e:
            logger.error(f"failed to retrieve sec link from nasdaq: {e}")
            return none

    @staticmethod
    def get_press_release_link_from_nasdaq(html_text):
        try:
            soup = beautifulsoup(html_text, "html.parser")
            link = soup.find("a", string="press release")
            if link and link.get("href"):
                press_url = link["href"]
                if press_url.startswith("/"):
                    press_url = "https://www.nasdaqtrader.com" + press_url
                logger.info(f"press release link found: {press_url}")
                return press_url
            else:
                logger.warning("no press release link found on nasdaq page.")
                return none
        except exception as e:
            logger.error(f"error extracting press release link: {e}")
            return none

    @staticmethod
    def fetch_sec_filing_text(url):
        try:
            headers = {
                "user-agent": "mozilla/5.0 (windows nt 10.0; win64; x64) applewebkit/537.36 (khtml, like gecko) chrome/112.0.0.0 safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            if "html" in response.headers.get("content-type", ""):
                soup = beautifulsoup(response.text, "html.parser")
                text = soup.get_text(separator=" ")
            else:
                text = response.text

            text = " ".join(text.split())
            logger.info(f"fetched sec filing text ({len(text)} characters)")
            return text
        except exception as e:
            logger.error(f"error fetching sec filing text: {e}")
            return none

    @staticmethod
    def analyze_fractional_share_policy(text, window=300):
        """
        detects fractional share policy and returns a summary + contextual snippet.
        """
        if not text:
            return {"summary": "no text content available.", "context": none}

        text_lower = text.lower()

        # known policy patterns
        if "fractional share" not in text_lower:
            return {"summary": "no mention of fractional shares.", "context": none}

        # pick target phrases to extract context around
        match_phrases = [
            "no fractional shares will be issued",
            "cash in lieu",
            "rounded up",
            "rounded down",
            "entitled to receive an additional fraction",
            "cash will not be paid",
        ]

        # scan for any match
        for phrase in match_phrases:
            idx = text_lower.find(phrase)
            if idx != -1:
                start = max(0, idx - window // 2)
                end = min(len(text), idx + window // 2)
                snippet = text[start:end].strip().replace("\n", " ")

                # classify
                if "cash in lieu" in phrase or "paid in cash" in phrase:
                    summary = "fractional shares will be paid out in cash."
                elif (
                    "rounded up" in phrase
                    or "entitled to receive an additional fraction" in phrase
                ):
                    summary = "fractional shares will be rounded up to a full share."
                elif "rounded down" in phrase:
                    summary = (
                        "fractional shares will be rounded down (likely forfeited)."
                    )
                elif "no fractional shares" in phrase:
                    summary = "fractional shares will not be issued."
                else:
                    summary = "fractional share policy mentioned, but unclear details."

                return {"summary": summary, "context": snippet}

        return {
            "summary": "fractional share handling mentioned, but unclear policy.",
            "context": none,
        }

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for keyword in keywords:
            if keyword in text:
                logger.info(f"detected policy keyword: {keyword}")
                return keyword.capitalize()
        logger.warning("no specific policy keywords detected.")
        return "policy not clearly stated."

    @staticmethod
    def is_round_up_policy(text):
        if not text:
            return false

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
