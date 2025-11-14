"""Asynchronous controller for the ULT-MA automated trading mode."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Union

from .executor import TradeExecutor
from .market_data import YahooMarketDataProvider
from .state import TradePosition, TradingSettings, TradingStateStore
from ..config_utils import TRADING_BROKERS

logger = logging.getLogger(__name__)

TZ_UTC = timezone.utc


@dataclass
class StrategyMetrics:
    """Light-weight snapshot used by the Discord UI."""

    last_color: Optional[str]
    previous_color: Optional[str]
    last_trade_direction: Optional[str]
    next_check_at: Optional[datetime]
    paused: bool


class UltMaTradingBot:
    """Implements the ULT-MA strategy as an optional task inside RSAssistant."""

    def __init__(
        self,
        executor: TradeExecutor,
        state_store: TradingStateStore,
        data_provider: Optional[YahooMarketDataProvider] = None,
        candle_interval: timedelta = timedelta(hours=4),
        price_check_interval: timedelta = timedelta(minutes=5),
        trailing_buffer: float = 0.03,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.executor = executor
        self.store = state_store
        self.data = data_provider or YahooMarketDataProvider()
        self.candle_interval = candle_interval
        self.price_check_interval = price_check_interval
        self.trailing_buffer = trailing_buffer
        self.on_error = on_error
        self._configured_brokers = list(TRADING_BROKERS)

        self._monitor_task: Optional[asyncio.Task] = None
        self._position_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._paused = False
        self._next_check_at: Optional[datetime] = None
        self._webhook_color: Optional[str] = None
        self._webhook_timestamp: Optional[datetime] = None

        self.store.initialise()
        settings = self.store.load_settings()
        settings.trailing_buffer = trailing_buffer
        self.store.save_settings(settings)

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Start background monitoring tasks."""

        if self._monitor_task and not self._monitor_task.done():
            return
        self._stop_event.clear()
        loop = asyncio.get_running_loop()
        self._monitor_task = loop.create_task(
            self._monitor_loop(), name="ult-ma-monitor"
        )
        self._position_task = loop.create_task(
            self._position_loop(), name="ult-ma-position"
        )
        logger.info("ULT-MA trading bot tasks started.")

    async def stop(self) -> None:
        """Stop background monitoring tasks."""

        self._stop_event.set()
        for task in (self._monitor_task, self._position_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("ULT-MA trading bot tasks stopped.")

    # ------------------------------------------------------------------
    def pause(self) -> None:
        self._paused = True
        logger.info("ULT-MA trading bot paused.")

    def resume(self) -> None:
        self._paused = False
        logger.info("ULT-MA trading bot resumed.")

    # ------------------------------------------------------------------
    def toggle_trend_safeguard(self) -> TradingSettings:
        settings = self.store.load_settings()
        settings.trend_safeguard_enabled = not settings.trend_safeguard_enabled
        self.store.save_settings(settings)
        return settings

    def toggle_extended_trend(self) -> TradingSettings:
        settings = self.store.load_settings()
        settings.allow_extended_trend = not settings.allow_extended_trend
        self.store.save_settings(settings)
        return settings

    def toggle_logging(self) -> TradingSettings:
        settings = self.store.load_settings()
        settings.logging_enabled = not settings.logging_enabled
        self.store.save_settings(settings)
        return settings

    # ------------------------------------------------------------------
    def update_color_from_webhook(self, color: str, timestamp: datetime) -> None:
        """Record the latest TradingView colour for optional webhook integration."""

        normalized = color.lower()
        if normalized not in {"green", "red"}:
            logger.warning("Ignoring webhook colour %s", color)
            return
        self._webhook_color = normalized
        self._webhook_timestamp = timestamp.astimezone(TZ_UTC)

    # ------------------------------------------------------------------
    def metrics(self) -> StrategyMetrics:
        state = self.store.load_state()
        return StrategyMetrics(
            last_color=state.last_color,
            previous_color=state.previous_color,
            last_trade_direction=state.last_trade_direction,
            next_check_at=self._next_check_at,
            paused=self._paused,
        )

    def active_position(self) -> Optional[TradePosition]:
        return self.store.load_active_position()

    # ------------------------------------------------------------------
    async def force_entry(self, direction: str) -> None:
        direction = direction.lower()
        if direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        symbol = "TQQQ" if direction == "long" else "SQQQ"
        price = self.data.fetch_last_price(symbol)
        if price is None:
            raise RuntimeError(f"Failed to fetch price for {symbol}")
        color = "green" if direction == "long" else "red"
        await self._evaluate_color(color, price, datetime.now(TZ_UTC), forced=True)

    # ------------------------------------------------------------------
    async def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not self._paused:
                    await self._refresh_color()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("ULT-MA monitor loop error: %s", exc)
                if self.on_error:
                    self.on_error(str(exc))
            await asyncio.sleep(self.candle_interval.total_seconds())

    async def _position_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not self._paused:
                    await self._check_position()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("ULT-MA position loop error: %s", exc)
                if self.on_error:
                    self.on_error(str(exc))
            await asyncio.sleep(self.price_check_interval.total_seconds())

    # ------------------------------------------------------------------
    async def _refresh_color(self) -> None:
        timestamp = datetime.now(TZ_UTC)
        color, price = self._determine_color()
        if color is None or price is None:
            logger.debug("Colour detection returned no signal.")
            return
        await self._evaluate_color(color, price, timestamp)

    async def _evaluate_color(
        self, color: str, price: float, timestamp: datetime, forced: bool = False
    ) -> None:
        state = self.store.load_state()
        settings = self.store.load_settings()
        state.last_check_at = timestamp

        if color not in {"green", "red"}:
            logger.debug("Invalid colour %s", color)
            return

        if state.last_color is None:
            state.last_color = color
            state.previous_color = color
            state.pending_color = None
            state.pending_since = None
            self.store.save_state(state)
            logger.info("Initialised ULT-MA state with colour %s", color)
            return

        if state.last_color == color:
            state.pending_color = None
            state.pending_since = None
            self.store.save_state(state)
            return

        confirmation_required = settings.trend_safeguard_enabled and not forced
        confirmation_ready = False
        if confirmation_required:
            if state.pending_color == color:
                if (
                    state.pending_since
                    and timestamp - state.pending_since >= self.candle_interval
                ):
                    confirmation_ready = True
                else:
                    logger.info(
                        "Trend safeguard awaiting confirmation candle for %s", color
                    )
            else:
                state.pending_color = color
                state.pending_since = timestamp
                self.store.save_state(state)
                logger.info("Trend safeguard armed for %s", color)
                return
        else:
            confirmation_ready = True

        if not confirmation_ready:
            self.store.save_state(state)
            return

        logger.info("Colour flip detected: %s -> %s", state.last_color, color)
        previous_color = state.last_color
        state.previous_color = previous_color
        state.last_color = color
        state.pending_color = None
        state.pending_since = None
        state.last_trade_direction = "long" if color == "green" else "short"
        self.store.save_state(state)

        await self._execute_trade(color=color, price=price, timestamp=timestamp)

    async def _execute_trade(
        self, color: str, price: float, timestamp: datetime
    ) -> None:
        target_symbol = "TQQQ" if color == "green" else "SQQQ"
        opposite_symbol = "SQQQ" if target_symbol == "TQQQ" else "TQQQ"

        active = self.store.load_active_position()
        if active and active.symbol == target_symbol:
            logger.info(
                "Position for %s already active; skipping duplicate entry.",
                target_symbol,
            )
            return

        if active and active.symbol == opposite_symbol:
            await self._close_position(price, reason="colour flip")

        self.executor.cancel_all(target_symbol)
        self.executor.cancel_all(opposite_symbol)

        tp = price * 1.10
        sl = price * 0.95
        logger.info(
            "Opening %s position at price %.2f with TP %.2f and SL %.2f",
            target_symbol,
            price,
            tp,
            sl,
        )
        self._sell_across_brokers(opposite_symbol, "all")
        self.executor.buy(target_symbol, 1.0, use_percent=True)
        self.executor.set_tp_sl(target_symbol, tp, sl)

        position = TradePosition(
            symbol=target_symbol,
            direction="long" if color == "green" else "short",
            entry_price=price,
            quantity=1.0,
            take_profit=tp,
            stop_loss=sl,
            opened_at=timestamp,
        )
        self.store.save_active_position(position)
        logger.info("Stored new active position for %s", target_symbol)

    async def _check_position(self) -> None:
        position = self.store.load_active_position()
        if not position:
            return
        price = self.data.fetch_last_price(position.symbol)
        if price is None:
            logger.debug("Unable to retrieve price for %s", position.symbol)
            return
        settings = self.store.load_settings()
        hit_tp = price >= position.take_profit
        hit_sl = price <= position.stop_loss
        if hit_tp and settings.allow_extended_trend:
            new_trailing = price * (1 - settings.trailing_buffer)
            if position.trailing_stop is None or new_trailing > position.trailing_stop:
                position.trailing_stop = new_trailing
                self.store.save_active_position(position)
                logger.info(
                    "Extended trend enabled for %s – trailing stop moved to %.2f",
                    position.symbol,
                    new_trailing,
                )
                return
        if position.trailing_stop is not None and price <= position.trailing_stop:
            logger.info(
                "Trailing stop triggered for %s at %.2f (stop %.2f)",
                position.symbol,
                price,
                position.trailing_stop,
            )
            await self._close_position(price, reason="trailing stop")
            return
        if hit_tp or hit_sl:
            reason = "take profit" if hit_tp else "stop loss"
            logger.info("%s hit for %s at %.2f", reason, position.symbol, price)
            await self._close_position(price, reason=reason)

    async def _close_position(self, price: float, reason: str) -> None:
        position = self.store.load_active_position()
        if not position:
            return
        logger.info("Closing %s due to %s", position.symbol, reason)
        self._sell_across_brokers(position.symbol, "all")
        self.executor.cancel_all(position.symbol)
        self.store.record_closed_position(
            symbol=position.symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=price,
            quantity=position.quantity,
            opened_at=position.opened_at,
            closed_at=datetime.now(TZ_UTC),
        )
        self.store.save_active_position(None)

    # ------------------------------------------------------------------
    def _sell_across_brokers(
        self, symbol: str, amount: Union[float, int, str] = "all"
    ) -> None:
        """Dispatch sell requests to the configured brokers.

        When :data:`TRADING_BROKERS` is configured the executor receives one
        sell command per broker with the broker identifier included in the
        payload. When no brokers are configured the legacy behaviour of
        targeting ``"all"`` is preserved by issuing a single unqualified
        sell request.
        """

        brokers = self._configured_brokers or [None]
        for broker in brokers:
            self.executor.sell(symbol, amount, broker=broker)

    # ------------------------------------------------------------------
    def _determine_color(self) -> tuple[Optional[str], Optional[float]]:
        if self._webhook_color and self._webhook_timestamp:
            if (
                datetime.now(TZ_UTC) - self._webhook_timestamp
                < self.candle_interval * 2
            ):
                symbol = "TQQQ" if self._webhook_color == "green" else "SQQQ"
                price = self.data.fetch_last_price(symbol)
                return self._webhook_color, price
        candles = self.data.fetch_candles("TQQQ", interval="4h", range_="1mo")
        if not candles:
            return None, None
        closes = [c.close for c in candles if c.close]
        if len(closes) < 10:
            return None, None
        fast = sum(closes[-7:]) / 7
        slow = sum(closes[-21:]) / 21
        color = "green" if fast >= slow else "red"
        price = closes[-1]
        self._next_check_at = datetime.now(TZ_UTC) + self.candle_interval
        return color, price


__all__ = ["UltMaTradingBot", "StrategyMetrics"]
