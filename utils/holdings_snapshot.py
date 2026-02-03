"""Holdings snapshot helpers for Discord output."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

import discord

from utils.config_utils import HOLDINGS_LOG_CSV, get_account_nickname_or_default
from utils.csv_utils import load_csv_log


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _format_currency(value: float) -> str:
    return f"${value:,.2f}"


def _truncate_lines(lines: Iterable[str], max_chars: int) -> str:
    rendered = "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    trimmed = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > max_chars:
            trimmed.append("…")
            break
        trimmed.append(line)
        total += len(line) + 1
    return "\n".join(trimmed)


def build_holdings_snapshot_embeds(
    broker_filter: str | None = None, top_n: int = 5
) -> tuple[list[discord.Embed], str | None]:
    rows = load_csv_log(HOLDINGS_LOG_CSV)
    if not rows:
        return [], "No holdings snapshot found. Run `!rsa holdings` or import a holdings file."

    broker_filter_norm = broker_filter.lower().strip() if broker_filter else None
    if broker_filter_norm in {"all", "*"}:
        broker_filter_norm = None

    account_totals: dict[tuple[str, str, str], float] = {}
    account_position_sums: dict[tuple[str, str, str], float] = defaultdict(float)
    broker_accounts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    broker_positions: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    latest_ts: datetime | None = None

    for row in rows:
        broker = str(row.get("Broker Name", "")).strip()
        if not broker:
            continue
        if broker_filter_norm and broker.lower() != broker_filter_norm:
            continue

        group = str(row.get("Broker Number", "")).strip()
        account = str(row.get("Account Number", "")).strip()
        account_key = (broker, group, account)
        broker_accounts[broker].add(account_key)

        ticker = str(row.get("Stock", "")).strip().upper()
        quantity = _parse_float(row.get("Quantity"))
        price = _parse_float(row.get("Price"))
        position_value = _parse_float(row.get("Position Value"))
        if position_value <= 0:
            position_value = max(quantity * price, 0.0)

        if ticker:
            broker_positions[broker][ticker] += position_value
        account_position_sums[account_key] += position_value

        account_total = _parse_float(row.get("Account Total"))
        if account_total > 0:
            existing = account_totals.get(account_key)
            if existing is None or account_total > existing:
                account_totals[account_key] = account_total

        ts = _parse_timestamp(row.get("Timestamp"))
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    for account_key, total in account_position_sums.items():
        if account_totals.get(account_key, 0.0) <= 0:
            account_totals[account_key] = total

    if not broker_accounts:
        return [], "No holdings matched that broker filter."

    embeds: list[discord.Embed] = []
    timestamp_label = latest_ts.strftime("%Y-%m-%d %H:%M:%S") if latest_ts else "Unknown"

    brokers = sorted(broker_accounts.keys(), key=str.lower)
    if broker_filter_norm:
        broker_name = brokers[0]
        broker_total = sum(
            account_totals.get(account_key, 0.0)
            for account_key in broker_accounts[broker_name]
        )
        positions = broker_positions[broker_name]
        top_positions = sorted(positions.items(), key=lambda x: x[1], reverse=True)
        top_positions = top_positions[: max(1, top_n)]

        embed = discord.Embed(
            title=f"Holdings Snapshot • {broker_name}",
            color=discord.Color.blue(),
        )
        embed.description = (
            f"Accounts: {len(broker_accounts[broker_name])} • "
            f"Positions: {len(positions)} • Total: {_format_currency(broker_total)}"
        )

        account_lines = []
        for account_key in sorted(
            broker_accounts[broker_name],
            key=lambda k: account_totals.get(k, 0.0),
            reverse=True,
        ):
            nickname = get_account_nickname_or_default(
                account_key[0], account_key[1], account_key[2]
            )
            total = account_totals.get(account_key, 0.0)
            account_lines.append(f"{nickname}: {_format_currency(total)}")

        embed.add_field(
            name="Accounts",
            value=_truncate_lines(account_lines, 900) if account_lines else "No accounts",
            inline=False,
        )

        if top_positions:
            top_lines = [f"{ticker}: {_format_currency(value)}" for ticker, value in top_positions]
            embed.add_field(
                name=f"Top Positions (Top {len(top_positions)})",
                value=_truncate_lines(top_lines, 900),
                inline=False,
            )

        embed.set_footer(text=f"Holdings snapshot • {timestamp_label}")
        embeds.append(embed)
        return embeds, None

    chunk_size = 9
    for i in range(0, len(brokers), chunk_size):
        embed = discord.Embed(title="Holdings Snapshot", color=discord.Color.blue())
        for broker in brokers[i : i + chunk_size]:
            positions = broker_positions[broker]
            broker_total = sum(
                account_totals.get(account_key, 0.0)
                for account_key in broker_accounts[broker]
            )
            top_positions = sorted(positions.items(), key=lambda x: x[1], reverse=True)
            top_positions = top_positions[: max(1, top_n)]
            top_line = " • ".join(
                [f"{ticker} {_format_currency(value)}" for ticker, value in top_positions]
            )
            summary_lines = [
                f"Accounts: {len(broker_accounts[broker])}",
                f"Positions: {len(positions)}",
                f"Total: {_format_currency(broker_total)}",
            ]
            if top_line:
                summary_lines.append(f"Top: {top_line}")

            embed.add_field(
                name=broker,
                value=_truncate_lines(summary_lines, 900),
                inline=False,
            )

        embed.set_footer(text=f"Holdings snapshot • {timestamp_label}")
        embeds.append(embed)

    return embeds, None
