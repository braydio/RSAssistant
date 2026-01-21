"""Unit tests for :mod:`rsassistant.bot.channel_resolver`."""

import unittest

from utils import config_utils


class DummyChannel:
    """Minimal stand-in for a Discord channel."""

    def __init__(self, channel_id):
        self.id = channel_id


class DummyBot:
    """Bot stub exposing :meth:`get_channel` for resolver tests."""

    def __init__(self, channels):
        self._channels = channels

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class ChannelResolverTest(unittest.TestCase):
    """Validate channel resolution fallbacks across configurations."""

    def setUp(self):
        self._original_primary = config_utils.DISCORD_PRIMARY_CHANNEL
        self._original_secondary = config_utils.DISCORD_SECONDARY_CHANNEL
        self._original_tertiary = config_utils.DISCORD_TERTIARY_CHANNEL

        from rsassistant.bot import channel_resolver

        self.resolver = channel_resolver

        self.addCleanup(self._restore_config)

    def _restore_config(self):
        config_utils.DISCORD_PRIMARY_CHANNEL = self._original_primary
        config_utils.DISCORD_SECONDARY_CHANNEL = self._original_secondary
        config_utils.DISCORD_TERTIARY_CHANNEL = self._original_tertiary

    def test_single_configured_channel_used_for_all_responses(self):
        config_utils.DISCORD_PRIMARY_CHANNEL = 101
        config_utils.DISCORD_SECONDARY_CHANNEL = 0
        config_utils.DISCORD_TERTIARY_CHANNEL = 0

        primary_channel = DummyChannel(101)
        bot = DummyBot({101: primary_channel})

        # Message arrives on a different channel; reply should target the only configured one.
        fallback = self.resolver.resolve_message_destination(bot, DummyChannel(999))
        self.assertIs(fallback, primary_channel)

        resolved = self.resolver.resolve_reply_channel(bot)
        self.assertIs(resolved, primary_channel)

    def test_preferred_channel_matches_message_when_configured(self):
        config_utils.DISCORD_PRIMARY_CHANNEL = 101
        config_utils.DISCORD_SECONDARY_CHANNEL = 202
        config_utils.DISCORD_TERTIARY_CHANNEL = 0

        primary_channel = DummyChannel(101)
        secondary_channel = DummyChannel(202)
        bot = DummyBot({101: primary_channel, 202: secondary_channel})

        destination = self.resolver.resolve_message_destination(bot, secondary_channel)
        self.assertIs(destination, secondary_channel)

    def test_resolver_falls_back_to_secondary_when_primary_missing(self):
        config_utils.DISCORD_PRIMARY_CHANNEL = 0
        config_utils.DISCORD_SECONDARY_CHANNEL = 202
        config_utils.DISCORD_TERTIARY_CHANNEL = 0

        secondary_channel = DummyChannel(202)
        bot = DummyBot({202: secondary_channel})

        destination = self.resolver.resolve_reply_channel(bot)
        self.assertIs(destination, secondary_channel)

    def test_message_destination_returns_original_when_no_configured_channels(self):
        config_utils.DISCORD_PRIMARY_CHANNEL = 0
        config_utils.DISCORD_SECONDARY_CHANNEL = 0
        config_utils.DISCORD_TERTIARY_CHANNEL = 0

        message_channel = DummyChannel(404)
        bot = DummyBot({})

        destination = self.resolver.resolve_message_destination(bot, message_channel)
        self.assertIs(destination, message_channel)


if __name__ == "__main__":
    unittest.main()
