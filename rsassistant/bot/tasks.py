"""Background tasks for RSAssistant."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import discord
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from discord.ext import commands

from rsassistant.bot.channel_resolver import resolve_reply_channel
from utils.config_utils import (
    AUTO_RSA_HOLDINGS_ENABLED,
    BOT_PREFIX,
    DISCORD_PRIMARY_CHANNEL,
    ENABLE_MARKET_REFRESH,
    RESOURCE_METRICS_ENABLED,
    RESOURCE_METRICS_INTERVAL_SECONDS,
)
from utils.performance_metrics import start_metrics_task
from utils.order_exec import schedule_and_execute, shutdown_order_dispatcher
from utils.order_queue_manager import (
    get_order_queue,
    recover_stale_dispatching,
    update_order_time,
)
from utils.refresh_scheduler import MARKET_TZ, compute_next_refresh_datetime
from utils.market_calendar import is_market_open_at, next_market_open
from utils.watch_utils import send_reminder_message
from utils.holdings_importer import import_holdings_if_updated

logger = logging.getLogger(__name__)

_total_refresh_lock = asyncio.Lock()


@dataclass
class BackgroundTasks:
    """Container for running background task handles."""

    total_refresh_task: Optional[asyncio.Task] = None
    reschedule_task: Optional[asyncio.Task] = None
    reminder_scheduler: Optional[AsyncIOScheduler] = None
    metrics_task: Optional[asyncio.Task] = None


async def reschedule_queued_orders(bot: commands.Bot) -> None:
    """Reschedule persisted orders from previous runs."""

    parked = recover_stale_dispatching()
    if parked:
        logger.warning(
            "%d order(s) were interrupted mid-send and are parked as needs_review "
            "(not re-sent automatically): %s",
            len(parked),
            ", ".join(parked),
        )
    queue = {
        oid: data
        for oid, data in get_order_queue().items()
        if data.get("state", "pending") == "pending"
    }
    if not queue:
        logger.info("No queued orders to reschedule.")
        return

    # channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
    # logger.info(f"Getting primary channel from resolver {DISCORD_PRIMARY_CHANNEL}")

    # if not channel:
    #    logger.error("Primary channel not found for rescheduling orders.")
    #    return
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    logger.info(
        f"Skipping that dumbass function to get the channel ID using the channel ID: {DISCORD_PRIMARY_CHANNEL}"
    )
    logger.info(f"Got the damn channel myself: {channel}")
    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now(MARKET_TZ)
            if execution_time.tzinfo is None:
                execution_time = execution_time.replace(tzinfo=MARKET_TZ)
            if execution_time <= now:
                execution_time = (
                    now if is_market_open_at(now) else next_market_open(now)
                )
                update_order_time(
                    order_id, execution_time.strftime("%Y-%m-%d %H:%M:%S")
                )
            bot.loop.create_task(
                schedule_and_execute(
                    channel,
                    action=data["action"],
                    ticker=data["ticker"],
                    quantity=data["quantity"],
                    broker=data["broker"],
                    execution_time=execution_time,
                    order_id=order_id,
                    add_to_queue=False,
                )
            )
            logger.info("Rescheduled queued order %s", order_id)
        except Exception as exc:
            logger.error("Failed to reschedule order %s: %s", order_id, exc)


async def reschedule_past_due_orders(bot: commands.Bot) -> None:
    """Reschedule past-due queued orders to the next market open."""

    queue = {
        oid: data
        for oid, data in get_order_queue().items()
        if data.get("state", "pending") == "pending"
    }
    if not queue:
        logger.info("No queued orders to check for past-due rescheduling.")
        return

    channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
    if not channel:
        logger.error("Primary channel not found for past-due rescheduling.")
        return

    now = datetime.now(MARKET_TZ)
    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
            if execution_time.tzinfo is None:
                execution_time = execution_time.replace(tzinfo=MARKET_TZ)
            if execution_time > now:
                continue
            new_time = now if is_market_open_at(now) else next_market_open(now)
            update_order_time(order_id, new_time.strftime("%Y-%m-%d %H:%M:%S"))
            bot.loop.create_task(
                schedule_and_execute(
                    channel,
                    action=data["action"],
                    ticker=data["ticker"],
                    quantity=data["quantity"],
                    broker=data["broker"],
                    execution_time=new_time,
                    order_id=order_id,
                    add_to_queue=False,
                )
            )
            logger.info("Rescheduled past-due queued order %s", order_id)
        except Exception as exc:
            logger.error("Failed to reschedule past-due order %s: %s", order_id, exc)


async def _invoke_total_refresh(bot: commands.Bot) -> None:
    """Trigger the ``..all`` command via a synthetic message."""

    channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
    if channel is None:
        logger.error(
            "Total refresh scheduler could not resolve primary channel %s",
            DISCORD_PRIMARY_CHANNEL,
        )
        return

    command = bot.get_command("all")
    if command is None:
        logger.error("Total refresh scheduler could not locate '..all' command handler")
        return

    message = await channel.send(f"{BOT_PREFIX}all")
    try:
        ctx = await bot.get_context(message)
        await bot.invoke(ctx)
    finally:
        try:
            await message.delete()
        except discord.HTTPException as exc:
            logger.debug("Unable to delete scheduled '..all' trigger message: %s", exc)


async def _execute_total_refresh(bot: commands.Bot) -> None:
    """Execute the scheduled ``..all`` refresh with locking."""

    if _total_refresh_lock.locked():
        logger.warning("Skipping scheduled '..all' refresh; previous run still active.")
        return

    async with _total_refresh_lock:
        logger.info("Executing scheduled '..all' holdings refresh.")
        await _invoke_total_refresh(bot)


async def run_total_refresh_scheduler(bot: commands.Bot) -> None:
    """Invoke ``..all`` at a cadence matching market and off-hours policies."""

    while True:
        now = datetime.now(MARKET_TZ)
        next_run = compute_next_refresh_datetime(now)
        wait_seconds = max((next_run - now).total_seconds(), 0)
        logger.info(
            "Next scheduled '..all' refresh at %s",
            next_run.astimezone(MARKET_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        )
        try:
            await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            logger.info("Total refresh scheduler cancelled before next execution.")
            raise

        try:
            await _execute_total_refresh(bot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Scheduled '..all' refresh failed: %s", exc)


_reminder_scheduler: Optional[AsyncIOScheduler] = None


async def _import_holdings_job() -> None:
    """Run the synchronous holdings import off the event loop."""

    await asyncio.to_thread(import_holdings_if_updated)


def _log_job_event(event) -> None:
    """Log scheduler job failures without payloads; never stops the scheduler."""

    if event.code == EVENT_JOB_MISSED:
        logger.warning("Scheduled job %s missed its run time.", event.job_id)
    else:
        logger.error(
            "Scheduled job %s failed (%s).",
            event.job_id,
            type(event.exception).__name__ if event.exception else "unknown",
        )


def _start_reminder_scheduler(bot: commands.Bot) -> AsyncIOScheduler:
    """Start asyncio-native reminders (08:45, 15:30) and 07:00 past-due sweep.

    Must be called from the running event loop. Repeated calls return the
    already-running scheduler instead of starting a second one.
    """

    global _reminder_scheduler
    if _reminder_scheduler is not None and _reminder_scheduler.running:
        return _reminder_scheduler

    scheduler = AsyncIOScheduler(
        event_loop=asyncio.get_running_loop(), timezone=MARKET_TZ
    )
    job_defaults = {"replace_existing": True, "max_instances": 1, "coalesce": True}
    scheduler.add_job(
        send_reminder_message,
        CronTrigger(hour=8, minute=45, timezone=MARKET_TZ),
        args=[bot],
        id="reminder_morning",
        **job_defaults,
    )
    scheduler.add_job(
        send_reminder_message,
        CronTrigger(hour=15, minute=30, timezone=MARKET_TZ),
        args=[bot],
        id="reminder_afternoon",
        **job_defaults,
    )
    scheduler.add_job(
        reschedule_past_due_orders,
        CronTrigger(hour=7, minute=0, timezone=MARKET_TZ),
        args=[bot],
        id="reschedule_past_due_orders",
        **job_defaults,
    )
    if AUTO_RSA_HOLDINGS_ENABLED:
        scheduler.add_job(
            _import_holdings_job,
            IntervalTrigger(minutes=5),
            id="holdings_import",
            **job_defaults,
        )
    scheduler.add_listener(_log_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    scheduler.start()
    _reminder_scheduler = scheduler
    logger.info("Scheduled reminders at 8:45 AM and 3:30 PM started.")
    return scheduler


async def start_background_tasks(bot: commands.Bot) -> BackgroundTasks:
    """Start recurring tasks and return handles for shutdown."""

    reminder_scheduler = _start_reminder_scheduler(bot)
    total_refresh: Optional[asyncio.Task] = None
    if ENABLE_MARKET_REFRESH:
        total_refresh = asyncio.create_task(run_total_refresh_scheduler(bot))
    rescheduler = asyncio.create_task(reschedule_queued_orders(bot))
    metrics = start_metrics_task(
        RESOURCE_METRICS_ENABLED, RESOURCE_METRICS_INTERVAL_SECONDS
    )

    return BackgroundTasks(
        metrics_task=metrics,
        total_refresh_task=total_refresh,
        reschedule_task=rescheduler,
        reminder_scheduler=reminder_scheduler,
    )


async def stop_background_tasks(tasks: BackgroundTasks) -> None:
    """Gracefully shut down running tasks and schedulers."""

    for task in (
        tasks.total_refresh_task,
        tasks.reschedule_task,
        tasks.metrics_task,
    ):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Cancelled task %s", task.get_name() or task)

    global _reminder_scheduler
    await shutdown_order_dispatcher()

    if tasks.reminder_scheduler:
        try:
            tasks.reminder_scheduler.shutdown(wait=False)
        except Exception as exc:  # scheduler may already be stopped
            logger.debug("Scheduler shutdown: %s", type(exc).__name__)
        if tasks.reminder_scheduler is _reminder_scheduler:
            _reminder_scheduler = None
