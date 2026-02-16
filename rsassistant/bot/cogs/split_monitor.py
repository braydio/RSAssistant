"""Reverse split monitoring commands."""

from __future__ import annotations

import datetime

from discord.ext import commands

from utils import split_watch_utils
from utils.config_utils import CSV_LOGGING_ENABLED, ORDERS_LOG_CSV
from utils.csv_utils import load_csv_log


class SplitMonitorCog(commands.Cog):
    """Commands for tracking reverse-split watch entries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        split_watch_utils.cleanup_expired_tickers()
        status = split_watch_utils.get_status(ticker)
        if not status:
            await ctx.send(f"{ticker.upper()} is not being tracked.")
            return

        bought = ", ".join(status.get("accounts_bought", [])) or "None"
        sold = ", ".join(status.get("accounts_sold", [])) or "None"
        await ctx.send(
            f"{ticker.upper()} | Split: {status.get('split_date')} | Phase: {status.get('status')}\n"
            f"Bought: {bought}\nSold: {sold}"
        )

    @commands.command(
        name="splitlist",
        aliases=["sl"],
        help="List tickers under reverse-split monitoring.",
        extras={"category": "Split Monitor"},
    )
    async def split_list(self, ctx: commands.Context) -> None:
        split_watch_utils.cleanup_expired_tickers()
        watchlist = split_watch_utils.get_full_watchlist()
        if not watchlist:
            await ctx.send("No reverse splits are currently being monitored.")
            return

        lines = []
        for ticker, info in watchlist.items():
            lines.append(
                f"{ticker}: {info.get('split_date')} ({info.get('status', 'unknown')})"
            )
        await ctx.send("\n".join(lines))

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
        if not CSV_LOGGING_ENABLED:
            await ctx.send("CSV logging is disabled; no order history is available.")
            return

        if not ORDERS_LOG_CSV.exists():
            await ctx.send("Orders log not found. No order history is available yet.")
            return

        ticker = ticker.upper()
        watch_status = split_watch_utils.get_status(ticker)
        if not watch_status:
            await ctx.send(
                f"{ticker} is not on the reverse-split watchlist. Showing history anyway."
            )

        orders = load_csv_log(ORDERS_LOG_CSV)
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

    @commands.command(
        name="splitcleanup",
        aliases=["sc"],
        help="Advance phases and remove completed reverse splits.",
        extras={"category": "Split Monitor"},
    )
    async def split_cleanup(self, ctx: commands.Context) -> None:
        split_watch_utils.update_split_status()
        split_watch_utils.cleanup_completed_tickers()
        await ctx.send("Updated reverse split statuses and cleaned completed entries.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SplitMonitorCog(bot))
