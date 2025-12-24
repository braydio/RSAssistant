"""Order scheduling and execution commands."""

from __future__ import annotations

from datetime import datetime, timedelta

from discord.ext import commands

from utils.csv_utils import sell_all_position
from utils.order_exec import schedule_and_execute
from utils.order_queue_manager import list_order_queue

ORD_COMMAND_USAGE = "..ord <buy/sell> <ticker> [broker] [quantity] [time]"


class OrdersCog(commands.Cog):
    """Commands for scheduling and inspecting orders."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="queue",
        help="View all scheduled orders.",
        usage="",
        extras={"category": "Orders"},
    )
    async def show_order_queue(self, ctx: commands.Context) -> None:
        queue = list_order_queue()
        if not queue:
            await ctx.send("There are no scheduled orders.")
            return
        message = "**Scheduled Orders:**\n" + "\n".join(queue)
        await ctx.send(message)

    @commands.command(
        name="ord",
        help="Schedule a buy or sell order.",
        usage="<buy/sell> <ticker> [broker] [quantity] [time]",
        extras={"category": "Orders"},
    )
    async def process_order(
        self,
        ctx: commands.Context,
        action: str,
        ticker: str | None = None,
        broker: str = "all",
        quantity: float = 1,
        time: str | None = None,
    ) -> None:
        """Validate input and schedule an order for execution."""

        invalid_usage_message = f"Invalid arguments. Expected format: `{ORD_COMMAND_USAGE}`"

        if not action or action.lower() not in {"buy", "sell"}:
            await ctx.send(invalid_usage_message)
            return

        if not ticker:
            await ctx.send(invalid_usage_message)
            return

        try:
            quantity_value = float(quantity)
        except (TypeError, ValueError):
            await ctx.send(invalid_usage_message)
            return

        if quantity_value <= 0:
            await ctx.send(invalid_usage_message)
            return

        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        def next_open(base: datetime) -> datetime:
            cursor = base
            if cursor >= market_close:
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
            elif cursor < market_open:
                cursor = cursor.replace(hour=9, minute=30, second=0, microsecond=0)
            while cursor.weekday() >= 5:
                cursor += timedelta(days=1)
            return cursor

        try:
            if time:
                if "/" in time:
                    if " " in time:
                        date_part, time_part = time.split(" ")
                        month, day = map(int, date_part.split("/"))
                        hour, minute = map(int, time_part.split(":"))
                        execution_time = now.replace(
                            month=month,
                            day=day,
                            hour=hour,
                            minute=minute,
                            second=0,
                            microsecond=0,
                        )
                    else:
                        month, day = map(int, time.split("/"))
                        execution_time = now.replace(
                            month=month,
                            day=day,
                            hour=9,
                            minute=30,
                            second=0,
                            microsecond=0,
                        )
                else:
                    hour, minute = map(int, time.split(":"))
                    execution_time = now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )

                if execution_time < now:
                    execution_time += timedelta(days=1)
                execution_time = next_open(execution_time)
            else:
                if market_open <= now <= market_close and now.weekday() < 5:
                    execution_time = now
                else:
                    execution_time = next_open(now)
        except ValueError:
            await ctx.send(
                "Invalid time format. Use HH:MM, mm/dd, or HH:MM on mm/dd."
            )
            return

        if execution_time == now:
            await ctx.send(f"Executing {action.upper()} {ticker.upper()} immediately (market open).")
        else:
            await ctx.send(
                f"Scheduling {action.upper()} {ticker.upper()} for {execution_time.strftime('%A %m/%d %H:%M')}"
            )

        order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_{action.lower()}"
        self.bot.loop.create_task(
            schedule_and_execute(
                ctx,
                action=action,
                ticker=ticker,
                quantity=quantity_value,
                broker=broker,
                execution_time=execution_time,
                order_id=order_id,
                add_to_queue=True,
            )
        )

    @commands.command(
        name="liquidate",
        help="Liquidate holdings for a brokerage.",
        usage="<broker> [test_mode]",
        extras={"category": "Orders"},
    )
    async def liquidate(self, ctx: commands.Context, broker: str, test_mode: str = "false") -> None:
        """Liquidate holdings for a specific brokerage."""

        try:
            await sell_all_position(ctx, broker, test_mode)
        except Exception as exc:
            await ctx.send(f"An error occurred: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrdersCog(bot))
