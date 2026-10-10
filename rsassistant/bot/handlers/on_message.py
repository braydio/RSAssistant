"""Discord message handlers used by RSAssistant."""

import re
import asyncio
import uuid
import errno
from datetime import datetime, timedelta, date
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from utils.logging_setup import logger
from utils.config_utils import (
    BOT_PREFIX,
    TRUSTED_AUTORSA_BOT_ID,
    load_account_mappings,
)
from utils.parsing_utils import (
    alert_channel_message,
    parse_embed_message,
    parse_order_message,
)
from utils.csv_utils import (
    begin_holdings_refresh,
    finalize_holdings_refresh,
    holdings_refresh_in_progress,
    save_holdings_to_csv,
)
from utils.watch_utils import (
    parse_bulk_watchlist_message,
    add_entries_from_message,
    watch_list_manager,
)
from utils.update_utils import update_and_restart, revert_and_restart
from utils.order_exec import schedule_and_execute, send_sell_command
from utils.order_queue_manager import get_order_queue
from utils.market_calendar import MARKET_TZ, is_market_open_at, next_market_open
from utils.monitor_utils import try_record_action_today
from utils.config_utils import (
    AUTO_BUY_WATCHLIST,
    AUTO_SELL_LIVE,
    HOLDING_ALERT_MIN_PRICE,
    IGNORE_TICKERS as IGNORE_TICKERS_SET,
    IGNORE_BROKERS as IGNORE_BROKERS_SET,
    MENTION_USER_IDS,
    MENTION_ON_ALERTS,
    TAGGED_ALERT_REQUIREMENTS,
)
from utils import split_watch_utils
from rsassistant.bot.channel_resolver import (
    resolve_message_destination,
    resolve_reply_channel,
    resolve_watchlist_channel,
)

from rsassistant.services import alert_processing
from rsassistant.services import order_orchestration
from rsassistant.services.policy_orchestration import policy_analysis_service

DISCORD_PRIMARY_CHANNEL = None
DISCORD_SECONDARY_CHANNEL = None
DISCORD_TERTIARY_CHANNEL = None
DISCORD_HOLDINGS_CHANNEL = None

# Flag indicating the '..all' command is auditing watchlist holdings
_audit_active = False
# Accumulates missing tickers per account during an audit
_missing_summary = defaultdict(set)

# Flag and buffers for holdings refresh aggregation
_refresh_active = False
_pending_alerts_by_broker = defaultdict(dict)  # broker -> ticker -> quantity
_pending_sell_commands = []  # queued auto-sell commands during refresh
_pending_reverse_split_round_ups = False  # tracked reverse-split round-ups seen during refresh
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

ONE_SHARE_CACHE_TTL = timedelta(hours=4)
_one_share_positions: dict[str, dict[str, float]] = {}
_one_share_updated: dict[str, datetime] = {}


def _fd_usage_hint() -> str:
    fd_dir = Path("/proc/self/fd")
    try:
        return f"fd_count={len(list(fd_dir.iterdir()))}"
    except Exception:
        return "fd_count=unknown"


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
    return alert_processing.should_tag_alert(
        ticker, quantity, TAGGED_ALERT_REQUIREMENTS
    )


def _should_tag_entries(entries) -> bool:
    """Return ``True`` if any alert entry satisfies mention requirements."""

    return alert_processing.should_tag_entries(entries, TAGGED_ALERT_REQUIREMENTS)


def _format_account_label(broker: str, account_name: str) -> str:
    """Return an account label without repeating the broker prefix.

    Args:
        broker (str): Broker name associated with the holdings entry.
        account_name (str): Nickname parsed from holdings data.

    Returns:
        str: Combined account label with a single broker prefix.
    """

    return alert_processing.format_account_label(broker, account_name)


def _resolve_round_up_snippet(policy_info, max_length: int):
    """Return a trimmed snippet describing the round-up policy if present."""

    return alert_processing.resolve_round_up_snippet(policy_info, max_length)


def _format_watch_date(split_date: str) -> str:
    """Normalize split_date to M/D for watch command compatibility."""
    return alert_processing.format_watch_date(split_date)


def _resolve_round_up_confirmation(policy_info: dict) -> bool:
    """Resolve round-up confirmation, preferring LLM when available."""
    return alert_processing.resolve_round_up_confirmation(policy_info)


def _resolve_fractional_handling_text(policy_info: dict) -> str:
    """Return the resolved fractional share handling text."""
    return alert_processing.resolve_fractional_handling_text(policy_info)


async def _process_round_up_flow(
    bot,
    channel,
    ticker: str,
    split_date: str,
    split_ratio: str,
    watch_date: str,
) -> None:
    """Unified flow for confirmed round-up reverse splits."""
    ticker = (ticker or "").upper()
    if not ticker:
        logger.error("Round-up flow aborted: empty ticker.")
        return

    target_channel = channel
    if bot is not None:
        watchlist_channel = resolve_watchlist_channel(bot)
        if watchlist_channel and getattr(watchlist_channel, "id", None) != getattr(
            channel, "id", None
        ):
            await channel.send("Check the watchlist channel for updates.")
            target_channel = watchlist_channel

    # Refresh cached watchlists to avoid stale ticker data.
    watch_list_manager.load_watch_list()
    split_watch_utils.load_data()

    watchlist_updated = False
    if not watch_list_manager.ticker_exists(ticker):
        await watch_list_manager.watch_ticker(
            target_channel, ticker, watch_date, split_ratio
        )
        watchlist_updated = True
    else:
        existing = watch_list_manager.get_watch_list().get(ticker, {})
        existing_ratio = existing.get("split_ratio")
        if split_ratio and split_ratio != existing_ratio:
            watch_list_manager.add_ticker(ticker, watch_date, split_ratio)
            watchlist_updated = True
            await target_channel.send(
                f"Updated watchlist entry for {ticker} to {watch_date} ({split_ratio})."
            )

    scheduled_autobuy = False
    existing_split_watch = split_watch_utils.get_status(ticker)
    if existing_split_watch:
        logger.info("Split watch already exists for %s; skipping autobuy.", ticker)
    else:
        split_watch_utils.add_split_watch(ticker, split_date)
        logger.info("Added split watch: %s @ %s", ticker, split_date)
        await attempt_autobuy(bot, channel, ticker, quantity=1)
        scheduled_autobuy = True

    summary = (
        f"Round-up confirmed for {ticker}. "
        f"Watchlist {'updated' if watchlist_updated else 'already tracked'}; "
        f"autobuy {'scheduled' if scheduled_autobuy else 'already tracked'}."
    )
    await target_channel.send(summary)


def _normalize_broker_name(broker: str) -> str:
    """Return a normalized broker name for comparisons."""
    return alert_processing.normalize_broker_name(broker)


def _load_configured_brokers_from_mappings() -> set[str]:
    mappings = load_account_mappings()
    return {_normalize_broker_name(broker) for broker in mappings.keys() if broker}


def _ensure_configured_brokers_loaded() -> None:
    global _configured_brokers, _configured_brokers_source

    mapped_brokers = _load_configured_brokers_from_mappings()
    if mapped_brokers:
        if (
            _configured_brokers != mapped_brokers
            or _configured_brokers_source != "account_mapping"
        ):
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
    global _refresh_summary_task, _refresh_channel, _pending_reverse_split_round_ups

    if cancel_timer and _refresh_summary_task and not _refresh_summary_task.done():
        _refresh_summary_task.cancel()

    _refresh_active = False
    _pending_alerts_by_broker = defaultdict(dict)
    _pending_sell_commands = []
    _pending_reverse_split_round_ups = False
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
    finalize_holdings_refresh_if_complete()


def _reset_discovery_timer(bot) -> None:
    global _refresh_discovery_task

    if _refresh_discovery_task and not _refresh_discovery_task.done():
        _refresh_discovery_task.cancel()
    loop = getattr(bot, "loop", None) or asyncio.get_event_loop()
    _refresh_discovery_task = loop.create_task(
        _finalize_discovered_brokers_after_idle()
    )


def start_holdings_completion_tracking(bot, force: bool = True) -> None:
    """Begin tracking holdings brokers for refresh completion."""

    global _refresh_completion_event, _refresh_seen_brokers, _refresh_discovered_brokers
    global _refresh_discovery_task

    if (
        not force
        and _refresh_completion_event
        and not _refresh_completion_event.is_set()
    ):
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


def finalize_holdings_refresh_if_complete() -> bool:
    """Promote staged holdings once broker completion has been reached."""

    if not _refresh_completion_event or not _refresh_completion_event.is_set():
        return False
    if not holdings_refresh_in_progress():
        return False
    try:
        return finalize_holdings_refresh()
    except Exception as exc:
        logger.error("Failed to finalize staged holdings refresh: %s", exc)
        return False


def record_holdings_brokers(bot, brokers: set[str]) -> None:
    """Track seen brokers during a holdings refresh."""

    if (
        not brokers
        or not _refresh_completion_event
        or _refresh_completion_event.is_set()
    ):
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

    global _pending_alerts_by_broker, _pending_sell_commands, _pending_reverse_split_round_ups

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

    header = f"{mention}Holdings >= ${threshold:.2f} detected across {len(_pending_alerts_by_broker)} broker(s) during refresh:\n"
    if _pending_reverse_split_round_ups:
        header += "Run `..xsplits` to queue auto-sell of the 1-share positions.\n"
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
    except Exception as exc:
        if isinstance(exc, OSError) and exc.errno == errno.EMFILE:
            logger.error(
                "Holdings refresh summary task failed: %s (%s)",
                exc,
                _fd_usage_hint(),
            )
        else:
            logger.error("Holdings refresh summary task failed: %s", exc)
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


def is_tracked_reverse_split(ticker: str) -> bool:
    """Return ``True`` when ``ticker`` is a known reverse-split candidate.

    Used to keep the one-share round-up detector from flagging ordinary
    single-share holdings; only tickers already on the reverse-split
    watchlist (pre-split ``watch``/``sell`` entries or the split-status
    tracker) can be round-up positions worth closing out.
    """

    ticker_key = str(ticker or "").strip().upper()
    if not ticker_key:
        return False
    if ticker_key in watch_list_manager.get_watch_list():
        return True
    if ticker_key in watch_list_manager.get_sell_list():
        return True
    if ticker_key in split_watch_utils.get_full_watchlist():
        return True
    return False


def record_one_share_position(broker: str, ticker: str, price: float) -> None:
    """Record a >=$1 one-share reverse-split round-up in the ..xsplits cache."""

    broker_key = str(broker or "").strip()
    ticker_key = str(ticker or "").strip().upper()
    if not broker_key or not ticker_key:
        return
    _one_share_positions.setdefault(broker_key, {})[ticker_key] = float(price)
    _one_share_updated[broker_key] = datetime.now()


def get_one_share_positions() -> dict[str, dict[str, float]]:
    """Return a copy of the cached one-share positions grouped by broker."""

    return {broker: dict(tickers) for broker, tickers in _one_share_positions.items()}


def one_share_cache_fresh(brokers, ttl: timedelta = ONE_SHARE_CACHE_TTL) -> bool:
    """Return ``True`` when every ``brokers`` entry has a cache hit within ``ttl``."""

    now = datetime.now()
    return all(
        broker in _one_share_updated and now - _one_share_updated[broker] <= ttl
        for broker in brokers
    )


def clear_one_share_position(broker: str, ticker: str) -> None:
    """Remove a cached one-share position, e.g. after it has been queued for sale."""

    broker_key = str(broker or "").strip()
    ticker_key = str(ticker or "").strip().upper()
    bucket = _one_share_positions.get(broker_key)
    if not bucket or ticker_key not in bucket:
        return
    del bucket[ticker_key]
    if not bucket:
        del _one_share_positions[broker_key]


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
    return alert_processing.compute_account_missing_tickers(
        parsed_holdings, watch_list_manager.get_watch_list().keys()
    )


def _extract_order_queue_pairs() -> set[tuple[str, str]]:
    """Return queued ``(ticker, broker)`` pairs to avoid duplicate watchlist autobuys.

    Returns:
        set[tuple[str, str]]: Normalized ``(ticker, broker)`` pairs for queued buy
        and sell commands in the persistent order queue.
    """

    pairs: set[tuple[str, str]] = set()
    for order in get_order_queue().values():
        ticker = str(order.get("ticker", "")).strip().upper()
        broker = _normalize_broker_name(order.get("broker", ""))
        if ticker and broker:
            pairs.add((ticker, broker))
    return pairs


async def queue_missing_watchlist_autobuys(
    bot, channel, missing_by_account: dict[str, list[str]]
) -> int:
    """Queue watchlist autobuys for broker/ticker gaps discovered during ``..all``.

    A ``!rsa buy 1 <ticker> <broker> false`` command is queued only when there is
    no currently queued order for the same broker/ticker pair.

    Args:
        bot: Discord bot used to resolve the outbound command channel.
        channel: Current response channel used when channel resolution fails.
        missing_by_account (dict[str, list[str]]): Missing watchlist tickers keyed by
            account label in the form ``"<broker> ..."``.

    Returns:
        int: Number of missing watchlist autobuy commands queued/sent.
    """

    if not AUTO_BUY_WATCHLIST:
        return 0

    target_channel = resolve_reply_channel(
        bot, DISCORD_PRIMARY_CHANNEL
    ) or resolve_message_destination(bot, channel)
    queued_pairs = _extract_order_queue_pairs()
    planned, skipped = order_orchestration.build_watchlist_autobuy_commands(
        missing_by_account,
        queued_pairs,
        (broker for broker in IGNORE_BROKERS_SET if broker),
    )
    queued_count = 0
    for ticker, broker in skipped:
        logger.info(
            "Skipping watchlist autobuy for %s/%s; order already queued.",
            ticker,
            broker,
        )

    for ticker, broker, command in planned:
        await send_sell_command(target_channel, command, bot=bot)
        queued_count += 1
        logger.info(
            "Queued watchlist autobuy command for missing position %s/%s.",
            ticker,
            broker,
        )

    return queued_count


async def _audit_holdings(bot, message, parsed_holdings):
    """Accumulate audit deltas for ..all without per-account message spam."""
    missing = compute_account_missing_tickers(parsed_holdings)
    for account, tickers in missing.items():
        _missing_summary[account].update(tickers)

    queued_count = await queue_missing_watchlist_autobuys(bot, message.channel, missing)
    if queued_count:
        await response_channel.send(
            f"Queued {queued_count} watchlist autobuy command(s) for missing broker positions."
        )


def set_channels(primary_id, secondary_id, tertiary_id, holdings_id):
    global DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_TERTIARY_CHANNEL, DISCORD_HOLDINGS_CHANNEL
    DISCORD_PRIMARY_CHANNEL = primary_id
    DISCORD_SECONDARY_CHANNEL = secondary_id
    DISCORD_TERTIARY_CHANNEL = tertiary_id
    DISCORD_HOLDINGS_CHANNEL = holdings_id
    logger.info(
        "rsassistant.bot.handlers.on_message loaded with primary=%s, secondary=%s, tertiary=%s, holdings=%s",
        primary_id,
        secondary_id,
        tertiary_id,
        holdings_id,
    )


def on_message_ready(bot):
    """Compatibility helper: reapply channel IDs when the bot becomes ready."""

    set_channels(
        DISCORD_PRIMARY_CHANNEL,
        DISCORD_SECONDARY_CHANNEL,
        DISCORD_TERTIARY_CHANNEL,
        DISCORD_HOLDINGS_CHANNEL,
    )
    logger.debug("on_message_ready hook executed.")


def on_message_refresh_status():
    """Return the current refresh/audit state for diagnostic use."""

    return {
        "refresh_active": _refresh_active,
        "audit_active": _audit_active,
        "refresh_channel_id": getattr(_refresh_channel, "id", None),
    }


def on_message_set_channels(primary_id, secondary_id, tertiary_id, holdings_id):
    """Alias to `set_channels` that matches the legacy export."""

    set_channels(primary_id, secondary_id, tertiary_id, holdings_id)


def get_account_nickname_or_default(broker_name, group_number, account_number):
    try:
        broker_accounts = load_account_mappings().get(broker_name, {})
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
    if message.channel.id == DISCORD_PRIMARY_CHANNEL or (
        DISCORD_HOLDINGS_CHANNEL and message.channel.id == DISCORD_HOLDINGS_CHANNEL
    ):
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
    global _pending_reverse_split_round_ups
    lowered_content = message.content.lower().strip()

    response_channel = resolve_message_destination(bot, message.channel)

    # Detect start of holdings refresh to buffer alerts until completion
    if "!rsa holdings" in lowered_content:
        start_refresh_window(bot, message.channel, REFRESH_WINDOW_DURATION)
        start_holdings_completion_tracking(bot, force=False)
        begin_holdings_refresh()
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
            finalize_holdings_refresh_if_complete()

            # After saving, optionally alert and auto-sell tickers over threshold
            try:
                threshold = float(HOLDING_ALERT_MIN_PRICE)
            except Exception:
                threshold = 1.0

            alert_data = alert_processing.collect_holdings_alert_data(
                parsed_holdings,
                threshold=threshold,
                ignored_tickers=IGNORE_TICKERS_SET,
                is_broker_ignored=is_broker_ignored,
                is_tracked_reverse_split=is_tracked_reverse_split,
                record_action_today=try_record_action_today,
                areb_ticker=AREB_TICKER,
                areb_quantity_threshold=AREB_QUANTITY_THRESHOLD,
                auto_sell=AUTO_SELL_LIVE,
            )
            alert_entries = alert_data["alert_entries"]
            sell_commands = alert_data["sell_commands"]
            areb_alerts = alert_data["areb_alerts"]
            reverse_split_round_ups_found = alert_data[
                "reverse_split_round_ups_found"
            ]
            for broker, ticker, price in alert_data["one_share_positions"]:
                record_one_share_position(broker, ticker, price)

            if areb_alerts:
                mention = _mention_prefix(force=True)
                header = f"{mention}AREB position(s) above {AREB_QUANTITY_THRESHOLD} shares detected:\n"
                lines = []
                for alert in areb_alerts:
                    qty = alert["quantity"]
                    broker = alert["broker"]
                    account_name = alert["account_name"]
                    price = alert["price"]
                    price_fragment = f" @ ${price:.2f}" if price else ""
                    account_label = _format_account_label(broker, account_name)
                    lines.append(f"- {account_label}: {qty:.2f} shares{price_fragment}")
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
                if reverse_split_round_ups_found:
                    _pending_reverse_split_round_ups = True
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
                        f"{it['ticker']} @ ${it['price']:.2f} (qty {it['quantity']})"
                        for it in items
                    )
                    lines.append(f"- {account_label}: {details}")

                mention = _mention_prefix(
                    tag_enabled=_should_tag_entries(alert_entries)
                )
                header = f"{mention}Detected holdings >= ${threshold:.2f} across {len(grouped)} account(s):\n"
                if reverse_split_round_ups_found:
                    header += "Run `..xsplits` to queue auto-sell of the 1-share positions.\n"

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
            if isinstance(e, OSError) and e.errno == errno.EMFILE:
                logger.error("Error parsing embed message: %s (%s)", e, _fd_usage_hint())
            else:
                logger.error(f"Error parsing embed message: {e}")
    elif message.author.bot:
        if (
            not TRUSTED_AUTORSA_BOT_ID
            or getattr(message.author, "id", None) != TRUSTED_AUTORSA_BOT_ID
        ):
            logger.warning(
                "Ignoring message from untrusted bot ID %s.",
                getattr(message.author, "id", "unknown"),
            )
            return
        logger.info("Parsing regular order message.")
        lowered = lowered_content
        if (
            lowered in {"..updatebot", "..revertupdate"}
            and TRUSTED_AUTORSA_BOT_ID
            and getattr(message.author, "id", None) == TRUSTED_AUTORSA_BOT_ID
        ):
            if lowered == "..updatebot":
                await response_channel.send("Pulling latest code and restarting...")
                update_and_restart()
            else:
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
    alert_ticker = result.get("ticker")
    url = result.get("url")
    if not alert_ticker or not url:
        logger.error("Missing ticker or URL")
        return
    ticker = alert_ticker.upper()

    try:
        logger.info(f"Policy resolution for {url}")
        policy_info = await asyncio.to_thread(
            OnMessagePolicyResolver.full_analysis,
            url,
            ticker_hint=ticker,
            fallback_text=message.content,
        )
        if not policy_info:
            logger.warning(f"No policy info for {ticker}")
            return

        llm_ticker = (policy_info.get("llm_details") or {}).get("ticker")
        if llm_ticker and llm_ticker != ticker:
            logger.warning(
                "LLM ticker mismatch (alert=%s, llm=%s); using alert ticker.",
                ticker,
                llm_ticker,
            )

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

        if _resolve_round_up_confirmation(policy_info):
            summary = build_policy_summary(ticker, policy_info, url)
            await post_policy_summary(bot, ticker, summary)
            split_date = policy_info.get("effective_date") or date.today().isoformat()
            split_ratio = policy_info.get("split_ratio") or "N/A"
            watch_date = _format_watch_date(split_date)
            await _process_round_up_flow(
                bot,
                response_channel,
                ticker,
                split_date,
                split_ratio,
                watch_date,
            )
        else:
            handling = _resolve_fractional_handling_text(policy_info)
            alert = (
                f"Alert Detected: {ticker}\n" f"Fractional Share Handling: {handling}"
            )
            await post_alert_detection(bot, ticker, alert)
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

    # Prepare order configuration; the service returns plain order specs.
    from utils.config_utils import load_autobuy_config

    config = load_autobuy_config()
    orders_to_schedule = order_orchestration.build_autobuy_orders(
        ticker, quantity, config
    )
    for order in orders_to_schedule:
        order_id = str(uuid.uuid4())
        bot.loop.create_task(
            schedule_and_execute(
                ctx=target_channel,
                action="buy",
                ticker=order["ticker"],
                quantity=order["quantity"],
                broker=order["broker"],
                execution_time=exec_time,
                bot=bot,
                order_id=order_id,
            )
        )
        if order["kind"] == "standard":
            confirmation = (
                f"Scheduled autobuy: {order['ticker'].upper()} x{order['quantity']} at "
                f"{exec_time.strftime('%Y-%m-%d %H:%M')} ({order_id})"
            )
        else:
            confirmation = (
                f"Scheduled autobuy override: {order['ticker'].upper()} x{order['quantity']} "
                f"{order['broker']} at {exec_time.strftime('%Y-%m-%d %H:%M')} "
                f"({order_id})"
            )
        if order["excluded_brokers"]:
            confirmation += (
                f" [excluded: {', '.join(order['excluded_brokers'])}]"
            )
        await target_channel.send(confirmation)
        logger.info(confirmation)


def build_policy_summary(ticker, policy_info, fallback_url):
    return alert_processing.build_policy_summary(ticker, policy_info, fallback_url)


async def post_policy_summary(bot, ticker, summary):
    """Send a reverse split policy summary to the tertiary channel.

    If the tertiary channel ID is not configured or cannot be resolved, the
    summary falls back to the primary channel so the alert is not lost.

    Args:
        bot: Active Discord bot/client instance.
        ticker: The ticker symbol associated with the alert.
        summary: Rendered summary text to post.
    """

    channel = _resolve_alert_channel(bot, ticker)
    if not channel:
        return

    await channel.send(summary)
    logger.info(
        "Posted policy summary for %s to channel %s",
        ticker,
        getattr(channel, "id", "unknown"),
    )


async def post_alert_detection(bot, ticker, summary):
    """Send a minimal alert detection message to the alerts channel."""
    channel = _resolve_alert_channel(bot, ticker)
    if not channel:
        return

    await channel.send(summary)


def _resolve_alert_channel(bot, ticker):
    channel = None
    if DISCORD_TERTIARY_CHANNEL:
        channel = resolve_reply_channel(bot, DISCORD_TERTIARY_CHANNEL)
        if not channel:
            logger.error(
                "Tertiary channel %s not found; alert will fallback.",
                DISCORD_TERTIARY_CHANNEL,
            )

    if not channel and DISCORD_PRIMARY_CHANNEL:
        channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
        if channel:
            logger.warning("Posting %s alert to primary channel fallback.", ticker)

    if not channel:
        channel = resolve_reply_channel(bot)

    if not channel:
        logger.error("Unable to resolve a channel for %s alerts.", ticker)
        return None
    return channel


class OnMessagePolicyResolver:
    """Wrapper around :class:`utils.policy_resolver.SplitPolicyResolver`."""
    resolver = policy_analysis_service.resolver

    @classmethod
    def full_analysis(cls, nasdaq_url, ticker_hint=None, fallback_text=None):
        """Perform complete policy analysis for a NASDAQ notice URL."""
        return policy_analysis_service.full_analysis(
            nasdaq_url,
            ticker_hint=ticker_hint,
            fallback_text=fallback_text,
        )


# -------------------------
# SplitPolicyResolver
# -------------------------
