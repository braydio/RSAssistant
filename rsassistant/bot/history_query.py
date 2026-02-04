"""Helpers for querying and visualizing historical holdings.

This module provides functions for translating account identifiers to
nicknames and for rendering historical holdings charts that can be sent
back to Discord.
"""

import io

import discord
import matplotlib.pyplot as plt
import pandas as pd

from utils.sql_utils import fetch_account_labels, get_db_connection


def get_account_id_or_name(account_input):
    """Return account_id if given nickname, or nickname if given account_id."""
    account_mappings = fetch_account_labels()
    for entry in account_mappings:
        if account_input.isdigit() and str(entry["account_id"]) == account_input:
            return entry["account_nickname"]
        if entry["account_nickname"].lower() == account_input.lower():
            return entry["account_id"]
    return None


async def show_sql_holdings_history(
    ctx,
    account: str | None = None,
    ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Send a holdings history plot to Discord.

    Parameters
    ----------
    ctx:
        Discord invocation context used to send messages.
    account:
        Optional account nickname or numeric identifier to filter by.
    ticker:
        Optional stock ticker symbol to filter by.
    start_date, end_date:
        Optional date range bounds in ``YYYY-MM-DD`` format.

    The function queries the ``HistoricalHoldings`` table with the provided
    filters, generates a line plot of quantity over time and replies to the
    invoking Discord command with the resulting image.
    """
    try:
        query = "SELECT * FROM HistoricalHoldings WHERE 1=1"
        params = {}

        # Convert account nickname to account_id if necessary
        if account:
            mapped_account = get_account_id_or_name(account)
            if not mapped_account:
                await ctx.send(f"Account '{account}' not found.")
                return
            query += " AND account_id = :account"
            params["account"] = mapped_account

        if ticker:
            query += " AND ticker = :ticker"
            params["ticker"] = ticker.upper()

        if start_date:
            query += " AND date >= :start_date"
            params["start_date"] = start_date

        if end_date:
            query += " AND date <= :end_date"
            params["end_date"] = end_date

        # Fetch data from SQL
        with get_db_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            await ctx.send("No historical data matches your filters.")
            return

        # Convert date to datetime and sort
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(by="date")

        # Group by date to show cumulative quantities if multiple entries exist per date
        history = (
            df.groupby("date")
            .agg({"quantity": "sum", "average_price": "mean"})
            .reset_index()
        )

        # Plot the data
        plt.figure(figsize=(12, 7))
        plt.plot(
            history["date"],
            history["quantity"],
            marker="o",
            label="Total Quantity",
            color="blue",
        )
        plt.fill_between(
            history["date"], 0, history["quantity"], alpha=0.1, color="blue"
        )
        plt.title(
            f"Historical Holdings Over Time for {'All Accounts' if not account else account}"
        )
        plt.xlabel("Date")
        plt.ylabel("Quantity Held")
        plt.grid(True)
        plt.legend()

        # Save plot to memory and send as file
        buffer = io.BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        await ctx.send(
            "Here is the historical holdings trend:",
            file=discord.File(fp=buffer, filename="holdings_history.png"),
        )

        plt.close()

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
