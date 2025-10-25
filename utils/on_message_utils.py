"""Discord message handlers used by RSAssistant."""

import re
import asyncio
from datetime import datetime, timedelta, date
from collections import defaultdict
from typing import Sequence
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
    MENTION_USER_IDS,
    MENTION_ON_ALERTS,
    TAGGED_ALERT_REQUIREMENTS,
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
_pending_alerts_by_broker = defaultdict(dict)  # broker -> ticker -> quantity
_pending_sell_commands = []  # queued auto-sell commands during refresh

AREB_TICKER = "AREB"
AREB_QUANTITY_THRESHOLD = 50
_AREB_ALERT_SUFFIX = "_AREB_THRESHOLD"


def format_mentions(user_ids: Sequence[str], enabled: bool, force: bool = False) -> str:
    """Return a Discord mention string for ``user_ids`` when enabled or forced."""

    if not user_ids:
        return ""
    if force or enabled:
        return " ".join(f"<@{user_id}>" for user_id in user_ids) + " "
    return ""


def _mention_prefix(force: bool = False, tag_enabled: bool = True) -> str:
    """Return the configured mention prefix when tagging is enabled."""

    if not tag_enabled and not force:
        return ""
    return format_mentions(MENTION_USER_IDS, MENTION_ON_ALERTS, force=force)


def _should_tag_alert(ticker: str, quantity: float) -> bool:
    """Return ``True`` when alerts for ``ticker`` should include mentions."""

    if not TAGGED_ALERT_REQUIREMENTS:
        return True

    normalized = ticker.upper()
    if normalized not in TAGGED_ALERT_REQUIREMENTS:
        return False
    requirement = TAGGED_ALERT_REQUIREMENTS.get(normalized)
    if requirement is None:
        return True
    return quantity >= requirement


def _should_tag_entries(entries) -> bool:
    """Return ``True`` if any alert entry satisfies mention requirements."""

    if not entries:
        return False
    if not TAGGED_ALERT_REQUIREMENTS:
        return True

    for entry in entries:
        ticker = str(entry.get("ticker", "")).upper()
        try:
            quantity = float(entry.get("quantity", 0) or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        if ticker and _should_tag_alert(ticker, quantity):
            return True
    return False


def _resolve_round_up_snippet(policy_info, max_length: int):
    """Return a trimmed snippet describing the round-up policy if present."""

    if not policy_info or max_length <= 0:
        return None

    snippet = policy_info.get("snippet")
    if snippet:
        return snippet.strip()[:max_length]

    body_text = policy_info.get("body_text")
    if not body_text:
        return None

    extracted = PolicyResolver.extract_round_up_snippet(body_text)
    if not extracted:
        return None

    return extracted.strip()[:max_length]


def _reset_refresh_state():
    """Clear any buffered holdings refresh state."""

    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands
    _refresh_active = False
    _pending_alerts_by_broker = defaultdict(dict)
    _pending_sell_commands = []


async def _handle_refresh_completion(message, lowered_content: str) -> None:
    """Flush buffered alerts when AutoRSA signals holdings completion."""

    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands

    if not _refresh_active or "all commands complete in all brokers" not in lowered_content:
        return

    try:
        threshold = float(HOLDING_ALERT_MIN_PRICE)
    except Exception:
        threshold = 1.0

    if _pending_alerts_by_broker:
        pending_entries = [
            {"ticker": ticker, "quantity": quantity}
            for ticker_map in _pending_alerts_by_broker.values()
            for ticker, quantity in ticker_map.items()
        ]
        mention = _mention_prefix(tag_enabled=_should_tag_entries(pending_entries))
        lines = []
        for broker in sorted(_pending_alerts_by_broker.keys()):
            tickers = ", ".join(sorted(_pending_alerts_by_broker[broker].keys()))
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

    _reset_refresh_state()


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

    Notes
    -----
    Order messages are parsed in a background thread to keep the Discord
    heartbeat responsive even if broker APIs respond slowly.
    """

    # Detect completion message regardless of author to flush buffered alerts
    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands
    lowered_content = message.content.lower().strip()
    await _handle_refresh_completion(message, lowered_content)

    # Detect start of holdings refresh to buffer alerts until completion
    if "!rsa holdings" in lowered_content:
        _refresh_active = True
        _pending_alerts_by_broker = defaultdict(dict)
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
            areb_alerts = []

            for h in parsed_holdings:
                try:
                    ticker = str(h.get("ticker", "")).upper()
                    if not ticker or ticker == "CASH AND SWEEP FUNDS":
                        continue

                    broker = str(h.get("broker", "")).strip()
                    account_name = str(h.get("account_name", h.get("account", "")))
                    price = float(h.get("price", 0) or 0)
                    quantity = float(h.get("quantity", 0) or 0)

                    if ticker == AREB_TICKER and quantity > AREB_QUANTITY_THRESHOLD:
                        if not is_broker_ignored(broker):
                            alert_key = f"{ticker}{_AREB_ALERT_SUFFIX}"
                            if not has_acted_today(broker, account_name, alert_key):
                                areb_alerts.append(
                                    {
                                        "broker": broker,
                                        "account_name": account_name,
                                        "quantity": quantity,
                                        "price": price,
                                    }
                                )
                                record_action_today(broker, account_name, alert_key)

                    if ticker in IGNORE_TICKERS_SET or is_broker_ignored(broker):
                        continue
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

            if areb_alerts:
                mention = _mention_prefix(force=True)
                header = (
                    f"{mention}AREB position(s) above {AREB_QUANTITY_THRESHOLD} shares detected:\n"
                )
                lines = []
                for alert in areb_alerts:
                    qty = alert["quantity"]
                    broker = alert["broker"]
                    account_name = alert["account_name"]
                    price = alert["price"]
                    price_fragment = f" @ ${price:.2f}" if price else ""
                    lines.append(
                        f"- {broker} {account_name}: {qty:.2f} shares{price_fragment}"
                    )
                body = "\n".join(lines)
                await message.channel.send(header + body)

            # During refresh, buffer alerts and sell commands; otherwise, send immediately
            if alert_entries and _refresh_active:
                for e in alert_entries:
                    broker_alerts = _pending_alerts_by_broker[e["broker"]]
                    ticker = e["ticker"]
                    quantity = float(e.get("quantity", 0) or 0)
                    broker_alerts[ticker] = max(
                        quantity,
                        float(broker_alerts.get(ticker, 0) or 0),
                    )
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

                mention = _mention_prefix(tag_enabled=_should_tag_entries(alert_entries))
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
        lowered = lowered_content
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
        await asyncio.to_thread(parse_order_message, message.content)


async def handle_secondary_channel(bot, message):
    """Handle NASDAQ alerts posted in the secondary channel.

    Reverse split policy summaries and supporting snippets are forwarded to
    the tertiary channel when it is configured. Other operational messages
    continue to use their original destinations.
    """
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
        context = f"Round-up snippet from {url}: "
        max_length = max(0, 2000 - len(context))
        snippet = _resolve_round_up_snippet(policy_info, max_length=max_length)

        if snippet:
            logger.info(f"Posting body text snippet for {ticker}")

            target_channel = None
            if DISCORD_TERTIARY_CHANNEL:
                target_channel = bot.get_channel(DISCORD_TERTIARY_CHANNEL)
                if not target_channel:
                    logger.error(
                        "Tertiary channel %s not found; unable to post snippet to tertiary.",
                        DISCORD_TERTIARY_CHANNEL,
                    )
            if not target_channel:
                logger.warning(
                    "Falling back to secondary channel for %s snippet delivery.",
                    ticker,
                )
                target_channel = message.channel

            await target_channel.send(context + snippet)
        elif body_text:
            logger.warning(
                "No round-up snippet found in body text for %s; skipping post.", ticker
            )

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
    """Send a reverse split policy summary to the tertiary channel.

    If the tertiary channel ID is not configured or cannot be resolved, the
    summary falls back to the primary channel so the alert is not lost.

    Args:
        bot: Active Discord bot/client instance.
        ticker: The ticker symbol associated with the alert.
        summary: Rendered summary text to post.
    """

    channel = None
    if DISCORD_TERTIARY_CHANNEL:
        channel = bot.get_channel(DISCORD_TERTIARY_CHANNEL)
        if not channel:
            logger.error(
                "Tertiary channel %s not found; reverse split summary will fallback.",
                DISCORD_TERTIARY_CHANNEL,
            )

    if not channel and DISCORD_PRIMARY_CHANNEL:
        channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
        if channel:
            logger.warning(
                "Posting %s reverse split summary to primary channel fallback.", ticker
            )

    if not channel:
        logger.error(
            "Unable to resolve a channel for %s reverse split summary.", ticker
        )
        return

    await channel.send(summary)
    logger.info(
        "Posted policy summary for %s to channel %s", ticker, getattr(channel, "id", "unknown")
    )





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
