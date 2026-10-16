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


def test_split_status_does_not_delete_open_overdue_watch(tmp_path, monkeypatch):
    from datetime import date, timedelta
    from pathlib import Path

    from utils import split_watch_utils as sw

    monkeypatch.setattr(sw, "DATABASE_PATH", tmp_path / "r.db")
    monkeypatch.setattr(sw, "SPLIT_WATCH_FILE", Path(tmp_path) / "none.json")
    past = (date.today() - timedelta(days=2)).isoformat()
    sw.add_split_watch("OLD", past)
    sw.mark_account_bought("OLD", "A")
    sw.update_split_status()
    ctx = SimpleNamespace(messages=[])

    async def send(message):
        ctx.messages.append(message)

    ctx.send = send
    cog = split_monitor.SplitMonitorCog(SimpleNamespace())
    asyncio.run(cog.split_status.callback(cog, ctx, "old"))
    asyncio.run(cog.split_list.callback(cog, ctx))
    asyncio.run(cog.split_cleanup.callback(cog, ctx))
    assert "Phase: overdue" in ctx.messages[0]
    assert "(overdue)" in ctx.messages[1]
    assert "1 need attention" in ctx.messages[2]
    assert sw.get_status("OLD")["accounts_bought"] == ["A"]
