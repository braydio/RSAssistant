"""Unit tests for the ULT-MA trading controller."""

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

STAGING_ROOT = Path(__file__).resolve().parents[3]
if str(STAGING_ROOT) not in sys.path:
    sys.path.insert(0, str(STAGING_ROOT))

from plugins.ultma.market_data import Candle
from plugins.ultma.state import TradePosition, TradingStateStore
from plugins.ultma.ult_ma_bot import UltMaTradingBot


class DummyExecutor:
    """Collects executor calls for assertions."""

    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def buy(self, symbol, amount, use_percent=True):
        self.calls.append(("buy", symbol, amount, use_percent))

    def sell(self, symbol, amount_or_all="all", broker=None):
        self.calls.append(("sell", symbol, amount_or_all, broker))

    def set_tp_sl(self, symbol, tp, sl):
        self.calls.append(("brackets", symbol, tp, sl))

    def cancel_all(self, symbol):
        self.calls.append(("cancel", symbol))


class StubDataProvider:
    def __init__(self, price_sequence: List[float]):
        self.candles = [
            Candle(timestamp=0, open=90, high=95, low=89, close=90),
            Candle(timestamp=1, open=95, high=100, low=94, close=95),
            Candle(timestamp=2, open=99, high=105, low=98, close=100),
        ]
        self.price_sequence = list(price_sequence)

    def fetch_candles(self, symbol: str, interval: str = "4h", range_: str = "1mo"):
        return self.candles

    def fetch_last_price(self, symbol: str):
        if self.price_sequence:
            return self.price_sequence.pop(0)
        return self.candles[-1].close


def _create_bot(tmp_path: Path, provider: StubDataProvider) -> UltMaTradingBot:
    store = TradingStateStore(tmp_path / "trading.db")
    executor = DummyExecutor()
    bot = UltMaTradingBot(
        executor=executor,
        state_store=store,
        data_provider=provider,
        candle_interval=timedelta(hours=4),
        price_check_interval=timedelta(minutes=5),
    )
    return bot


def test_color_flip_triggers_long_entry():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[100, 102])
        bot = _create_bot(Path(tmp), provider)
        store = bot.store
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        # Seed state with a previous red colour
        state = store.load_state()
        state.last_color = "red"
        state.previous_color = "red"
        store.save_state(state)

        base_ts = datetime.now(timezone.utc)
        asyncio.run(bot._evaluate_color("green", price=100, timestamp=base_ts))
        # First flip arms the safeguard, no trade
        assert not any(call[0] == "buy" for call in executor.calls)

        asyncio.run(
            bot._evaluate_color(
                "green", price=102, timestamp=base_ts + timedelta(hours=4)
            )
        )
        assert any(call[0] == "buy" and call[1] == "TQQQ" for call in executor.calls)
        position = store.load_active_position()
        assert position is not None
        assert position.symbol == "TQQQ"


def test_trend_safeguard_requires_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[100])
        bot = _create_bot(Path(tmp), provider)
        store = bot.store
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        state = store.load_state()
        state.last_color = "green"
        state.previous_color = "green"
        store.save_state(state)

        ts = datetime.now(timezone.utc)
        asyncio.run(bot._evaluate_color("red", price=90, timestamp=ts))
        assert not any(call[0] == "sell" for call in executor.calls)
        # Pending colour should be stored for confirmation
        pending_state = store.load_state()
        assert pending_state.pending_color == "red"
        assert pending_state.pending_since is not None


def test_take_profit_closes_position():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[111])
        bot = _create_bot(Path(tmp), provider)
        store = bot.store
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        position = TradePosition(
            symbol="TQQQ",
            direction="long",
            entry_price=100,
            quantity=1,
            take_profit=110,
            stop_loss=95,
            opened_at=datetime.now(timezone.utc),
        )
        store.save_active_position(position)

        asyncio.run(bot._check_position())
        assert any(call[0] == "sell" and call[1] == "TQQQ" for call in executor.calls)
        assert store.load_active_position() is None


def test_extended_trend_trailing_stop():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[112, 108])
        bot = _create_bot(Path(tmp), provider)
        store = bot.store
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        settings = store.load_settings()
        settings.allow_extended_trend = True
        settings.trailing_buffer = 0.03
        store.save_settings(settings)

        position = TradePosition(
            symbol="TQQQ",
            direction="long",
            entry_price=100,
            quantity=1,
            take_profit=110,
            stop_loss=95,
            opened_at=datetime.now(timezone.utc),
        )
        store.save_active_position(position)

        # First check should introduce a trailing stop instead of closing
        asyncio.run(bot._check_position())
        updated = store.load_active_position()
        assert updated is not None
        assert updated.trailing_stop is not None

        # Second check should close via trailing stop
        asyncio.run(bot._check_position())
        assert any(call[0] == "sell" and call[1] == "TQQQ" for call in executor.calls)
        assert store.load_active_position() is None


def test_execute_trade_uses_configured_brokers():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[100])
        bot = _create_bot(Path(tmp), provider)
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        bot._configured_brokers = ["Fidelity", "Schwab"]

        asyncio.run(
            bot._execute_trade(
                color="green",
                price=100,
                timestamp=datetime.now(timezone.utc),
            )
        )

        sell_calls = [call for call in executor.calls if call[0] == "sell"]
        assert sell_calls == [
            ("sell", "SQQQ", "all", "Fidelity"),
            ("sell", "SQQQ", "all", "Schwab"),
        ]


def test_execute_trade_defaults_to_all_when_no_brokers():
    with tempfile.TemporaryDirectory() as tmp:
        provider = StubDataProvider(price_sequence=[100])
        bot = _create_bot(Path(tmp), provider)
        executor: DummyExecutor = bot.executor  # type: ignore[assignment]

        bot._configured_brokers = []

        asyncio.run(
            bot._execute_trade(
                color="red",
                price=100,
                timestamp=datetime.now(timezone.utc),
            )
        )

        sell_calls = [call for call in executor.calls if call[0] == "sell"]
        assert sell_calls == [("sell", "TQQQ", "all", None)]


# --- TP-20261010-007: nonblocking market data -------------------------------
import threading
import time


class SlowProvider(StubDataProvider):
    def __init__(self, price_sequence, delay=0.2):
        super().__init__(price_sequence)
        self.delay = delay
        self.candle_calls = 0
        self.price_calls = 0
        self.threads = []

    def fetch_candles(self, symbol, interval="4h", range_="1mo"):
        self.candle_calls += 1
        self.threads.append(threading.get_ident())
        time.sleep(self.delay)
        return [
            Candle(timestamp=i, open=1, high=1, low=1, close=float(i + 1))
            for i in range(30)
        ]

    def fetch_last_price(self, symbol):
        self.price_calls += 1
        self.threads.append(threading.get_ident())
        time.sleep(self.delay)
        return 100.0


async def _ticks_during(coro):
    ticks = 0
    done = asyncio.Event()

    async def beat():
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    task = asyncio.create_task(beat())
    try:
        await coro
    finally:
        done.set()
        await task
    return ticks


def test_refresh_color_does_not_block_event_loop_and_caches_candles():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            provider = SlowProvider([], delay=0.2)
            bot = _create_bot(Path(tmp), provider)
            ticks = await _ticks_during(bot._refresh_color())
            assert ticks > 5
            assert provider.threads and threading.get_ident() not in provider.threads
            await bot._refresh_color()  # same candle interval: served from cache
            assert provider.candle_calls == 1

    asyncio.run(run())


def test_overlapping_cycles_are_skipped():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            provider = SlowProvider([], delay=0.2)
            bot = _create_bot(Path(tmp), provider)
            await asyncio.gather(bot._refresh_color(), bot._refresh_color())
            assert provider.candle_calls == 1

    asyncio.run(run())


def test_idle_position_check_makes_no_fetch_and_exit_price_never_cached():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            provider = SlowProvider([], delay=0.05)
            bot = _create_bot(Path(tmp), provider)
            await bot._check_position()
            assert provider.price_calls == 0
            bot.store.save_active_position(
                TradePosition(
                    symbol="TQQQ", direction="long", entry_price=100.0, quantity=1.0,
                    take_profit=1000.0, stop_loss=1.0, opened_at=datetime.now(timezone.utc),
                )
            )
            await bot._check_position()
            await bot._check_position()
            assert provider.price_calls == 2  # every check fetches a fresh quote

    asyncio.run(run())


def test_force_entry_fetch_off_loop_and_stop_cancels_tasks():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            provider = SlowProvider([], delay=0.2)
            bot = _create_bot(Path(tmp), provider)
            ticks = await _ticks_during(bot.force_entry("long"))
            assert ticks > 5
            await bot.start()
            await bot.stop()
            assert bot._monitor_task.done() and bot._position_task.done()

    asyncio.run(run())


def test_fetch_errors_counted_without_payload():
    class Boom(StubDataProvider):
        def fetch_candles(self, *a, **k):
            raise RuntimeError("SECRET-PAYLOAD")

    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            bot = _create_bot(Path(tmp), Boom([]))
            try:
                await bot._refresh_color()
            except RuntimeError:
                pass
            assert bot.fetch_error_count == 1

    asyncio.run(run())
