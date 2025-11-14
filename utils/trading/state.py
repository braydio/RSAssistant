"""Persistence helpers for the ULT-MA trading subsystem."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


@dataclass
class TradingSettings:
    """Runtime toggles stored in the database."""

    allow_extended_trend: bool = False
    trend_safeguard_enabled: bool = True
    logging_enabled: bool = True
    trailing_buffer: float = 0.03


@dataclass
class UltMaState:
    """Represents the last known indicator state."""

    last_color: Optional[str] = None
    previous_color: Optional[str] = None
    last_trade_direction: Optional[str] = None
    pending_color: Optional[str] = None
    pending_since: Optional[datetime] = None
    last_check_at: Optional[datetime] = None


@dataclass
class TradePosition:
    """Metadata for the active trade."""

    symbol: str
    direction: str
    entry_price: float
    quantity: float
    take_profit: float
    stop_loss: float
    opened_at: datetime
    trailing_stop: Optional[float] = None


class TradingStateStore:
    """Simple SQLite-backed store for trading state."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialised = False

    # ------------------------------------------------------------------
    def initialise(self) -> None:
        if self._initialised:
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS ult_ma_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_color TEXT,
                    previous_color TEXT,
                    last_trade_direction TEXT,
                    pending_color TEXT,
                    pending_since TEXT,
                    last_check_at TEXT
                );

                CREATE TABLE IF NOT EXISTS trade_position (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    symbol TEXT,
                    direction TEXT,
                    entry_price REAL,
                    quantity REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    opened_at TEXT,
                    trailing_stop REAL
                );

                CREATE TABLE IF NOT EXISTS trading_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pnl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL,
                    pnl REAL NOT NULL
                );
                """
            )
            conn.commit()
        self._initialised = True
        logger.debug("TradingStateStore initialised at %s", self.db_path)

    # ------------------------------------------------------------------
    def load_state(self) -> UltMaState:
        self.initialise()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT last_color, previous_color, last_trade_direction, pending_color, pending_since, last_check_at FROM ult_ma_state WHERE id = 1"
            ).fetchone()
            if not row:
                return UltMaState()
            pending_since = (
                datetime.strptime(row[4], ISO_FORMAT) if row[4] else None
            )
            last_check_at = (
                datetime.strptime(row[5], ISO_FORMAT) if row[5] else None
            )
            return UltMaState(
                last_color=row[0],
                previous_color=row[1],
                last_trade_direction=row[2],
                pending_color=row[3],
                pending_since=pending_since,
                last_check_at=last_check_at,
            )

    def save_state(self, state: UltMaState) -> None:
        self.initialise()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ult_ma_state (id, last_color, previous_color, last_trade_direction, pending_color, pending_since, last_check_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_color=excluded.last_color,
                    previous_color=excluded.previous_color,
                    last_trade_direction=excluded.last_trade_direction,
                    pending_color=excluded.pending_color,
                    pending_since=excluded.pending_since,
                    last_check_at=excluded.last_check_at
                """,
                (
                    state.last_color,
                    state.previous_color,
                    state.last_trade_direction,
                    state.pending_color,
                    state.pending_since.strftime(ISO_FORMAT)
                    if state.pending_since
                    else None,
                    state.last_check_at.strftime(ISO_FORMAT)
                    if state.last_check_at
                    else None,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    def load_settings(self) -> TradingSettings:
        self.initialise()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT payload FROM trading_settings WHERE id = 1"
            ).fetchone()
            if not row:
                settings = TradingSettings()
                self.save_settings(settings)
                return settings
            data = json.loads(row[0])
            return TradingSettings(**data)

    def save_settings(self, settings: TradingSettings) -> None:
        self.initialise()
        payload = json.dumps(asdict(settings))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trading_settings (id, payload)
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
                """,
                (payload,),
            )
            conn.commit()

    # ------------------------------------------------------------------
    def load_active_position(self) -> Optional[TradePosition]:
        self.initialise()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT symbol, direction, entry_price, quantity, take_profit, stop_loss, opened_at, trailing_stop FROM trade_position WHERE id = 1"
            ).fetchone()
            if not row:
                return None
            return TradePosition(
                symbol=row[0],
                direction=row[1],
                entry_price=row[2],
                quantity=row[3],
                take_profit=row[4],
                stop_loss=row[5],
                opened_at=datetime.strptime(row[6], ISO_FORMAT),
                trailing_stop=row[7],
            )

    def save_active_position(self, position: Optional[TradePosition]) -> None:
        self.initialise()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if position is None:
                cursor.execute("DELETE FROM trade_position WHERE id = 1")
            else:
                cursor.execute(
                    """
                    INSERT INTO trade_position (id, symbol, direction, entry_price, quantity, take_profit, stop_loss, opened_at, trailing_stop)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        symbol=excluded.symbol,
                        direction=excluded.direction,
                        entry_price=excluded.entry_price,
                        quantity=excluded.quantity,
                        take_profit=excluded.take_profit,
                        stop_loss=excluded.stop_loss,
                        opened_at=excluded.opened_at,
                        trailing_stop=excluded.trailing_stop
                    """,
                    (
                        position.symbol,
                        position.direction,
                        position.entry_price,
                        position.quantity,
                        position.take_profit,
                        position.stop_loss,
                        position.opened_at.strftime(ISO_FORMAT),
                        position.trailing_stop,
                    ),
                )
            conn.commit()

    # ------------------------------------------------------------------
    def record_closed_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        opened_at: datetime,
        closed_at: datetime,
    ) -> None:
        self.initialise()
        pnl = (exit_price - entry_price) * quantity
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pnl_history (symbol, direction, entry_price, exit_price, quantity, opened_at, closed_at, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    direction,
                    entry_price,
                    exit_price,
                    quantity,
                    opened_at.strftime(ISO_FORMAT),
                    closed_at.strftime(ISO_FORMAT),
                    pnl,
                ),
            )
            conn.commit()


__all__ = [
    "TradingStateStore",
    "TradingSettings",
    "UltMaState",
    "TradePosition",
]
