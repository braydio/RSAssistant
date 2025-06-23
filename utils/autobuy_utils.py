"""Helper for auto-buying tickers with market-hours awareness."""

from datetime import datetime, timedelta

from utils.logging_setup import logger
from utils.order_exec import schedule_and_execute


async def autobuy_ticker(bot, ctx, ticker, quantity=1, broker="all"):
    """
    Automatically buys a ticker immediately if market is open,
    or schedules it for next market open if closed.
    """
    try:
        now = datetime.now()
        weekday = now.weekday()  # 0=Monday, 6=Sunday
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        if market_open <= now <= market_close and weekday < 5:
            # Market is open
            execution_time = now
            logger.info(f"Market is OPEN - executing autobuy immediately for {ticker}.")
        else:
            # Market closed or weekend, schedule for next trading day 9:30 AM
            if weekday >= 5:  # Saturday (5) or Sunday (6)
                days_until_monday = 7 - weekday
                execution_time = (now + timedelta(days=days_until_monday)).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
            elif now > market_close:
                execution_time = (now + timedelta(days=1)).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
            else:  # Before market open today
                execution_time = market_open

            logger.info(
                f"Market CLOSED - scheduling autobuy for {ticker} at {execution_time}."
            )

        order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_buy"
        bot.loop.create_task(
            schedule_and_execute(
                ctx=ctx,
                action="buy",
                ticker=ticker,
                quantity=quantity,
                broker=broker,
                execution_time=execution_time,
                order_id=order_id,
            )
        )

        confirmation = f"✅ Auto-buy for `{ticker}` scheduled at {execution_time.strftime('%Y-%m-%d %H:%M:%S')}."
        await ctx.send(confirmation)
        logger.info(confirmation)

    except Exception as e:
        logger.error(f"Critical failure in autobuy_ticker for {ticker}: {e}")
