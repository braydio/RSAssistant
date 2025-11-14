"""Unit tests for the ULT-MA trading controller."""

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from utils.trading.market_data import Candle
from utils.trading.state import TradePosition, TradingStateStore
from utils.trading.ult_ma_bot import UltMaTradingBot


class DummyExecutor:
    """Collects executor calls for assertions."""

    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def buy(self, symbol, amount, use_percent=True):
        self.calls.append(("buy", symbol, amount, use_percent))

    def sell(self, symbol, amount_or_all="all"):
        self.calls.append(("sell", symbol, amount_or_all))

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
