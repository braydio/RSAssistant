import sys
from types import SimpleNamespace
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import RSAssistant

"""Tests for the consolidated broker holdings summary produced by ``..all``."""


class DummyChannel:
    async def send(self, *args, **kwargs):
        pass


class DummyCtx:
    def __init__(self, channel):
        self.channel = channel
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class DummyEmbed:
    def __init__(self, title=None, color=None):
        self.title = title
        self.color = color
        self.fields = []
        self.footer = None

    def add_field(self, name=None, value=None, inline=None):
        self.fields.append((name, value, inline))

    def set_footer(self, text=None):
        self.footer = text


class DummyColor:
    @staticmethod
    def red():
        return "red"

    @staticmethod
    def blue():
        return "blue"


def test_all_command_consolidates_broker_checks(monkeypatch):
    channel = DummyChannel()
    ctx = DummyCtx(channel)

    # Patch Discord constructs
    monkeypatch.setattr(RSAssistant.discord, "Embed", DummyEmbed)
    monkeypatch.setattr(RSAssistant.discord, "Color", DummyColor)

    # Patch utility functions used in show_reminder
    async def dummy_clear(ctx):
        pass

    async def dummy_send_embed(channel):
        pass

    monkeypatch.setattr(RSAssistant, "clear_holdings", dummy_clear)
    monkeypatch.setattr(RSAssistant, "send_reminder_message_embed", dummy_send_embed)
    monkeypatch.setattr(RSAssistant, "enable_audit", lambda: None)
    monkeypatch.setattr(RSAssistant, "disable_audit", lambda: None)
    monkeypatch.setattr(RSAssistant, "get_audit_summary", lambda: {})

    # Patch bot helpers
    monkeypatch.setattr(RSAssistant.bot, "get_channel", lambda _id: channel)

    async def fake_wait_for(event, check, timeout):
        message = SimpleNamespace(
            channel=channel,
            author=SimpleNamespace(bot=True, name="AutoRSA"),
            content="All commands complete in all brokers",
        )
        assert check(message)
        return message

    monkeypatch.setattr(RSAssistant.bot, "wait_for", fake_wait_for)

    # Track calls to track_ticker_summary
    calls = []

    async def fake_track(ctx_arg, ticker_arg, collect=False, **kwargs):
        calls.append((ticker_arg, collect))
        return {"BrokerA": ("✅", 1, 1)}, "2023-01-01 00:00:00"

    monkeypatch.setattr(RSAssistant, "track_ticker_summary", fake_track)

    # Provide a fake watch list
    monkeypatch.setattr(
        RSAssistant.watch_list_manager,
        "get_watch_list",
        lambda: {"AAA": {}, "BBB": {}},
    )

    asyncio.run(RSAssistant.show_reminder(ctx))

    # track_ticker_summary called for each ticker with collect=True
    assert calls == [("AAA", True), ("BBB", True)]

    # A single summary embed should be sent
    embeds = [kw["embed"] for _, kw in ctx.sent if "embed" in kw]
    assert any(getattr(e, "title", None) == "Broker Holdings Check" for e in embeds)
    assert len(embeds) == 1
