"""Tests for sell queue command helpers."""

import asyncio

import RSAssistant


class DummyCtx:
    """Capture messages sent during command execution."""

    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):  # noqa: D401 - simple passthrough
        """Store outbound Discord messages for later assertions."""

        self.messages.append(message)


def test_remove_sell_order_success(monkeypatch):
    """The command should remove an existing ticker from the sell list."""

    ctx = DummyCtx()
    recorded = []

    def fake_remove(ticker):
        recorded.append(ticker)
        return True

    monkeypatch.setattr(
        RSAssistant.watch_list_manager,
        "remove_from_sell_list",
        fake_remove,
    )

    asyncio.run(RSAssistant.remove_sell_order(ctx, "abc"))

    assert recorded == ["ABC"]
    assert ctx.messages == ["ABC removed from the sell list."]


def test_remove_sell_order_not_found(monkeypatch):
    """The command should report when the ticker is not queued."""

    ctx = DummyCtx()
    monkeypatch.setattr(
        RSAssistant.watch_list_manager,
        "remove_from_sell_list",
        lambda ticker: False,
    )

    asyncio.run(RSAssistant.remove_sell_order(ctx, "xyz"))

    assert ctx.messages == ["XYZ was not found in the sell list."]
