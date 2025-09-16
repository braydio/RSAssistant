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
    IGNORE_BROKERS as IGNORE_BROKERS_SET,
    DISCORD_PRIMARY_CHANNEL as PRIMARY_CHAN_ID,
    MENTION_USER_ID,
    MENTION_ON_ALERTS,
)
from utils import split_watch_utils

from utils.policy_resolver import SplitPolicyResolver as PolicyResolver

DISCORD_PRIMARY_CHANNEL = None
DISCORD_SECONDARY_CHANNEL = None
DISCORD_TERTIARY_CHANNEL = None

# Flag indicating the '..all' command is auditing watchlist holdings
_audit_active = False
# Accumulates missing tickers per account during an audit
_missing_summary = defaultdict(set)

# Flag and buffers for holdings refresh aggregation
_refresh_active = False
_pending_alerts_by_broker = defaultdict(set)  # broker -> set[ticker]
_pending_sell_commands = []  # queued auto-sell commands during refresh


def is_broker_ignored(broker: str) -> bool:
    """Return ``True`` when ``broker`` is configured to skip alerts/auto-sell."""

    if not broker:
        return False
    return broker.strip().upper() in IGNORE_BROKERS_SET


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

    # Detect completion message regardless of author to flush buffered alerts
    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands
    lowered_content = message.content.lower().strip()
    if _refresh_active and "all commands complete in all brokers" in lowered_content:
        try:
            threshold = float(HOLDING_ALERT_MIN_PRICE)
        except Exception:
            threshold = 1.0

        if _pending_alerts_by_broker:
            mention = (
                f"<@{MENTION_USER_ID}> " if (MENTION_ON_ALERTS and MENTION_USER_ID) else ""
            )
            lines = []
            for broker in sorted(_pending_alerts_by_broker.keys()):
                tickers = ", ".join(sorted(_pending_alerts_by_broker[broker]))
                lines.append(f"- {broker}: {tickers}")

            header = (
                f"{mention}Detected holdings >= ${threshold:.2f} across {len(_pending_alerts_by_broker)} broker(s):\n"
            )
            max_len = 2000
            body = "\n".join(lines)
            first_msg = (header + body)[:max_len]
            await message.channel.send(first_msg)

            remaining = body[len(first_msg) - len(header) :]
            while remaining:
                chunk = remaining[: max_len - 1]
                await message.channel.send(chunk)
                remaining = remaining[len(chunk) :]

            for cmd in _pending_sell_commands:
                await message.channel.send(cmd)

        _refresh_active = False
        _pending_alerts_by_broker = defaultdict(set)
        _pending_sell_commands = []

    # Detect start of holdings refresh to buffer alerts until completion
    if "!rsa holdings" in lowered_content:
        _refresh_active = True
        _pending_alerts_by_broker = defaultdict(set)
        _pending_sell_commands = []
        logger.info("Detected start of holdings refresh; buffering alerts.")

    if message.content.startswith(BOT_PREFIX):
        logger.warning(f"Detected message with command prefix: {BOT_PREFIX}")
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

            # Aggregate alerts for a single summary message at the end
            alert_entries = []
            sell_commands = []

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
                    if is_broker_ignored(broker):
                        continue
                    account_name = str(h.get("account_name", h.get("account", "")))
                    if price < threshold or quantity <= 0:
                        continue
                    if has_acted_today(broker, account_name, ticker):
                        continue

                    # Accumulate for summary
                    alert_entries.append(
                        {
                            "broker": broker,
                            "account_name": account_name,
                            "ticker": ticker,
                            "price": price,
                            "quantity": quantity,
                        }
                    )

                    # Queue optional auto-sell commands to send after summary
                    if AUTO_SELL_LIVE:
                        sell_cmd = f"{BOT_PREFIX}ord sell {ticker} {broker} {quantity}"
                        sell_commands.append(sell_cmd)

                    # Record that we've acted to avoid duplicates the same day
                    record_action_today(broker, account_name, ticker)
                except Exception as exc:
                    logger.error(f"Monitor/auto-sell step failed for holding {h}: {exc}")

            # During refresh, buffer alerts and sell commands; otherwise, send immediately
            if alert_entries and _refresh_active:
                for e in alert_entries:
                    _pending_alerts_by_broker[e["broker"]].add(e["ticker"])
                _pending_sell_commands.extend(sell_commands)
            elif alert_entries:
                # Group tickers by account for readability
                grouped = {}
                for e in alert_entries:
                    key = (e["broker"], e["account_name"])
                    grouped.setdefault(key, []).append(e)

                lines = []
                for (broker, account_name), items in grouped.items():
                    details = ", ".join(
                        f"{it['ticker']} @ ${it['price']:.2f} (qty {it['quantity']})" for it in items
                    )
                    lines.append(f"- {broker} {account_name}: {details}")

                mention = (
                    f"<@{MENTION_USER_ID}> " if (MENTION_ON_ALERTS and MENTION_USER_ID) else ""
                )
                header = (
                    f"{mention}Detected holdings >= ${threshold:.2f} across {len(grouped)} account(s):\n"
                )

                # Discord 2000 char limit; send in chunks if needed. Mention only once.
                max_len = 2000
                body = "\n".join(lines)
                first_msg = (header + body)[:max_len]
                await message.channel.send(first_msg)

                remaining = body[len(first_msg) - len(header) :]
                while remaining:
                    chunk = remaining[: max_len - 1]
                    await message.channel.send(chunk)
                    remaining = remaining[len(chunk) :]

                # After summary, send any queued auto-sell commands
                for cmd in sell_commands:
                    await message.channel.send(cmd)
            if _audit_active:
                await _audit_holdings(message, parsed_holdings)
        except Exception as e:
            logger.error(f"Error parsing embed message: {e}")
    elif message.author.bot:
        logger.info("Parsing regular order message.")
        lowered = message.content.lower().strip()
        # If AutoRSA signals completion, flush buffered alerts per brokerage
        if _refresh_active and "all commands complete in all brokers" in lowered:
            try:
                threshold = float(HOLDING_ALERT_MIN_PRICE)
            except Exception:
                threshold = 1.0

            if _pending_alerts_by_broker:
                mention = (
                    f"<@{MENTION_USER_ID}> " if (MENTION_ON_ALERTS and MENTION_USER_ID) else ""
                )
                lines = []
                # Produce per-broker unique ticker list
                for broker in sorted(_pending_alerts_by_broker.keys()):
                    tickers = ", ".join(sorted(_pending_alerts_by_broker[broker]))
                    lines.append(f"- {broker}: {tickers}")

                header = (
                    f"{mention}Detected holdings >= ${threshold:.2f} across {len(_pending_alerts_by_broker)} broker(s):\n"
                )
                max_len = 2000
                body = "\n".join(lines)
                first_msg = (header + body)[:max_len]
                await message.channel.send(first_msg)

                remaining = body[len(first_msg) - len(header) :]
                while remaining:
                    chunk = remaining[: max_len - 1]
                    await message.channel.send(chunk)
                    remaining = remaining[len(chunk) :]

                # Send queued auto-sell commands after the summary
                for cmd in _pending_sell_commands:
                    await message.channel.send(cmd)

            # Reset refresh state
            _refresh_active = False
            _pending_alerts_by_broker = defaultdict(set)
            _pending_sell_commands = []
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
            # Use parsed URL/ticker variables defined above
            context = f"Round-up snippet from {url}: "
            snippet = body_text[: 2000 - len(context)]
            logger.info(f"Posting body text snippet for {ticker}")
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
    mon_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

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

    # Prepare scheduling details and enqueue
    order_id = f"{ticker.upper()}_{exec_time.strftime('%Y%m%d_%H%M')}_buy"
    bot.loop.create_task(
        schedule_and_execute(
            ctx=channel,
            action="buy",
            ticker=ticker,
            quantity=quantity,
            broker="all",
            execution_time=exec_time,
            order_id=order_id,
        )
    )
    confirmation = (
        f"Scheduled autobuy: {ticker.upper()} x{quantity} at "
        f"{exec_time.strftime('%Y-%m-%d %H:%M')} ({order_id})"
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
