"""Discord message handlers used by RSAssistant."""

import re
import asyncio
from datetime import datetime, timedelta, date
from collections import defaultdict
import requests

from utils.logging_setup import logger
from utils.config_utils import BOT_PREFIX
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
    watch_list_manager,
)
from utils.update_utils import update_and_restart, revert_and_restart
from utils.order_exec import schedule_and_execute
from utils.monitor_utils import has_acted_today, record_action_today
from utils.config_utils import (
    AUTO_SELL_LIVE,
    HOLDING_ALERT_MIN_PRICE,
    IGNORE_TICKERS as IGNORE_TICKERS_SET,
    DISCORD_PRIMARY_CHANNEL as PRIMARY_CHAN_ID,
    MENTION_USER_ID,
    MENTION_ON_ALERTS,
)
from utils import split_watch_utils

from bs4 import BeautifulSoup
from utils.policy_resolver import SplitPolicyResolver as PolicyResolver

DISCORD_PRIMARY_CHANNEL = None
DISCORD_SECONDARY_CHANNEL = None
DISCORD_TERTIARY_CHANNEL = None

# Flag indicating the '..all' command is auditing watchlist holdings
_audit_active = False
# Accumulates missing tickers per account during an audit
_missing_summary = defaultdict(set)


def enable_audit():
    """Activate watchlist auditing for the '..all' command."""
    global _audit_active, _missing_summary
    _audit_active = True
    _missing_summary = defaultdict(set)


def disable_audit():
    """Deactivate auditing mode."""
    global _audit_active
    _audit_active = False


def get_audit_summary():
    """Return accumulated missing tickers per account."""
    return {k: sorted(v) for k, v in _missing_summary.items()}


def compute_account_missing_tickers(parsed_holdings):
    """Return missing watchlist tickers per account from parsed holdings."""
    watchlist = {t.upper() for t in watch_list_manager.get_watch_list().keys()}
    account_holdings = defaultdict(set)
    for h in parsed_holdings:
        key = f"{h['broker']} {h['account_name']} ({h['account']})"
        account_holdings[key].add(h["ticker"].upper())
    results = {}
    for account, held in account_holdings.items():
        missing = watchlist - held
        if missing:
            results[account] = sorted(missing)
    return results


async def _audit_holdings(message, parsed_holdings):
    missing = compute_account_missing_tickers(parsed_holdings)
    for account, tickers in missing.items():
        _missing_summary[account].update(tickers)
        await message.channel.send(f"Missing in {account}: {', '.join(tickers)}")


def set_channels(primary_id, secondary_id, tertiary_id):
    global DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_TERTIARY_CHANNEL
    DISCORD_PRIMARY_CHANNEL = primary_id
    DISCORD_SECONDARY_CHANNEL = secondary_id
    DISCORD_TERTIARY_CHANNEL = tertiary_id
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

    if message.content.startswith(BOT_PREFIX):
        logger.warning("Detected message with command prefix: {BOT_PREFIX}")
        return
    elif message.embeds:
        logger.info("Embed message detected.")
        try:
            embeds = message.embeds
            parsed_holdings = parse_embed_message(embeds)

            if not parsed_holdings:
                logger.error("Failed to parse embedded holdings")
                return

            for holding in parsed_holdings:
                holding["Key"] = (
                    f"{holding['broker']}_{holding['group']}_{holding['account']}_{holding['ticker']}"
                )

            save_holdings_to_csv(parsed_holdings)

            # After saving, optionally alert and auto-sell tickers over threshold
            try:
                threshold = float(HOLDING_ALERT_MIN_PRICE)
            except Exception:
                threshold = 1.0

            for h in parsed_holdings:
                try:
                    ticker = str(h.get("ticker", "")).upper()
                    if not ticker or ticker == "CASH AND SWEEP FUNDS":
                        continue
                    if ticker in IGNORE_TICKERS_SET:
                        continue
                    price = float(h.get("price", 0) or 0)
                    quantity = float(h.get("quantity", 0) or 0)
                    broker = str(h.get("broker", "")).strip()
                    account_name = str(h.get("account_name", h.get("account", "")))
                    if price < threshold or quantity <= 0:
                        continue
                    if has_acted_today(broker, account_name, ticker):
                        continue

                    mention = f"<@{MENTION_USER_ID}> " if (MENTION_ON_ALERTS and MENTION_USER_ID) else ""
                    note = (
                        f"{mention}Detected holding >= ${threshold:.2f}: {ticker} @ ${price:.2f} "
                        f"in {broker} {account_name} (qty {quantity})."
                    )
                    await message.channel.send(note)

                    if AUTO_SELL_LIVE:
                        # Use '..ord' so scheduling logic (market hours) is respected
                        sell_cmd = f"{BOT_PREFIX}ord sell {ticker} {broker} {quantity}"
                        await message.channel.send(sell_cmd)
                    record_action_today(broker, account_name, ticker)
                except Exception as exc:
                    logger.error(f"Monitor/auto-sell step failed for holding {h}: {exc}")
            if _audit_active:
                await _audit_holdings(message, parsed_holdings)
        except Exception as e:
            logger.error(f"Error parsing embed message: {e}")
    elif message.author.bot:
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
    """Handle NASDAQ alerts posted in the secondary channel."""
    logger.info(f"Received message on secondary channel: {message.content}")
    result = alert_channel_message(message.content)
    logger.info(f"Alert parser result: {result}")
    if not (isinstance(result, dict) and result.get("reverse_split_confirmed")):
        logger.warning("Message not confirming reverse split or malformed")
        return
    ticker = result.get("ticker")
    url = result.get("url")
    if not ticker or not url:
        logger.error("Missing ticker or URL")
        return

    try:
        logger.info(f"Policy resolution for {url}")
        policy_info = OnMessagePolicyResolver.full_analysis(url)
        if not policy_info:
            logger.warning(f"No policy info for {ticker}")
            return

        summary = build_policy_summary(ticker, policy_info, url)
        await post_policy_summary(bot, ticker, summary)

        body_text = policy_info.get("body_text")
        if body_text:
            context = f"Round-up snippet from {alert_url}: "
            snippet = body_text[: 2000 - len(context)]
            logger.info(f"Posting body text snippet for {alert_ticker}")
            await message.channel.send(context + snippet)

        if policy_info.get("round_up_confirmed"):
            await attempt_autobuy(bot, message.channel, ticker, quantity=1)
            split_date = policy_info.get("effective_date") or date.today().isoformat()
            split_watch_utils.add_split_watch(ticker, split_date)
            logger.info(f"Added split watch: {ticker} @ {split_date}")
    except Exception:
        logger.exception("Error during policy analysis secondary channel")


async def attempt_autobuy(bot, channel, ticker, quantity=1):
    now = datetime.now()
    mon_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    mon_close = now.replace(hour=16, minute=0, microsecond=0)

    if now.weekday() >= 5:
        days = (7 - now.weekday()) % 7 or 7
        exec_time = (now + timedelta(days=days)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
        logger.warning("Scheduling autobuy next Monday")
    elif mon_open <= now <= mon_close:
        exec_time = now
        logger.info("Market open – immediate autobuy")
    else:
        exec_time = (now + timedelta(days=1)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
        logger.info("Market closed – scheduling next market open")

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
    await channel.send(confirmation)
    logger.info(confirmation)


def build_policy_summary(ticker, policy_info, fallback_url):
    summary = f"**Reverse Split Alert** for `{ticker}`\n"
    summary += f"[NASDAQ Notice]({policy_info.get('nasdaq_url', fallback_url)})\n"

    if "press_url" in policy_info:
        summary += f"[Press Release]({policy_info['press_url']})\n"
    if "sec_url" in policy_info:
        summary += f"[SEC Filing]({policy_info['sec_url']})\n"

    effective_date = policy_info.get("effective_date")
    if effective_date:
        summary += f"**Effective Date:** {effective_date}\n"

    policy_text = policy_info.get("sec_policy") or policy_info.get("policy")
    summary += f"**Fractional Share Policy:** {policy_text}"

    snippet = policy_info.get("snippet")
    if snippet:
        summary += f"\n> {snippet}"

    return summary


async def post_policy_summary(bot, ticker, summary):
    chan = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if chan:
        await chan.send(summary)
        logger.info(f"Posted policy summary for {ticker}")
    else:
        logger.error("Primary channel unavailable")


# -----------------------------------------------------------------------------------------------
# SplitPolicyResolver and OnMessagePolicyResolver (deduplicated and cleaned)
# -----------------------------------------------------------------------------------------------


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
            "q": f"{ticker} " + " OR ".join(f'"{t}"' for t in self.SEARCH_TERMS),
            "dateRange": "custom",
            "startdt": self.start_date,
            "enddt": self.end_date,
            "category": "full",
            "start": 0,
            "count": 10,
        }

    def search_sec_filings(self, ticker):
        try:
            response = requests.get(
                self.BASE_URL,
                params=self.build_search_params(ticker),
                headers=self.HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception("SEC filings search error")
            return None

    def extract_policy_from_sec_filing(self, url):
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ")
            return {
                "round_up": self.is_round_up_policy(text),
                "cash_in_lieu": "cash in lieu" in text.lower(),
                "round_down": "rounded down" in text.lower(),
            }
        except Exception:
            logger.exception("Error extracting SEC filing")
            return None

    def fetch_sec_policy(self, ticker):
        data = self.search_sec_filings(ticker)
        if not data or "hits" not in data.get("hits", {}):
            logger.warning("No filings found")
            return None
        for fh in data["hits"]["hits"]:
            form = fh["_source"].get("form", "")
            if form in ("8-K", "S-1", "S-3", "S-4", "14A", "10-K", "10-Q"):
                cik = fh["_source"].get("ciks", [""])[0]
                adsh = fh["_source"].get("adsh", "")
                fid = fh["_id"].split(":", 1)[-1]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fid}"
                info = self.extract_policy_from_sec_filing(filing_url)
                if info:
                    logger.info("Policy info extracted")
                    return info
        logger.warning("No valid policy extracted")
        return None

    @staticmethod
    def is_round_up_policy(text):
        if not text:
            return False
        txt = text.lower()
        return (
            "rounded up" in txt
            and all(
                term not in txt
                for term in ("cash in lieu", "paid in cash", "payment for fractional")
            )
            and "fractional share" in txt
        )

    @staticmethod
    def detect_policy_from_text(text, keywords):
        for kw in keywords:
            if kw in text:
                logger.info(f"Detected keyword: {kw}")
                return kw.capitalize()
        logger.warning("No clear policy keyword detected")
        return "Policy not clearly stated."

    @classmethod
    def fetch_text_from_url(cls, url):
        try:
            resp = requests.get(url, headers=cls.HEADERS, timeout=10)
            resp.raise_for_status()
            text = resp.text
            if "html" in resp.headers.get("Content-Type", ""):
                text = BeautifulSoup(text, "html.parser").get_text(" ")
            text = " ".join(text.split())
            logger.info(f"Fetched text ({len(text)} chars)")
            return text
        except Exception:
            logger.exception("Error fetching text from URL")
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
    def analyze_text(cls, source, keywords=None):
        text = cls.fetch_text_from_url(source)
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
