"""Discord message handlers used by RSAssistant."""

import re
from datetime import datetime, timedelta
import requests

from utils.logging_setup import logger
from utils.parsing_utils import (
    alert_channel_message,
    parse_embed_message,
    parse_order_message,
)
from utils.csv_utils import save_holdings_to_csv
from utils.watch_utils import (
    parse_bulk_watchlist_message,
    add_entries_from_message,
    account_mapping,
)
from utils.update_utils import update_and_restart, revert_and_restart
from utils.order_exec import schedule_and_execute
from utils import split_watch_utils

from bs4 import BeautifulSoup
from utils.policy_resolver import SplitPolicyResolver as PolicyResolver

DISCORD_PRIMARY_CHANNEL = None
DISCORD_SECONDARY_CHANNEL = None
DISCORD_AI_CHANNEL = None


def set_channels(primary_id, secondary_id, tertiary_id):
    """Sets primary and secondary channel IDs for use in on_message handling."""
    global DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_AI_CHANNEL
    DISCORD_PRIMARY_CHANNEL = primary_id
    DISCORD_SECONDARY_CHANNEL = secondary_id
    DISCORD_AI_CHANNEL = tertiary_id
    logger.info(
        f"on_message_utils loaded with primary={primary_id}, secondary={secondary_id}, tertiary={tertiary_id}"
    )


def get_account_nickname_or_default(broker_name, group_number, account_number):
    try:
        broker_accounts = account_mapping.get(broker_name, {})
        group_accounts = broker_accounts.get(str(group_number), {})

        if not isinstance(group_accounts, dict):
            logger.error(
                f"Expected dict for group {group_number} in {broker_name}, got {type(group_accounts)}"
            )
            return f"{broker_name} {group_number} {account_number}"

        return group_accounts.get(
            str(account_number), f"{broker_name} {group_number} {account_number}"
        )
    except Exception as e:
        logger.error(
            f"Error retrieving nickname for {broker_name} {group_number} {account_number}: {e}"
        )
        return f"{broker_name} {group_number} {account_number}"


async def handle_on_message(bot, message):
    logger.info(f"Received message: {message}")
    """Main on_message event handler.

    Routes messages to the appropriate handler based on channel ID.
    """
    if message.channel.id == DISCORD_PRIMARY_CHANNEL:
        await handle_primary_channel(bot, message)
    elif message.channel.id == DISCORD_SECONDARY_CHANNEL:
        await handle_secondary_channel(bot, message)


async def handle_primary_channel(bot, message):
    """Process messages received in the primary channel.

    Embed messages are treated as holdings updates and persisted to the
    holdings CSV log. All other messages are routed to order parsing or
    maintenance commands.
    """

    if message.content.lower().startswith("manual"):
        logger.warning(f"Manual order detected: {message.content}")

    elif message.embeds:
        logger.info("Embed message detected.")
        try:
            embeds = message.embeds
            parsed_holdings = parse_embed_message(embeds)

            if not parsed_holdings:
                logger.error("Failed to parse embedded holdings")
                return

            for holding in parsed_holdings:
                holding[
                    "Key"
                ] = f"{holding['broker']}_{holding['group']}_{holding['account']}_{holding['ticker']}"

            save_holdings_to_csv(parsed_holdings)
        except Exception as e:
            logger.error(f"Error parsing embed message: {e}")
    else:
        logger.info("Parsing regular order message.")
        lowered = message.content.lower().strip()
        if lowered == "..updatebot":
            await message.channel.send("Pulling latest code and restarting...")
            update_and_restart()
            return
        if lowered == "..revertupdate":
            await message.channel.send("Reverting last update and restarting...")
            revert_and_restart()
            return

        entries = parse_bulk_watchlist_message(message.content)
        if entries:
            ctx = await bot.get_context(message)
            count = await add_entries_from_message(message.content, ctx)
            await message.channel.send(f"Added {count} tickers to watchlist.")
            logger.info(f"Added {count} tickers from bulk watchlist message.")
            return
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

        body_text = policy_info.get("body_text")
        if body_text:
            prompt = (
                "..ai Will the fractional shares of this reverse split be rounded up "
                "to the nearest whole share or paid out cash in lieu? "
            )
            snippet = body_text[: 2000 - len(prompt)]
            logger.info(f"Appending body text to prompt {body_text}")
            await message.channel.send(prompt + snippet)

        if policy_info.get("round_up_confirmed"):
            logger.info(f"Round-up confirmed for {alert_ticker}. Scheduling autobuy...")
            await attempt_autobuy(bot, message.channel, alert_ticker, quantity=1)
            split_date = datetime.date.today().isoformat()
            ticker = result.get("ticker")
            if ticker:
                split_watch_utils.add_split_watch(ticker, split_date)
                logger.info(f"Added {ticker} to split watch with date {split_date}.")
        else:
            logger.info(
                f"No autobuy triggered for {alert_ticker}: round_up_confirmed=False."
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

    order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_buy"
    bot.loop.create_task(
        schedule_and_execute(
            ctx=channel,
            action="buy",
            ticker=ticker,
            quantity=quantity,
            broker="all",
            execution_time=execution_time,
            order_id=order_id,
        )
    )

    confirmation = f"✅ Autobuy for `{ticker}` scheduled at {execution_time.strftime('%Y-%m-%d %H:%M:%S')}."
    logger.info(confirmation)
    await channel.send(confirmation)


def build_policy_summary(ticker, policy_info, fallback_url):
    summary = f"**Reverse Split Alert** for `{ticker}`\n"
    summary += f"[NASDAQ Notice]({policy_info.get('nasdaq_url', fallback_url)})\n"

    if "press_url" in policy_info:
        summary += f"[Press Release]({policy_info['press_url']})\n"
    if "sec_url" in policy_info:
        summary += f"[SEC Filing]({policy_info['sec_url']})\n"

    policy_text = policy_info.get("sec_policy") or policy_info.get("policy")
    summary += f" **Fractional Share Policy:** {policy_text}"

    snippet = policy_info.get("snippet")
    if snippet:
        summary += f"\n> {snippet}"

    return summary


async def post_policy_summary(bot, ticker, summary):
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await channel.send(summary)
        logger.info(f"Policy summary posted successfully for {ticker}.")
    else:
        logger.error("Primary channel not found to post summary.")


# -------------------------
# SplitPolicyResolver
# -------------------------


class SplitPolicyResolver:
    BASE_URL = "https://efts.sec.gov/LATEST/search-index"
    HEADERS = {"User-Agent": "MyApp/1.0 (my.email@example.com)"}
    SEARCH_TERMS = [
        "reverse stock split",
        "no fractional shares",
        "reverse split",
        "in lieu",
        "preserve round lot",
    ]
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

    def __init__(self, back_days=30):
        self.start_date = (datetime.today() - timedelta(days=back_days)).strftime(
            "%Y-%m-%d"
        )
        self.end_date = datetime.today().strftime("%Y-%m-%d")

    def build_search_params(self, ticker):
        return {
            "q": f"{ticker} "
            + " OR ".join([f'"{term}"' for term in self.SEARCH_TERMS]),
            "dateRange": "custom",
            "startdt": self.start_date,
            "enddt": self.end_date,
            "category": "full",
            "start": 0,
            "count": 10,
        }

    def search_sec_filings(self, ticker):
        try:
            logger.info(
                f"Searching SEC filings for {ticker} from {self.start_date} to {self.end_date}"
            )
            params = self.build_search_params(ticker)
            response = requests.get(
                self.BASE_URL, params=params, headers=self.HEADERS, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching SEC search results: {e}")
            return None

    def extract_policy_from_sec_filing(self, filing_url):
        try:
            logger.info(f"Fetching and analyzing SEC filing from {filing_url}")
            response = requests.get(filing_url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text_content = soup.get_text(separator=" ")

            return {
                "round_up": self.is_round_up_policy(text_content),
                "cash_in_lieu": "cash in lieu" in text_content.lower(),
                # or "paid in cash" in text_content.lower(),
                # "round_down": "rounded down" in text_content.lower(),
            }
        except Exception as e:
            logger.error(f"Error analyzing SEC filing text: {e}")
            return None

    def fetch_sec_policy(self, ticker):
        search_data = self.search_sec_filings(ticker)
        if not search_data or "hits" not in search_data.get("hits", {}):
            logger.warning(f"No filings found for ticker {ticker}")
            return None

        filings = search_data["hits"]["hits"]
        for filing in filings:
            form_type = filing["_source"].get("form", "")
            if form_type in ["8-K", "S-1", "S-3", "S-4", "14A", "10-K", "10-Q"]:
                cik = filing["_source"].get("ciks", [""])[0]
                accession_number = filing["_source"].get("adsh", "")
                file_id = filing["_id"].split(":")[1]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number.replace('-', '')}/{file_id}"

                policy_info = self.extract_policy_from_sec_filing(filing_url)
                if policy_info:
                    logger.info(f"Policy info extracted for {ticker}: {policy_info}")
                    return policy_info

        logger.warning(f"No valid policy extracted for {ticker}")
        return None

    @staticmethod
    def is_round_up_policy(text):
        """
        Determines if text confirms a round-up policy without disqualifying phrases.
        """
        if not text:
            return False

        text = text.lower()
        cash_indicators = ["cash in lieu", "paid in cash", "payment for fractional"]

        return (
            "rounded up" in text
            and all(term not in text for term in cash_indicators)
            and "fractional share" in text
        )

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for keyword in keywords:
            if keyword in text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()
        logger.warning("No specific policy keywords detected.")
        return "Policy not clearly stated."

    @staticmethod
    def fetch_text_from_url(url):
        try:
            headers = SplitPolicyResolver.HEADERS
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
    def extract_round_up_snippet(text, window=5):
        """Return a short excerpt around any round-up mention."""
        phrases = [
            "rounded up",
            "round up",
            "rounded to the nearest",
        ]
        for phrase in phrases:
            pattern = re.compile(
                rf"(?:\S+\s+){{0,{window}}}{re.escape(phrase)}(?:\s+\S+){{0,{window}}}",
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if match:
                return match.group(0).strip()
        return None

    @classmethod
    def analyze_text(cls, text_source, keywords=None):
        if not text_source:
            return None

        text = cls.fetch_text_from_url(text_source)
        if not text:
            return None

        policy = cls.detect_policy_from_text(text, keywords or cls.SEC_KEYWORDS)
        round_up = cls.is_round_up_policy(text)
        snippet = cls.extract_round_up_snippet(text)
        return {
            "policy": policy,
            "round_up_confirmed": bool(snippet) or round_up,
            "source_url": text_source,
            "snippet": snippet,
        }


# -------------------------
# OnMessagePolicyResolver
# -------------------------


class OnMessagePolicyResolver:
    """Wrapper around :class:`utils.policy_resolver.SplitPolicyResolver`."""

    resolver = PolicyResolver()

    @classmethod
    def full_analysis(cls, nasdaq_url):
        """Perform complete policy analysis for a NASDAQ notice URL."""
        try:
            logger.info(f"Starting full_analysis for: {nasdaq_url}")
            return cls.resolver.full_analysis(nasdaq_url)
        except Exception as e:
            logger.error(f"Critical failure during full_analysis: {e}")
            return None


# -------------------------
# SplitPolicyResolver
# -------------------------


class SplitPolicyResolver:
    BASE_URL = "https://efts.sec.gov/LATEST/search-index"
    HEADERS = {"User-Agent": "MyApp/1.0 (my.email@example.com)"}
    SEARCH_TERMS = [
        "reverse stock split",
        "no fractional shares",
        "reverse split",
        "in lieu",
        "preserve round lot",
    ]
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

    def __init__(self, back_days=30):
        self.start_date = (datetime.today() - timedelta(days=back_days)).strftime(
            "%Y-%m-%d"
        )
        self.end_date = datetime.today().strftime("%Y-%m-%d")

    def build_search_params(self, ticker):
        return {
            "q": f"{ticker} "
            + " OR ".join([f'"{term}"' for term in self.SEARCH_TERMS]),
            "dateRange": "custom",
            "startdt": self.start_date,
            "enddt": self.end_date,
            "category": "full",
            "start": 0,
            "count": 10,
        }

    def search_sec_filings(self, ticker):
        try:
            logger.info(
                f"Searching SEC filings for {ticker} from {self.start_date} to {self.end_date}"
            )
            params = self.build_search_params(ticker)
            response = requests.get(
                self.BASE_URL, params=params, headers=self.HEADERS, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching SEC search results: {e}")
            return None

    def extract_policy_from_sec_filing(self, filing_url):
        try:
            logger.info(f"Fetching and analyzing SEC filing from {filing_url}")
            response = requests.get(filing_url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text_content = soup.get_text(separator=" ")

            return {
                "round_up": self.is_round_up_policy(text_content),
                "cash_in_lieu": "cash in lieu" in text_content.lower()
                or "paid in cash" in text_content.lower(),
                "round_down": "rounded down" in text_content.lower(),
            }
        except Exception as e:
            logger.error(f"Error analyzing SEC filing text: {e}")
            return None

    def fetch_sec_policy(self, ticker):
        search_data = self.search_sec_filings(ticker)
        if not search_data or "hits" not in search_data.get("hits", {}):
            logger.warning(f"No filings found for ticker {ticker}")
            return None

        filings = search_data["hits"]["hits"]
        for filing in filings:
            form_type = filing["_source"].get("form", "")
            if form_type in ["8-K", "S-1", "S-3", "S-4", "14A", "10-K", "10-Q"]:
                cik = filing["_source"].get("ciks", [""])[0]
                accession_number = filing["_source"].get("adsh", "")
                file_id = filing["_id"].split(":")[1]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number.replace('-', '')}/{file_id}"

                policy_info = self.extract_policy_from_sec_filing(filing_url)
                if policy_info:
                    logger.info(f"Policy info extracted for {ticker}: {policy_info}")
                    return policy_info

        logger.warning(f"No valid policy extracted for {ticker}")
        return None

    @staticmethod
    def is_round_up_policy(text):
        """
        Determines if text confirms a round-up policy without disqualifying phrases.
        """
        if not text:
            return False

        text = text.lower()
        cash_indicators = ["cash in lieu", "paid in cash", "payment for fractional"]

        return (
            "rounded up" in text
            and all(term not in text for term in cash_indicators)
            and "fractional share" in text
        )

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for keyword in keywords:
            if keyword in text:
                logger.info(f"Detected policy keyword: {keyword}")
                return keyword.capitalize()
        logger.warning("No specific policy keywords detected.")
        return "Policy not clearly stated."

    @staticmethod
    def fetch_text_from_url(url):
        try:
            headers = SplitPolicyResolver.HEADERS
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            if "html" in response.headers.get("Content-Type", ""):
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(separator=" ")
            else:
                text = response.text

            text = " ".join(text.split())
            with open("./Policy_Info.txt", "w", encoding="utf-8") as f:
                f.write(text)
                logger.info("Saved SEC filing text to ./Policy_Info.txt")
            logger.info(f"Fetched SEC filing text ({len(text)} characters)")
            return text
        except Exception as e:
            logger.error(f"Error fetching SEC filing text: {e}")
            return None

    @classmethod
    def analyze_text(cls, text_source, keywords=None):
        if not text_source:
            return None

        text = cls.fetch_text_from_url(text_source)
        if not text:
            return None

        policy = cls.detect_policy_from_text(text, keywords or cls.SEC_KEYWORDS)
        round_up = cls.is_round_up_policy(text)
        snippet = cls.extract_round_up_snippet(text)
        return {
            "policy": policy,
            "round_up_confirmed": bool(snippet) or round_up,
            "source_url": text_source,
            "snippet": snippet,
        }
