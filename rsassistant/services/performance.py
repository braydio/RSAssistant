"""Account/portfolio value-change summaries and series (TP-20261004-002).

Everything here is *value change*, never investment return: deposits and
withdrawals are not modeled, so no time- or money-weighted return is claimed.

Comparison-boundary rules (``as_of`` defaults to now):

- ``1d``: the latest observation on an earlier calendar day than the newest one.
- ``7d``/``30d``/``90d``/``1y`` (7/30/90/365 days): the latest observation at or
  before ``as_of - N days``.
- ``ytd``: the latest observation at or before Jan 1 of ``as_of``'s year (the
  prior year-end baseline); if none exists, the earliest one after Jan 1.
- ``all``: the earliest observation.

An *observation* is one holdings refresh (``refresh_id``); backfilled
``historical:`` rows are grouped by ``observed_at`` instead. Changes are only
computed over accounts present in **both** endpoints (common accounts), so
newly added or removed accounts never look like growth; the difference is
reported in ``added_accounts``/``removed_accounts``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from rsassistant.persistence import performance as repo
from rsassistant.persistence.accounts import fetch_account_labels

WINDOWS: dict[str, int | None] = {
    "1d": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "ytd": None,
    "1y": 365,
    "all": None,
}
DEFAULT_WINDOW = "30d"


def normalize_window(window: str | None) -> str:
    key = (window or DEFAULT_WINDOW).strip().lower()
    if key not in WINDOWS:
        raise ValueError(
            f"Unknown window '{window}'. Choose from: {', '.join(WINDOWS)}."
        )
    return key


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "")).replace(tzinfo=None)


def _load_observations(
    account_ids: Iterable[int] | None, database=None
) -> list[dict[str, Any]]:
    """Group snapshots into observations, oldest first."""

    rows = repo.list_account_value_snapshots(
        account_ids=list(account_ids) if account_ids else None, database=database
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        refresh_id = str(row["refresh_id"])
        key = row["observed_at"] if refresh_id.startswith("historical:") else refresh_id
        obs = grouped.setdefault(key, {"time": None, "accounts": {}})
        ts = _parse_ts(row["observed_at"])
        if obs["time"] is None or ts > obs["time"]:
            obs["time"] = ts
        obs["accounts"][row["account_id"]] = row
    return sorted(grouped.values(), key=lambda o: o["time"])


def _comparison_observation(
    observations: list[dict[str, Any]], window: str, as_of: datetime
) -> dict[str, Any] | None:
    latest = observations[-1]
    if window == "all":
        return observations[0]
    if window == "1d":
        earlier = [o for o in observations if o["time"].date() < latest["time"].date()]
        return earlier[-1] if earlier else None
    if window == "ytd":
        jan1 = datetime(as_of.year, 1, 1)
        before = [o for o in observations if o["time"] <= jan1]
        if before:
            return before[-1]
        after = [o for o in observations if o["time"] > jan1 and o is not latest]
        return after[0] if after else None
    target = as_of - timedelta(days=WINDOWS[window])
    before = [o for o in observations if o["time"] <= target]
    return before[-1] if before else None


def _scope_total(obs: dict[str, Any], ids: Iterable[int], field: str) -> float:
    return sum(obs["accounts"][i][field] for i in ids)


def _change(latest, comparison, field="effective_value") -> dict[str, Any]:
    """Value change over accounts common to both endpoints."""

    empty = {"change": None, "pct": None, "start_value": None, "end_value": None,
             "added_accounts": [], "removed_accounts": [], "comparison_observed_at": None,
             "common_accounts": 0, "mixed_basis": False}
    if comparison is None:
        return empty
    cur_ids, cmp_ids = set(latest["accounts"]), set(comparison["accounts"])
    common = sorted(cur_ids & cmp_ids)
    result = dict(
        empty,
        added_accounts=sorted(cur_ids - cmp_ids),
        removed_accounts=sorted(cmp_ids - cur_ids),
        comparison_observed_at=comparison["time"],
        common_accounts=len(common),
    )
    if not common:
        return result
    bases = {latest["accounts"][i]["valuation_basis"] for i in common} | {
        comparison["accounts"][i]["valuation_basis"] for i in common
    }
    start = _scope_total(comparison, common, field)
    end = _scope_total(latest, common, field)
    result.update(
        start_value=start,
        end_value=end,
        change=end - start,
        pct=((end - start) / abs(start) * 100.0) if start else None,
        mixed_basis=len(bases) > 1,
    )
    return result


def _labels() -> dict[int, str]:
    return {int(e["account_id"]): e["account_nickname"] for e in fetch_account_labels()}


def get_performance_summary(
    window: str | None = None,
    account_ids: Iterable[int] | None = None,
    as_of: datetime | None = None,
    *,
    database=None,
) -> dict[str, Any]:
    """Summarize current value and value change for ``window`` over the scope."""

    window = normalize_window(window)
    as_of = as_of or datetime.now()
    observations = [o for o in _load_observations(account_ids, database) if o["time"] <= as_of]
    if not observations:
        return {"window": window, "has_data": False}

    latest, earliest = observations[-1], observations[0]
    main = _change(latest, _comparison_observation(observations, window, as_of))
    seven = main if window == "7d" else _change(
        latest, _comparison_observation(observations, "7d", as_of)
    )
    since = main if window == "all" else _change(latest, earliest if earliest is not latest else None)

    ids = list(latest["accounts"])
    labels = _labels()
    contributors = sorted(
        ({"account_id": i, "name": labels.get(i, f"Account {i}"),
          "value": latest["accounts"][i]["effective_value"]} for i in ids),
        key=lambda c: c["value"], reverse=True,
    )[:3]
    current_bases = {latest["accounts"][i]["valuation_basis"] for i in ids}
    all_bases = {a["valuation_basis"] for o in observations for a in o["accounts"].values()}

    return {
        "window": window,
        "has_data": True,
        "account_count": len(ids),
        "current_value": _scope_total(latest, ids, "effective_value"),
        "current_positions_value": _scope_total(latest, ids, "positions_value"),
        "current_observed_at": latest["time"],
        "earliest_observed_at": earliest["time"],
        "as_of": as_of,
        "current_coverage": sorted(ids),
        "comparison_coverage": sorted(_comparison_ids(observations, window, as_of)),
        "change": main,
        "change_7d": seven,
        "since_tracking": since,
        "top_contributors": contributors,
        "current_basis": sorted(current_bases),
        "basis": sorted(all_bases),
        "mixed_basis": len(all_bases) > 1 or main["mixed_basis"],
    }


def _comparison_ids(observations, window, as_of) -> list[int]:
    comparison = _comparison_observation(observations, window, as_of)
    return list(comparison["accounts"]) if comparison else []


def _downsample(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Display-only thinning: raw ≤120d, daily ≤2y, weekly ≤5y, else monthly."""

    if len(observations) < 2:
        return observations
    span = (observations[-1]["time"] - observations[0]["time"]).days
    if span <= 120:
        return observations
    if span <= 730:
        key = lambda o: o["time"].date()
    elif span <= 1825:
        key = lambda o: tuple(o["time"].isocalendar()[:2])
    else:
        key = lambda o: (o["time"].year, o["time"].month)
    kept: dict[Any, dict[str, Any]] = {}
    for obs in observations:
        kept[key(obs)] = obs  # last observation per bucket wins
    return list(kept.values())


def get_performance_series(
    window: str | None = None,
    account_ids: Iterable[int] | None = None,
    as_of: datetime | None = None,
    *,
    database=None,
) -> list[dict[str, Any]]:
    """Return chart points (``time``, ``effective_value``, ``positions_value``,
    ``account_count``, ``basis``) for the window, oldest first."""

    window = normalize_window(window)
    as_of = as_of or datetime.now()
    observations = [o for o in _load_observations(account_ids, database) if o["time"] <= as_of]
    if not observations:
        return []
    start = _comparison_observation(observations, window, as_of) or observations[0]
    observations = [o for o in observations if o["time"] >= start["time"]]
    points = []
    for obs in _downsample(observations):
        ids = list(obs["accounts"])
        bases = {a["valuation_basis"] for a in obs["accounts"].values()}
        points.append(
            {
                "time": obs["time"],
                "effective_value": _scope_total(obs, ids, "effective_value"),
                "positions_value": _scope_total(obs, ids, "positions_value"),
                "account_count": len(ids),
                "basis": sorted(bases),
            }
        )
    return points


__all__ = [
    "DEFAULT_WINDOW",
    "WINDOWS",
    "get_performance_series",
    "get_performance_summary",
    "normalize_window",
]
