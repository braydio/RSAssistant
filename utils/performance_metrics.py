"""Opt-in runtime resource metrics (TP-20261010-001).

Nothing here runs unless ``RESOURCE_METRICS_ENABLED`` is true. A single task
logs one structured summary per interval: CPU time, RSS, event-loop drift,
asyncio task count and call counters/durations. Counter names come from a
fixed allow-list so labels can never grow with tickers, accounts or URLs, and
no message text or payload is ever recorded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

ALLOWED_CALLS = frozenset({"holdings_import", "policy_resolution", "yfinance_batch"})
_OTHER = "other"
_DRIFT_PROBE_SECONDS = 0.05

_calls: dict[str, dict[str, float]] = {}
_task: asyncio.Task | None = None


def record_call(name: str, duration_seconds: float) -> None:
    """Count one outbound call and add its monotonic duration."""

    key = name if name in ALLOWED_CALLS else _OTHER
    entry = _calls.setdefault(key, {"count": 0, "seconds": 0.0})
    entry["count"] += 1
    entry["seconds"] += max(duration_seconds, 0.0)


@contextmanager
def timed_call(name: str) -> Iterator[None]:
    """Time the enclosed block and record it, even when it raises."""

    start = time.monotonic()
    try:
        yield
    finally:
        record_call(name, time.monotonic() - start)


def reset_calls() -> None:
    _calls.clear()


def read_rss_kib(path: str = "/proc/self/status") -> int | None:
    """Return resident set size in KiB, or ``None`` when unavailable."""

    try:
        with open(path, encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


async def measure_loop_drift_ms() -> float:
    """Return how late a short sleep wakes up, in milliseconds (≥ 0)."""

    loop = asyncio.get_running_loop()
    start = loop.time()
    await asyncio.sleep(_DRIFT_PROBE_SECONDS)
    return max((loop.time() - start - _DRIFT_PROBE_SECONDS) * 1000.0, 0.0)


async def collect_snapshot() -> dict[str, Any]:
    """Collect one metrics sample; never touches the network or any payload."""

    return {
        "cpu_seconds": time.process_time(),
        "uptime_seconds": time.monotonic(),
        "rss_kib": read_rss_kib(),
        "loop_drift_ms": await measure_loop_drift_ms(),
        "asyncio_tasks": len(asyncio.all_tasks()),
        "calls": {k: dict(v) for k, v in sorted(_calls.items())},
    }


def format_snapshot(snapshot: dict[str, Any]) -> str:
    rss = snapshot["rss_kib"]
    calls = " ".join(
        f"{name}={int(v['count'])}/{v['seconds']:.2f}s"
        for name, v in snapshot["calls"].items()
    )
    return (
        "resource_metrics "
        f"cpu_s={snapshot['cpu_seconds']:.2f} "
        f"rss_kib={'unavailable' if rss is None else rss} "
        f"loop_drift_ms={snapshot['loop_drift_ms']:.1f} "
        f"tasks={snapshot['asyncio_tasks']} "
        f"calls=[{calls or 'none'}]"
    )


async def run_metrics_loop(interval_seconds: float) -> None:
    """Log one summary per interval until cancelled."""

    interval = max(float(interval_seconds), 1.0)
    while True:
        try:
            await asyncio.sleep(interval)
            logger.info(format_snapshot(await collect_snapshot()))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Resource metrics sample failed.")


def start_metrics_task(enabled: bool, interval_seconds: float) -> asyncio.Task | None:
    """Start the single metrics task; ``None`` when disabled.

    Repeated calls (e.g. reconnects) return the already-running task.
    """

    global _task
    if not enabled:
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(run_metrics_loop(interval_seconds), name="resource-metrics")
    return _task
