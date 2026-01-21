"""Discord channel resolution helpers.

This module centralizes logic for picking the most appropriate Discord
channel when sending responses. It respects the configured primary,
secondary, and tertiary channel IDs defined via environment variables while
providing sensible fallbacks when some IDs are omitted.
"""

from __future__ import annotations

from typing import Iterable, Optional

from discord.ext import commands
from discord.abc import Messageable

from utils import config_utils


def _configured_channel_ids() -> tuple[int, ...]:
    """Return the configured channel IDs in priority order.

    The order favors the primary, then secondary, then tertiary channel as
    specified in the environment. Duplicate IDs are collapsed while preserving
    order so downstream consumers can iterate without additional guards.
    """

    ordered_ids: list[int] = []
    seen: set[int] = set()
    for channel_id in (
        config_utils.DISCORD_PRIMARY_CHANNEL,
        config_utils.DISCORD_SECONDARY_CHANNEL,
        config_utils.DISCORD_TERTIARY_CHANNEL,
    ):
        if isinstance(channel_id, int) and channel_id > 0 and channel_id not in seen:
            ordered_ids.append(channel_id)
            seen.add(channel_id)
    return tuple(ordered_ids)


def _iter_preferred_ids(preferred_id: Optional[int]) -> Iterable[int]:
    """Yield channel IDs prioritizing ``preferred_id`` when provided."""

    seen: set[int] = set()
    if isinstance(preferred_id, int) and preferred_id > 0:
        seen.add(preferred_id)
        yield preferred_id

    for channel_id in _configured_channel_ids():
        if channel_id not in seen:
            seen.add(channel_id)
            yield channel_id


def resolve_reply_channel(
    bot: commands.Bot, preferred_id: Optional[int] = None
):
    """Return the best available Discord channel for responses.

    Parameters
    ----------
    bot:
        The Discord bot instance used to locate channels.
    preferred_id:
        Optional channel ID to attempt first before falling back to configured
        IDs.

    Returns
    -------
    Optional[Messageable]
        The resolved channel object or ``None`` when no configured channel can
        be located.
    """

    for channel_id in _iter_preferred_ids(preferred_id):
        channel = bot.get_channel(channel_id)
        if channel is not None:
            return channel
    return None


def resolve_message_destination(
    bot: commands.Bot, message_channel: Optional[Messageable]
) -> Messageable:
    """Determine where to send a reply for a received message.

    Parameters
    ----------
    bot:
        The Discord bot instance used to resolve configured channels.
    message_channel:
        The original channel associated with the inbound message.

    Returns
    -------
    Messageable
        The channel where the bot should send its response. When no configured
        channel can be found, the original ``message_channel`` is returned to
        avoid dropping the reply entirely.
    """

    preferred_id = getattr(message_channel, "id", None)
    channel = resolve_reply_channel(bot, preferred_id=preferred_id)
    if channel is not None:
        return channel
    if message_channel is not None:
        return message_channel

    fallback_channel = resolve_reply_channel(bot)
    if fallback_channel is not None:
        return fallback_channel

    raise RuntimeError("No channel available for message response")
