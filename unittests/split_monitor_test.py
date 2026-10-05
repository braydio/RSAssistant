import asyncio
from types import SimpleNamespace

from rsassistant.bot.cogs import split_monitor


def test_split_orders_reads_sql_when_csv_is_unavailable(monkeypatch):
    ctx = SimpleNamespace(messages=[])
    async def send(message):
        ctx.messages.append(message)
    ctx.send = send
    monkeypatch.setattr(split_monitor.split_watch_utils, "get_status", lambda _ticker: None)
    monkeypatch.setattr(split_monitor, "list_order_history", lambda **kwargs: [{
        "broker_name": "Broker A", "broker_number": "1", "account_number": "1234",
        "action": "buy", "ticker": "ABC", "quantity": 2, "price": 4,
        "date": "2026-10-01", "timestamp": "2026-10-01 12:00:00",
    }])
    cog = split_monitor.SplitMonitorCog(SimpleNamespace())

    asyncio.run(cog.split_orders.callback(cog, ctx, "abc", None))

    history_message = next(message for message in ctx.messages if message.startswith("Order history"))
    assert "Buy count: 1" in history_message
    assert "Broker A" in history_message
