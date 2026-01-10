"""Discord message handlers used by RSAssistant."""

import json
import re
import asyncio
from datetime import datetime, timedelta, date
from collections import defaultdict
from typing import Sequence
import requests

from utils.logging_setup import logger
from utils.config_utils import BOT_PREFIX, load_account_mappings
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
from utils.order_exec import schedule_and_execute, send_sell_command
from utils.market_calendar import MARKET_TZ, is_market_open_at, next_market_open
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
from utils.channel_resolver import (
    resolve_message_destination,
    resolve_reply_channel,
)

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
_refresh_summary_task = None
_refresh_channel = None
REFRESH_WINDOW_DURATION = timedelta(minutes=30)
BROKER_DISCOVERY_WINDOW = timedelta(seconds=20)

_configured_brokers = set()
_configured_brokers_source = None
_refresh_seen_brokers = set()
_refresh_discovered_brokers = set()
_refresh_completion_event = None
_refresh_discovery_task = None

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


def _format_account_label(broker: str, account_name: str) -> str:
    """Return an account label without repeating the broker prefix.

    Args:
        broker (str): Broker name associated with the holdings entry.
        account_name (str): Nickname parsed from holdings data.

    Returns:
        str: Combined account label with a single broker prefix.
    """

    broker_prefix = (broker or "").strip()
    normalized_account = (account_name or "").strip()

    if not broker_prefix:
        return normalized_account

    if normalized_account.lower().startswith(broker_prefix.lower()):
        return normalized_account

    if not normalized_account:
        return broker_prefix

    return f"{broker_prefix} {normalized_account}".strip()


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


def _format_watch_date(split_date: str) -> str:
    """Normalize split_date to M/D for watch command compatibility."""
    if not split_date:
        return split_date
    try:
        parsed = datetime.fromisoformat(split_date).date()
        return f"{parsed.month}/{parsed.day}"
    except ValueError:
        return split_date


def _normalize_broker_name(broker: str) -> str:
    """Return a normalized broker name for comparisons."""

    return (broker or "").strip().upper()


def _load_configured_brokers_from_mappings() -> set[str]:
    mappings = load_account_mappings()
    return {_normalize_broker_name(broker) for broker in mappings.keys() if broker}


def _ensure_configured_brokers_loaded() -> None:
    global _configured_brokers, _configured_brokers_source

    mapped_brokers = _load_configured_brokers_from_mappings()
    if mapped_brokers:
        if _configured_brokers != mapped_brokers or _configured_brokers_source != "account_mapping":
            _configured_brokers = mapped_brokers
            _configured_brokers_source = "account_mapping"
            logger.info(
                "Configured brokers loaded from account mapping (%d).",
                len(_configured_brokers),
            )
        return
    if _configured_brokers:
        return


def _set_configured_brokers_from_discovery(brokers: set[str]) -> None:
    global _configured_brokers, _configured_brokers_source

    if not brokers:
        return
    _configured_brokers = set(brokers)
    _configured_brokers_source = "discovered"
    logger.info(
        "Configured brokers discovered from holdings refresh (%d).",
        len(_configured_brokers),
    )


def _reset_refresh_state(cancel_timer: bool = True):
    """Clear buffered holdings refresh state and any pending timers."""

    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands
    global _refresh_summary_task, _refresh_channel

    if cancel_timer and _refresh_summary_task and not _refresh_summary_task.done():
        _refresh_summary_task.cancel()

    _refresh_active = False
    _pending_alerts_by_broker = defaultdict(dict)
    _pending_sell_commands = []
    _refresh_summary_task = None
    _refresh_channel = None


def _reset_completion_state() -> None:
    global _refresh_seen_brokers, _refresh_discovered_brokers
    global _refresh_completion_event, _refresh_discovery_task

    _refresh_seen_brokers = set()
    _refresh_discovered_brokers = set()
    _refresh_completion_event = None
    if _refresh_discovery_task and not _refresh_discovery_task.done():
        _refresh_discovery_task.cancel()
    _refresh_discovery_task = None


def _record_refresh_channel(channel) -> None:
    """Persist the target channel for the refresh summary."""

    global _refresh_channel
    _refresh_channel = channel


async def _finalize_discovered_brokers_after_idle() -> None:
    try:
        await asyncio.sleep(BROKER_DISCOVERY_WINDOW.total_seconds())
    except asyncio.CancelledError:
        return

    if not _refresh_completion_event or _refresh_completion_event.is_set():
        return
    if not _refresh_discovered_brokers:
        return
    _set_configured_brokers_from_discovery(_refresh_discovered_brokers)
    _refresh_completion_event.set()


def _reset_discovery_timer(bot) -> None:
    global _refresh_discovery_task

    if _refresh_discovery_task and not _refresh_discovery_task.done():
        _refresh_discovery_task.cancel()
    loop = getattr(bot, "loop", None) or asyncio.get_event_loop()
    _refresh_discovery_task = loop.create_task(_finalize_discovered_brokers_after_idle())


def start_holdings_completion_tracking(bot, force: bool = True) -> None:
    """Begin tracking holdings brokers for refresh completion."""

    global _refresh_completion_event, _refresh_seen_brokers, _refresh_discovered_brokers
    global _refresh_discovery_task

    if not force and _refresh_completion_event and not _refresh_completion_event.is_set():
        return

    _ensure_configured_brokers_loaded()
    _refresh_seen_brokers = set()
    _refresh_discovered_brokers = set()
    if _refresh_completion_event is None or _refresh_completion_event.is_set():
        _refresh_completion_event = asyncio.Event()
    else:
        _refresh_completion_event.clear()
    if _refresh_discovery_task and not _refresh_discovery_task.done():
        _refresh_discovery_task.cancel()
    _refresh_discovery_task = None


def reset_holdings_completion_tracking() -> None:
    """Clear holdings refresh completion tracking state."""

    _reset_completion_state()


async def wait_for_holdings_completion(timeout: float) -> bool:
    """Wait for holdings refresh to complete based on broker tracking."""

    if not _refresh_completion_event:
        return False
    try:
        await asyncio.wait_for(_refresh_completion_event.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


def record_holdings_brokers(bot, brokers: set[str]) -> None:
    """Track seen brokers during a holdings refresh."""

    if not brokers or not _refresh_completion_event or _refresh_completion_event.is_set():
        return

    normalized = {_normalize_broker_name(broker) for broker in brokers if broker}
    if not normalized:
        return

    if _configured_brokers:
        matched = normalized & _configured_brokers
        if not matched:
            return
        _refresh_seen_brokers.update(matched)
        if _configured_brokers.issubset(_refresh_seen_brokers):
            _refresh_completion_event.set()
        return

    _refresh_seen_brokers.update(normalized)
    _refresh_discovered_brokers.update(normalized)
    _reset_discovery_timer(bot)


async def _emit_refresh_summary(bot) -> None:
    """Send a consolidated holdings summary after the refresh window ends."""

    global _pending_alerts_by_broker, _pending_sell_commands

    if not _pending_alerts_by_broker:
        logger.info("No buffered alerts captured during holdings refresh window.")
        _reset_refresh_state(cancel_timer=False)
        return

    try:
        threshold = float(HOLDING_ALERT_MIN_PRICE)
    except Exception:
        threshold = 1.0

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
        f"{mention}Holdings >= ${threshold:.2f} detected across {len(_pending_alerts_by_broker)} broker(s) during refresh:\n"
    )
    max_len = 2000
    body = "\n".join(lines)
    first_msg = (header + body)[:max_len]

    channel = resolve_message_destination(bot, _refresh_channel)
    if channel is None:
        logger.error("Unable to resolve channel for holdings refresh summary.")
        _reset_refresh_state(cancel_timer=False)
        return

    await channel.send(first_msg)

    remaining = body[len(first_msg) - len(header) :]
    while remaining:
        chunk = remaining[: max_len - 1]
        await channel.send(chunk)
        remaining = remaining[len(chunk) :]

    for cmd in _pending_sell_commands:
        await send_sell_command(channel, cmd, bot=bot)

    _reset_refresh_state(cancel_timer=False)


async def _await_refresh_window(bot, duration: timedelta) -> None:
    """Wait for the refresh window to elapse before emitting a summary."""

    try:
        await asyncio.sleep(duration.total_seconds())
        await _emit_refresh_summary(bot)
    except asyncio.CancelledError:
        logger.info("Holdings refresh summary window cancelled before completion.")
        raise
    finally:
        _reset_refresh_state(cancel_timer=False)


def start_refresh_window(bot, channel, duration: timedelta) -> None:
    """Begin buffering holdings alerts and schedule a consolidated summary."""

    global _refresh_active, _refresh_summary_task

    _reset_refresh_state()
    _refresh_active = True
    _record_refresh_channel(channel)
    loop = getattr(bot, "loop", None) or asyncio.get_event_loop()
    _refresh_summary_task = loop.create_task(_await_refresh_window(bot, duration))


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


async def _audit_holdings(bot, message, parsed_holdings):
    missing = compute_account_missing_tickers(parsed_holdings)
    response_channel = resolve_message_destination(bot, message.channel)
    for account, tickers in missing.items():
        _missing_summary[account].update(tickers)
        await response_channel.send(f"Missing in {account}: {', '.join(tickers)}")


def set_channels(primary_id, secondary_id, tertiary_id):
    global DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_TERTIARY_CHANNEL
    DISCORD_PRIMARY_CHANNEL = primary_id
    DISCORD_SECONDARY_CHANNEL = secondary_id
    DISCORD_TERTIARY_CHANNEL = tertiary_id
    logger.info(
        f"rsassistant.bot.handlers.on_message loaded with primary={primary_id}, secondary={secondary_id}, tertiary={tertiary_id}"
    )


def on_message_ready(bot):
    """Compatibility helper: reapply channel IDs when the bot becomes ready."""

    set_channels(
        DISCORD_PRIMARY_CHANNEL,
        DISCORD_SECONDARY_CHANNEL,
        DISCORD_TERTIARY_CHANNEL,
    )
    logger.debug("on_message_ready hook executed.")


def on_message_refresh_status():
    """Return the current refresh/audit state for diagnostic use."""

    return {
        "refresh_active": _refresh_active,
        "audit_active": _audit_active,
        "refresh_channel_id": getattr(_refresh_channel, "id", None),
    }


def on_message_set_channels(primary_id, secondary_id, tertiary_id):
    """Alias to `set_channels` that matches the legacy export."""

    set_channels(primary_id, secondary_id, tertiary_id)


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

    global _refresh_active, _pending_alerts_by_broker, _pending_sell_commands
    lowered_content = message.content.lower().strip()

    response_channel = resolve_message_destination(bot, message.channel)

    # Detect start of holdings refresh to buffer alerts until completion
    if "!rsa holdings" in lowered_content:
        start_refresh_window(bot, message.channel, REFRESH_WINDOW_DURATION)
        start_holdings_completion_tracking(bot, force=False)
        logger.info("Detected start of holdings refresh; buffering alerts with timer.")

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

            brokers_seen = {str(h.get("broker", "")).strip() for h in parsed_holdings}
            record_holdings_brokers(bot, brokers_seen)

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
                        sell_cmd = f"!rsa sell {quantity} {ticker} {broker} false"
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
                    account_label = _format_account_label(broker, account_name)
                    lines.append(
                        f"- {account_label}: {qty:.2f} shares{price_fragment}"
                    )
                body = "\n".join(lines)
                await response_channel.send(header + body)

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
                    account_label = _format_account_label(broker, account_name)
                    details = ", ".join(
                        f"{it['ticker']} @ ${it['price']:.2f} (qty {it['quantity']})" for it in items
                    )
                    lines.append(f"- {account_label}: {details}")

                mention = _mention_prefix(tag_enabled=_should_tag_entries(alert_entries))
                header = (
                    f"{mention}Detected holdings >= ${threshold:.2f} across {len(grouped)} account(s):\n"
                )

                # Discord 2000 char limit; send in chunks if needed. Mention only once.
                max_len = 2000
                body = "\n".join(lines)
                first_msg = (header + body)[:max_len]
                await response_channel.send(first_msg)

                remaining = body[len(first_msg) - len(header) :]
                while remaining:
                    chunk = remaining[: max_len - 1]
                    await response_channel.send(chunk)
                    remaining = remaining[len(chunk) :]

                # After summary, send any queued auto-sell commands
                for cmd in sell_commands:
                    await send_sell_command(response_channel, cmd, bot=bot)
            if _audit_active:
                await _audit_holdings(bot, message, parsed_holdings)
        except Exception as e:
            logger.error(f"Error parsing embed message: {e}")
    elif message.author.bot:
        logger.info("Parsing regular order message.")
        lowered = lowered_content
        if lowered == "..updatebot":
            await response_channel.send("Pulling latest code and restarting...")
            update_and_restart()
            return
        if lowered == "..revertupdate":
            await response_channel.send("Reverting last update and restarting...")
            revert_and_restart()
            return

        entries = parse_bulk_watchlist_message(message.content)
        if entries:
            ctx = await bot.get_context(message)
            count = await add_entries_from_message(message.content, ctx)
            await response_channel.send(f"Added {count} tickers to watchlist.")
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

    response_channel = resolve_message_destination(bot, message.channel)
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
                target_channel = resolve_reply_channel(
                    bot, preferred_id=DISCORD_TERTIARY_CHANNEL
                )
                if not target_channel:
                    logger.error(
                        "Tertiary channel %s not found; unable to post snippet to tertiary.",
                        DISCORD_TERTIARY_CHANNEL,
                    )
            if not target_channel:
                fallback_channel = resolve_reply_channel(
                    bot, preferred_id=DISCORD_SECONDARY_CHANNEL
                )
                if fallback_channel:
                    target_channel = fallback_channel
                else:
                    target_channel = response_channel
                logger.warning(
                    "Falling back to channel %s for %s snippet delivery.",
                    getattr(target_channel, "id", "unknown"),
                    ticker,
                )

            await target_channel.send(context + snippet)
        elif body_text:
            logger.warning(
                "No round-up snippet found in body text for %s; skipping post.", ticker
            )

        if policy_info.get("round_up_confirmed"):
            split_date = policy_info.get("effective_date") or date.today().isoformat()
            split_ratio = policy_info.get("split_ratio") or "N/A"
            watch_date = _format_watch_date(split_date)

            if not watch_list_manager.ticker_exists(ticker):
                watch_command = (
                    f"{BOT_PREFIX}watch {ticker.upper()} {watch_date} {split_ratio}"
                )
                logger.info("Auto watch command: %s", watch_command)
                await watch_list_manager.watch_ticker(
                    response_channel, ticker, watch_date, split_ratio
                )

            existing = split_watch_utils.get_status(ticker)
            if existing:
                logger.info(
                    "Split watch already exists for %s; skipping autobuy.",
                    ticker,
                )
            else:
                split_watch_utils.add_split_watch(ticker, split_date)
                logger.info("Added split watch: %s @ %s", ticker, split_date)
                await attempt_autobuy(bot, response_channel, ticker, quantity=1)
    except Exception:
        logger.exception("Error during policy analysis secondary channel")


async def attempt_autobuy(bot, channel, ticker, quantity=1):
    now = datetime.now(MARKET_TZ)

    target_channel = resolve_message_destination(bot, channel)

    if is_market_open_at(now):
        exec_time = now
        logger.info("Market open – immediate autobuy")
    else:
        exec_time = next_market_open(now)
        logger.info("Market closed – scheduling next market open")

    # Prepare scheduling details and enqueue
    order_id = f"{ticker.upper()}_{exec_time.strftime('%Y%m%d_%H%M')}_buy"
    bot.loop.create_task(
        schedule_and_execute(
            ctx=target_channel,
            action="buy",
            ticker=ticker,
            quantity=quantity,
            broker="all",
            execution_time=exec_time,
            bot=bot,
            order_id=order_id,
        )
    )
    confirmation = (
        f"Scheduled autobuy: {ticker.upper()} x{quantity} at "
        f"{exec_time.strftime('%Y-%m-%d %H:%M')} ({order_id})"
    )
    await target_channel.send(confirmation)
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

    split_ratio = policy_info.get("split_ratio")
    if split_ratio:
        summary += f"**Split Ratio:** {split_ratio}\n"

    policy_text = policy_info.get("sec_policy") or policy_info.get("policy")
    summary += f"**Fractional Share Policy:** {policy_text}"

    fractional_policy = policy_info.get("fractional_share_policy")
    if fractional_policy:
        summary += f"\n**Fractional Share Policy (LLM):** {fractional_policy}"

    snippet = policy_info.get("snippet")
    if snippet:
        summary += f"\n> {snippet}"

    llm_details = policy_info.get("llm_details")
    if llm_details:
        summary += "\n```json\n"
        summary += json.dumps(llm_details, sort_keys=True)
        summary += "\n```"

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
        channel = resolve_reply_channel(bot, DISCORD_TERTIARY_CHANNEL)
        if not channel:
            logger.error(
                "Tertiary channel %s not found; reverse split summary will fallback.",
                DISCORD_TERTIARY_CHANNEL,
            )

    if not channel and DISCORD_PRIMARY_CHANNEL:
        channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
        if channel:
            logger.warning(
                "Posting %s reverse split summary to primary channel fallback.", ticker
            )

    if not channel:
        channel = resolve_reply_channel(bot)

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
