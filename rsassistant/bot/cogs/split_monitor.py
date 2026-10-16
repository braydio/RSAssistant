"""Reverse split monitoring commands."""

from __future__ import annotations

import datetime

from discord.ext import commands
from utils.discord_permissions import operator_only

from utils import split_watch_utils
from rsassistant.persistence.orders import list_order_history


class SplitMonitorCog(commands.Cog):
    """Commands for tracking reverse-split watch entries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @operator_only()
    @commands.command(
        name="splitwatch",
        aliases=["sw"],
        help="Add a ticker to the reverse-split watchlist.",
        usage="<ticker> <yyyy-mm-dd>",
        extras={"category": "Split Monitor"},
    )
    async def add_split_watch(self, ctx: commands.Context, ticker: str, split_date: str) -> None:
        try:
            datetime.datetime.strptime(split_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("Invalid date format. Please use YYYY-MM-DD.")
            return

        split_watch_utils.add_split_watch(ticker, split_date)
        await ctx.send(f"Tracking {ticker.upper()} for reverse split on {split_date}.")

    @commands.command(
        name="splitstatus",
        aliases=["ss"],
        help="Show reverse-split progress for a ticker.",
        usage="<ticker>",
        extras={"category": "Split Monitor"},
    )
    async def split_status(self, ctx: commands.Context, ticker: str) -> None:
        status = split_watch_utils.get_status(ticker)
        if not status:
            await ctx.send(f"{ticker.upper()} is not being tracked.")
            return

        bought = ", ".join(status.get("accounts_bought", [])) or "None"
        sold = ", ".join(status.get("accounts_sold", [])) or "None"
        phase = _phase_for(ticker, status)
        await ctx.send(
            f"{ticker.upper()} | Split: {status.get('split_date')} | Phase: {phase}\n"
            f"Bought: {bought}\nSold: {sold}"
        )

    @commands.command(
        name="splitlist",
        aliases=["sl"],
        help="List tickers under reverse-split monitoring.",
        extras={"category": "Split Monitor"},
    )
    async def split_list(self, ctx: commands.Context) -> None:
        watchlist = split_watch_utils.get_full_watchlist()
        if not watchlist:
            await ctx.send("No reverse splits are currently being monitored.")
            return

        lines = []
        for ticker, info in watchlist.items():
            lines.append(
                f"{ticker}: {info.get('split_date')} ({_phase_for(ticker, info)})"
            )
        await ctx.send("\n".join(lines))

    @operator_only()
    @commands.command(
        name="splitorders",
        aliases=["so"],
        help="Show order history for a watched ticker, grouped by broker.",
        usage="<ticker> [broker]",
        extras={"category": "Split Monitor"},
    )
    async def split_orders(
        self, ctx: commands.Context, ticker: str, broker: str | None = None
    ) -> None:
        ticker = ticker.upper()
        watch_status = split_watch_utils.get_status(ticker)
        if not watch_status:
            await ctx.send(
                f"{ticker} is not on the reverse-split watchlist. Showing history anyway."
            )

        try:
            orders = [
                {
                    "Broker Name": row["broker_name"],
                    "Broker Number": row["broker_number"],
                    "Account Number": row["account_number"],
                    "Order Type": row["action"],
                    "Stock": row["ticker"],
                    "Quantity": row["quantity"],
                    "Price": row["price"],
                    "Date": row["date"],
                    "Timestamp": row["timestamp"],
                }
                for row in list_order_history(ticker=ticker)
            ]
        except (OSError, ValueError) as exc:
            await ctx.send(f"Unable to read order history: {exc}")
            return
        if not orders:
            await ctx.send("Orders log is empty.")
            return

        broker_filter = broker.lower() if broker else None
        filtered = []
        for row in orders:
            if row.get("Stock", "").strip().upper() != ticker:
                continue
            row_broker = row.get("Broker Name", "").strip()
            if broker_filter and row_broker.lower() != broker_filter:
                continue
            filtered.append(row)

        if not filtered:
            suffix = f" for broker {broker}" if broker else ""
            await ctx.send(f"No orders found for {ticker}{suffix}.")
            return

        broker_summary = {}
        for row in filtered:
            broker_name = row.get("Broker Name", "Unknown").strip() or "Unknown"
            broker_entry = broker_summary.setdefault(
                broker_name,
                {
                    "buy_count": 0,
                    "sell_count": 0,
                    "last_buy": None,
                    "last_sell": None,
                    "accounts": set(),
                },
            )

            order_type = row.get("Order Type", "").strip().lower()
            timestamp = row.get("Timestamp", "").strip() or row.get("Date", "").strip()
            account = row.get("Account Number", "").strip()
            if account:
                broker_entry["accounts"].add(account)

            if order_type == "buy":
                broker_entry["buy_count"] += 1
                if not broker_entry["last_buy"] or timestamp > broker_entry["last_buy"]:
                    broker_entry["last_buy"] = timestamp
            elif order_type == "sell":
                broker_entry["sell_count"] += 1
                if not broker_entry["last_sell"] or timestamp > broker_entry["last_sell"]:
                    broker_entry["last_sell"] = timestamp

        lines = [f"Order history for {ticker}:"]
        for broker_name, details in sorted(broker_summary.items()):
            accounts = ", ".join(sorted(details["accounts"])) or "N/A"
            lines.append(f"- {broker_name}")
            lines.append(f"  Buy count: {details['buy_count']} | Last buy: {details['last_buy'] or 'N/A'}")
            lines.append(f"  Sell count: {details['sell_count']} | Last sell: {details['last_sell'] or 'N/A'}")
            lines.append(f"  Accounts: {accounts}")

        message = "\n".join(lines)
        if len(message) <= 2000:
            await ctx.send(message)
        else:
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) + 1 > 2000:
                    await ctx.send(chunk)
                    chunk = line
                else:
                    chunk = f"{chunk}\n{line}" if chunk else line
            if chunk:
                await ctx.send(chunk)

    @operator_only()
    @commands.command(
        name="splitcleanup",
        aliases=["sc"],
        help="Advance phases and remove completed reverse splits.",
        extras={"category": "Split Monitor"},
    )
    async def split_cleanup(self, ctx: commands.Context) -> None:
        transitioned = split_watch_utils.update_split_status() or []
        completed = split_watch_utils.cleanup_completed_tickers() or []
        watchlist = split_watch_utils.get_full_watchlist()
        attention = [
            ticker
            for ticker, info in watchlist.items()
            if _phase_for(ticker, info) in ("overdue", "reconciliation needed")
        ]
        await ctx.send(
            f"Split cleanup: {len(transitioned)} moved to selling, "
            f"{len(completed)} completed and archived, "
            f"{len(watchlist)} still open, {len(attention)} need attention"
            + (f" ({', '.join(attention)})." if attention else ".")
        )

    @operator_only()
    @commands.command(
        name="splitreview",
        aliases=["sr"],
        help="List split events with unresolved order intent.",
        extras={"category": "Split Monitor"},
    )
    async def split_review(self, ctx: commands.Context) -> None:
        events = split_watch_utils.list_unresolved_events()
        if not events:
            await ctx.send("No unresolved split order intents.")
            return
        await ctx.send(
            "\n".join(
                f"{e['ticker']} {e['split_date']}: {e['state']}"
                + (f" ({e['reason']})" if e["reason"] else "")
                for e in events
            )
            + "\nUse splitresolve <ticker> <yyyy-mm-dd> after checking brokers."
        )

    @operator_only()
    @commands.command(
        name="splitresolve",
        help="Mark an unresolved split event reconciled (no orders are sent).",
        usage="<ticker> <yyyy-mm-dd>",
        extras={"category": "Split Monitor"},
    )
    async def split_resolve(self, ctx: commands.Context, ticker: str, split_date: str) -> None:
        if split_watch_utils.resolve_split_event(ticker, split_date):
            await ctx.send(f"{ticker.upper()} {split_date} marked reconciled.")
        else:
            await ctx.send(f"No unresolved event for {ticker.upper()} {split_date}.")

    @operator_only()
    @commands.command(
        name="splitreplace",
        help="Replace an active watch with a later split date (drops old account marks).",
        usage="<ticker> <yyyy-mm-dd>",
        extras={"category": "Split Monitor"},
    )
    async def split_replace(self, ctx: commands.Context, ticker: str, split_date: str) -> None:
        if split_watch_utils.replace_split_watch(ticker, split_date):
            await ctx.send(
                f"{ticker.upper()} now tracked for {split_date}; no orders were scheduled."
            )
        else:
            await ctx.send("Invalid ticker or date (use YYYY-MM-DD, a reasonable date).")


def _phase_for(ticker: str, info: dict) -> str:
    unresolved = any(
        e["ticker"] == ticker.upper()
        and e["split_date"] == info.get("split_date")
        and e["state"] == "needs_reconciliation"
        for e in split_watch_utils.list_unresolved_events()
    )
    return split_watch_utils.split_phase(info, unresolved=unresolved)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SplitMonitorCog(bot))
