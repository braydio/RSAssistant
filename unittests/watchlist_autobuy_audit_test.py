"""Unit tests for watchlist autobuy queueing during ``..all`` audits."""

import unittest
from unittest.mock import patch

from rsassistant.bot.handlers import on_message


class WatchlistAutobuyAuditTest(unittest.IsolatedAsyncioTestCase):
    """Verify broker/ticker autobuy queue behavior during holdings audits."""

    def test_extract_order_queue_pairs_normalizes_entries(self):
        """Queued order pairs should normalize ticker and broker case."""

        with patch.object(
            on_message,
            "get_order_queue",
            return_value={
                "a": {"ticker": "abC", "broker": "schwab"},
                "b": {"ticker": "", "broker": "ignored"},
                "c": {"ticker": "TSLA", "broker": ""},
            },
        ):
            self.assertEqual(
                on_message._extract_order_queue_pairs(),
                {("ABC", "SCHWAB")},
            )

    async def test_queue_missing_watchlist_autobuys_skips_existing_pairs(self):
        """Queueing should skip broker/ticker pairs already present in queue."""

        sent_commands: list[str] = []

        async def fake_send(target, command, bot=None):
            sent_commands.append(command)

        with (
            patch.object(on_message, "AUTO_BUY_WATCHLIST", True),
            patch.object(on_message, "DISCORD_PRIMARY_CHANNEL", 0),
            patch.object(on_message, "resolve_reply_channel", return_value=None),
            patch.object(
                on_message,
                "resolve_message_destination",
                side_effect=lambda bot, channel: channel,
            ),
            patch.object(on_message, "send_sell_command", side_effect=fake_send),
            patch.object(on_message, "is_broker_ignored", return_value=False),
            patch.object(
                on_message,
                "get_order_queue",
                return_value={
                    "existing": {
                        "action": "buy",
                        "ticker": "AAA",
                        "broker": "SCHWAB",
                        "quantity": 1,
                        "time": "2099-01-01 09:30:00",
                    }
                },
            ),
        ):
            queued_count = await on_message.queue_missing_watchlist_autobuys(
                bot=None,
                channel=object(),
                missing_by_account={
                    "Schwab Main (1111)": ["AAA", "BBB"],
                    "Webull IRA (2222)": ["CCC"],
                },
            )

        self.assertEqual(queued_count, 2)
        self.assertEqual(
            sent_commands,
            [
                "!rsa buy 1 BBB SCHWAB false",
                "!rsa buy 1 CCC WEBULL false",
            ],
        )


if __name__ == "__main__":
    unittest.main()
