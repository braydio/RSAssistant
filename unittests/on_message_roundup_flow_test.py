"""Tests for the round-up processing flow in on_message."""

import asyncio
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from rsassistant.bot.handlers import on_message
from utils import split_watch_utils
from utils.watch_utils import WatchListManager


class DummyChannel:
    """Minimal async channel stub for Discord send operations."""

    def __init__(self):
        self.send = AsyncMock()


class RoundUpFlowTest(IsolatedAsyncioTestCase):
    """Validate the unified round-up flow behavior."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target in (
            patch.object(split_watch_utils, "DATABASE_PATH", Path(self.tmp.name) / "r.db"),
            patch.object(split_watch_utils, "SPLIT_WATCH_FILE", Path(self.tmp.name) / "x.json"),
            patch.object(on_message, "watch_list_manager", WatchListManager()),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.channel = DummyChannel()
        self.day = (date.today() + timedelta(days=3)).isoformat()

    async def _flow(self, split_date=None, **_):
        await on_message._process_round_up_flow(
            bot=None,
            channel=self.channel,
            ticker="TEST",
            split_date=self.day if split_date is None else split_date,
            split_ratio="1-10",
            watch_date="1/10",
        )

    async def test_first_alert_tracks_and_schedules_once_with_replay_blocked(self):
        with patch.object(on_message, "attempt_autobuy", new=AsyncMock()) as autobuy:
            await self._flow()
            await self._flow()
            await asyncio.gather(self._flow(), self._flow())
            autobuy.assert_awaited_once()
        self.assertEqual(autobuy.await_args.kwargs["split_date"], self.day)
        self.assertIn("TEST", on_message.watch_list_manager.watch_list)
        self.assertIsNotNone(split_watch_utils.get_status("TEST"))

    async def test_replay_after_watch_archived_does_not_reschedule(self):
        with patch.object(on_message, "attempt_autobuy", new=AsyncMock()) as autobuy:
            await self._flow()
            split_watch_utils.mark_account_bought("TEST", "A")
            split_watch_utils.mark_account_sold("TEST", "A")
            split_watch_utils.update_split_status()
            split_watch_utils.remove_split_watch("TEST")
            await self._flow()
            autobuy.assert_awaited_once()

    async def test_different_later_date_is_claimable_once_when_no_active_watch(self):
        later = (date.today() + timedelta(days=90)).isoformat()
        with patch.object(on_message, "attempt_autobuy", new=AsyncMock()) as autobuy:
            await self._flow()
            split_watch_utils.remove_split_watch("TEST")
            await self._flow(later)
            await self._flow(later)
            self.assertEqual(autobuy.await_count, 2)

    async def test_missing_or_bad_date_schedules_nothing(self):
        with patch.object(on_message, "attempt_autobuy", new=AsyncMock()) as autobuy:
            await self._flow("")
            await self._flow("garbage")
            autobuy.assert_not_awaited()
        self.assertIsNone(split_watch_utils.get_status("TEST"))
        self.assertIn("manual", self.channel.send.await_args_list[0].args[0])

    async def test_active_watch_other_date_needs_review(self):
        split_watch_utils.add_split_watch("TEST", self.day)
        split_watch_utils.mark_account_bought("TEST", "A")
        later = (date.today() + timedelta(days=90)).isoformat()
        with patch.object(on_message, "attempt_autobuy", new=AsyncMock()) as autobuy:
            await self._flow(later)
            autobuy.assert_not_awaited()
        self.assertEqual(split_watch_utils.get_status("TEST")["accounts_bought"], ["A"])

    async def test_schedule_failure_flags_reconciliation_without_retry(self):
        boom = AsyncMock(side_effect=RuntimeError("send failed"))
        with patch.object(on_message, "attempt_autobuy", new=boom):
            await self._flow()
            await self._flow()
        boom.assert_awaited_once()
        unresolved = split_watch_utils.list_unresolved_events()
        self.assertEqual(unresolved[0]["state"], "needs_reconciliation")

    async def test_attempt_autobuy_persists_unique_intents_per_plan(self):
        split_watch_utils.claim_split_event("TEST", self.day)
        bot = MagicMock()
        bot.loop.create_task = MagicMock(side_effect=lambda coro: coro.close())
        config = {
            "standard_order": {"quantity": 1},
            "overrides": [{"broker": "fidelity", "quantity": 2}],
        }
        with patch.object(on_message, "schedule_and_execute", new=MagicMock()), patch(
            "utils.config_utils.load_autobuy_config", return_value=config
        ), patch.object(on_message, "is_market_open_at", return_value=True), patch.object(
            on_message, "resolve_message_destination", return_value=self.channel
        ):
            await on_message.attempt_autobuy(bot, self.channel, "TEST", 1, split_date=self.day)
            await on_message.attempt_autobuy(bot, self.channel, "TEST", 1, split_date=self.day)
        self.assertEqual(bot.loop.create_task.call_count, 2)
        from rsassistant.persistence import split_events

        event = split_events.get_split_event(
            "TEST", self.day, database=split_watch_utils.DATABASE_PATH
        )
        self.assertEqual(event["state"], "submitted")
        self.assertEqual({o["state"] for o in event["orders"]}, {"queued"})
