"""Helper for auto-buying tickers with market-hours awareness."""

from datetime import datetime

from utils.logging_setup import logger
from utils.market_calendar import MARKET_TZ, is_market_open_at, next_market_open
from utils.order_exec import schedule_and_execute


async def autobuy_ticker(bot, ctx, ticker, quantity=1, broker="all"):
    """
    Automatically buys a ticker immediately if market is open,
    or schedules it for next market open if closed.
    """
    try:
        now = datetime.now(MARKET_TZ)
        if is_market_open_at(now):
            execution_time = now
            logger.info("Market is OPEN - executing autobuy immediately for %s.", ticker)
        else:
            execution_time = next_market_open(now)
            logger.info(
                "Market CLOSED - scheduling autobuy for %s at %s.",
                ticker,
                execution_time,
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
                bot=bot,
                order_id=order_id,
            )
        )

        confirmation = f"✅ Auto-buy for `{ticker}` scheduled at {execution_time.strftime('%Y-%m-%d %H:%M:%S')}."
        await ctx.send(confirmation)
        logger.info(confirmation)

    except Exception as e:
        logger.error(f"Critical failure in autobuy_ticker for {ticker}: {e}")
