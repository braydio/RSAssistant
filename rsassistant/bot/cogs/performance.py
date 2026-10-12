"""Value-change visibility commands (TP-20261004-002)."""

from __future__ import annotations

import io
from datetime import datetime

import discord
from discord.ext import commands

from rsassistant.persistence.accounts import resolve_account_id, resolve_broker_account_ids
from rsassistant.services import performance as perf

_BASIS_LABELS = {
    "reported_total": "reported account totals",
    "positions_sum": "position values (no reported total)",
    "historical_positions_sum": "position values (older history)",
}


def _money(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    sign = "+" if signed and value >= 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def _ago(then: datetime, now: datetime) -> str:
    seconds = max(int((now - then).total_seconds()), 0)
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def format_summary(summary: dict, scope_label: str = "Portfolio") -> str:
    """Render a summary from :func:`get_performance_summary` as Discord text."""

    window = summary["window"].upper()
    if not summary.get("has_data"):
        return f"No value history recorded yet for {scope_label}."
    change, week, since = summary["change"], summary["change_7d"], summary["since_tracking"]
    lines = [
        f"**{scope_label} Value · {window}**",
        "```",
        f"Current value        {_money(summary['current_value']):>14}",
        f"{window} value change   {_money(change['change'], True):>14}",
        f"{window} change         {_pct(change['pct']):>14}",
    ]
    if summary["window"] != "7d":
        lines.append(f"7D value change      {_money(week['change'], True):>14}")
    if summary["window"] != "all":
        lines.append(f"Since tracking       {_money(since['change'], True):>14}")
    lines.append("```")
    if change["change"] is None:
        lines.append(
            f"Not enough history for {window}; earliest observation is "
            f"{summary['earliest_observed_at']:%b %d, %Y}."
        )
    start = change["comparison_observed_at"] or summary["earliest_observed_at"]
    lines += [
        f"**Coverage** {start:%b %d, %Y} → {summary['current_observed_at']:%b %d, %Y} · "
        f"{summary['account_count']} accounts · updated "
        f"{_ago(summary['current_observed_at'], summary['as_of'])}",
    ]
    if change["added_accounts"] or change["removed_accounts"]:
        lines.append(
            f"Compared on {change['common_accounts']} common accounts "
            f"(+{len(change['added_accounts'])} added, "
            f"-{len(change['removed_accounts'])} removed since the comparison point)."
        )
    basis = ", ".join(_BASIS_LABELS.get(b, b) for b in summary["basis"])
    lines.append(f"**Basis** {basis}" + (" · mixed" if summary["mixed_basis"] else ""))
    if len(summary["top_contributors"]) > 1:
        top = "; ".join(f"{c['name']} {_money(c['value'])}" for c in summary["top_contributors"])
        lines.append(f"**Top accounts** {top}")
    lines.append("*Value change only — deposits/withdrawals are not adjusted for.*")
    return "\n".join(lines)


def render_chart(points: list[dict], title: str) -> bytes | None:
    """Render the value series to PNG bytes; ``None`` if matplotlib is missing."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ModuleNotFoundError:
        return None
    fig, ax = plt.subplots(figsize=(10, 5))
    try:
        times = [p["time"] for p in points]
        values = [p["effective_value"] for p in points]
        ax.plot(times, values, marker="o" if len(points) < 40 else None, label="Account value")
        if any(abs(p["positions_value"] - p["effective_value"]) > 0.005 for p in points):
            ax.plot(times, [p["positions_value"] for p in points], linestyle="--",
                    alpha=0.6, label="Positions value")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
        for idx, align in ((0, "left"), (-1, "right")):
            ax.annotate(_money(values[idx]), (times[idx], values[idx]), ha=align,
                        textcoords="offset points", xytext=(0, 8), fontsize=9)
        footer = ""
        if any("historical_positions_sum" in p["basis"] for p in points) and any(
            "reported_total" in p["basis"] for p in points
        ):
            footer = "Basis changes from position values to reported totals during this range."
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend()
        if footer:
            fig.text(0.01, 0.01, footer, fontsize=8, alpha=0.7)
        fig.autofmt_xdate()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=110)
        return buffer.getvalue()
    finally:
        plt.close(fig)


def resolve_scope(token: str | None) -> tuple[list[int] | None, str]:
    """Resolve an account nickname/ID or broker name to (account_ids, label)."""

    if not token:
        return None, "Portfolio"
    account_id = resolve_account_id(token)
    if account_id is not None:
        return [account_id], token
    broker_ids = resolve_broker_account_ids(token)
    if broker_ids:
        return broker_ids, token
    raise LookupError(f"No account or broker matches '{token}'.")


class PerformanceCog(commands.Cog):
    """Portfolio value growth commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="performance",
        aliases=["perf", "growth"],
        help="Show account value change and a value history chart. "
        "Windows: " + ", ".join(perf.WINDOWS) + f" (default {perf.DEFAULT_WINDOW}).",
        usage="[window] [account-or-broker]",
        extras={"category": "Reporting"},
    )
    async def performance(self, ctx: commands.Context, *args: str) -> None:
        window, rest = perf.DEFAULT_WINDOW, list(args)
        if rest and rest[0].lower() in perf.WINDOWS:
            window = rest.pop(0).lower()
        try:
            account_ids, label = resolve_scope(" ".join(rest) or None)
            summary = perf.get_performance_summary(window, account_ids)
            points = perf.get_performance_series(window, account_ids)
        except (LookupError, ValueError) as exc:
            await ctx.send(str(exc))
            return
        text = format_summary(summary, label)
        png = render_chart(points, f"{label} value · {window.upper()}") if points else None
        if png:
            await ctx.send(text, file=discord.File(io.BytesIO(png), filename="performance.png"))
        else:
            await ctx.send(text)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PerformanceCog(bot))
