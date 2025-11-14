"""Adapters for communicating with the auto-rsa execution layer.

The :class:`TradeExecutor` class wraps auto-rsa's HTTP API so the trading
strategy can place market orders, attach take-profit and stop-loss orders, and
inspect current positions. The implementation intentionally keeps the surface
area small and synchronous—auto-rsa executes orders quickly and the Discord bot
runs in a single asyncio event loop, so blocking I/O is isolated to this
module.

The executor accepts a base URL and optional API token via configuration. Each
method will fall back to a dry-run mode when a base URL is not configured. This
allows the strategy logic and unit tests to exercise the execution paths
without requiring a live broker connection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import requests

logger = logging.getLogger(__name__)


@dataclass
class ExecutorResponse:
    """Container for responses returned by :class:`TradeExecutor`.

    Attributes:
        success: Whether the request was acknowledged.
        payload: Parsed JSON payload returned by auto-rsa when available.
        status_code: HTTP status code for diagnostics.
        error: Optional error message captured from the response or raised
            locally when running in dry-run mode.
    """

    success: bool
    payload: Optional[Dict[str, Any]] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


class TradeExecutor:
    """Execute trades by forwarding requests to auto-rsa.

    Parameters:
        base_url: HTTP endpoint for the auto-rsa service. When omitted the
            executor runs in dry-run mode and only logs the intent.
        api_key: Optional API key injected via ``Authorization`` header.
        timeout: Timeout in seconds for outbound HTTP requests.
        session: Optional :class:`requests.Session` instance that is reused for
            all calls. Supplying a session is helpful in tests.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()
        self._dry_run = not bool(self.base_url)
        if self._dry_run:
            logger.warning(
                "TradeExecutor initialised without base_url; running in dry-run mode."
            )

    # --- Public API -----------------------------------------------------
    def buy(self, symbol: str, amount: Union[float, int], use_percent: bool = True) -> ExecutorResponse:
        """Place a market buy order via auto-rsa.

        Args:
            symbol: Ticker symbol.
            amount: Either the cash amount or percentage of the portfolio to
                allocate.
            use_percent: When ``True`` the ``amount`` is treated as a fraction
                of the available equity (``1.0`` == 100%).
        """

        payload = {"symbol": symbol, "amount": amount, "use_percent": use_percent}
        return self._dispatch("POST", "/orders/buy", payload)

    def sell(self, symbol: str, amount_or_all: Union[float, int, str] = "all") -> ExecutorResponse:
        """Close a position for ``symbol``.

        Args:
            symbol: Ticker symbol to close.
            amount_or_all: Either ``"all"`` to liquidate or the quantity to
                reduce.
        """

        payload = {"symbol": symbol, "amount": amount_or_all}
        return self._dispatch("POST", "/orders/sell", payload)

    def set_tp_sl(self, symbol: str, take_profit: float, stop_loss: float) -> ExecutorResponse:
        """Attach take-profit and stop-loss orders for ``symbol``."""

        payload = {
            "symbol": symbol,
            "take_profit": round(take_profit, 4),
            "stop_loss": round(stop_loss, 4),
        }
        return self._dispatch("POST", "/orders/brackets", payload)

    def cancel_all(self, symbol: str) -> ExecutorResponse:
        """Cancel all open orders associated with ``symbol``."""

        payload = {"symbol": symbol}
        return self._dispatch("POST", "/orders/cancel", payload)

    def get_positions(self) -> ExecutorResponse:
        """Return current positions from auto-rsa."""

        return self._dispatch("GET", "/portfolio/positions")

    # --- Internal helpers -----------------------------------------------
    def _dispatch(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> ExecutorResponse:
        url = f"{self.base_url}{path}" if self.base_url else path
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self._dry_run:
            logger.info("[DRY-RUN] %s %s payload=%s", method, path, payload)
            return ExecutorResponse(success=True, payload=payload, status_code=None)

        try:
            response = self.session.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data: Optional[Dict[str, Any]]
            if response.content:
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    data = None
            else:
                data = None
            logger.debug("auto-rsa response (%s %s): %s", method, path, data)
            return ExecutorResponse(
                success=True, payload=data, status_code=response.status_code
            )
        except requests.RequestException as exc:  # pragma: no cover - network err
            logger.error("auto-rsa request failed: %s", exc)
            return ExecutorResponse(
                success=False,
                payload=None,
                status_code=getattr(exc.response, "status_code", None),
                error=str(exc),
            )


__all__ = ["TradeExecutor", "ExecutorResponse"]
