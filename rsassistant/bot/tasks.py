"""Background tasks for RSAssistant."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import discord
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord.ext import commands

from utils.channel_resolver import resolve_reply_channel
from utils.config_utils import BOT_PREFIX, DISCORD_PRIMARY_CHANNEL, ENABLE_MARKET_REFRESH
from utils.order_exec import schedule_and_execute
from utils.order_queue_manager import get_order_queue
from utils.refresh_scheduler import MARKET_TZ, compute_next_refresh_datetime
from utils.watch_utils import send_reminder_message

logger = logging.getLogger(__name__)

_total_refresh_lock = asyncio.Lock()


@dataclass
class BackgroundTasks:
    """Container for running background task handles."""

    total_refresh_task: Optional[asyncio.Task] = None
    reschedule_task: Optional[asyncio.Task] = None
    reminder_scheduler: Optional[BackgroundScheduler] = None


async def reschedule_queued_orders(bot: commands.Bot) -> None:
    """Reschedule persisted orders from previous runs."""

    queue = get_order_queue()
    if not queue:
        logger.info("No queued orders to reschedule.")
        return

    channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
    if not channel:
        logger.error("Primary channel not found for rescheduling orders.")
        return

    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
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


def _start_reminder_scheduler(bot: commands.Bot) -> BackgroundScheduler:
    """Start APScheduler reminders at 8:45 AM and 3:30 PM."""

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: bot.loop.create_task(send_reminder_message(bot)),
        CronTrigger(hour=8, minute=45),
    )
    scheduler.add_job(
        lambda: bot.loop.create_task(send_reminder_message(bot)),
        CronTrigger(hour=15, minute=30),
    )
    scheduler.start()
    logger.info("Scheduled reminders at 8:45 AM and 3:30 PM started.")
    return scheduler


async def start_background_tasks(bot: commands.Bot) -> BackgroundTasks:
    """Start recurring tasks and return handles for shutdown."""

    reminder_scheduler = _start_reminder_scheduler(bot)
    total_refresh: Optional[asyncio.Task] = None
    if ENABLE_MARKET_REFRESH:
        total_refresh = asyncio.create_task(run_total_refresh_scheduler(bot))
    rescheduler = asyncio.create_task(reschedule_queued_orders(bot))

    return BackgroundTasks(
        total_refresh_task=total_refresh,
        reschedule_task=rescheduler,
        reminder_scheduler=reminder_scheduler,
    )


async def stop_background_tasks(tasks: BackgroundTasks) -> None:
    """Gracefully shut down running tasks and schedulers."""

    for task in (
        tasks.total_refresh_task,
        tasks.reschedule_task,
    ):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Cancelled task %s", task.get_name() or task)

    if tasks.reminder_scheduler:
        tasks.reminder_scheduler.shutdown(wait=False)
