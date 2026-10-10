"""Utility helpers for account mapping and Discord interactions."""

import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path

import discord
import yaml

from utils.config_utils import (
    ACCOUNT_MAPPING,
    CONFIG_DIR,
    HOLDINGS_LOG_CSV,
    get_account_nickname,
    load_account_mappings,
    load_config,
)
from rsassistant.persistence.holdings import get_current_holdings, latest_holdings_timestamp

logger = logging.getLogger(__name__)


def _normalize_identity_field(value):
    """Normalize broker/account style identifiers for robust matching."""

    return " ".join(str(value or "").strip().split())


def _normalize_ticker_symbol(value):
    """Normalize ticker input across commands and holdings rows."""

    ticker = _normalize_identity_field(value)
    if ticker.startswith("$"):
        ticker = ticker[1:].strip()
    return ticker.upper()


def _resolve_mapped_account(broker_mapping, broker_number, account_number):
    """Resolve snapshot identifiers to a configured account.

    Some importers emit values such as ``"Fidelity 1"`` and a full account
    number while the mapping stores ``"1"`` and only its last four digits.
    Prefer exact matches, then the longest unambiguous suffix match.
    """
    group_value = _normalize_identity_field(broker_number)
    account_value = _normalize_identity_field(account_number)

    group_candidates = []
    for mapped_group, accounts in broker_mapping.items():
        if not isinstance(accounts, dict):
            continue
        mapped_group_value = _normalize_identity_field(mapped_group)
        if group_value == mapped_group_value:
            group_candidates = [(mapped_group, accounts)]
            break
        if group_value.lower().endswith(f" {mapped_group_value.lower()}"):
            group_candidates.append((mapped_group, accounts))

    matches = []
    for mapped_group, accounts in group_candidates:
        for mapped_account, nickname in accounts.items():
            mapped_account_value = _normalize_identity_field(mapped_account)
            if account_value == mapped_account_value:
                return str(mapped_group), str(mapped_account), nickname
            if account_value.endswith(mapped_account_value):
                matches.append(
                    (len(mapped_account_value), mapped_group, mapped_account, nickname)
                )

    if not matches:
        return None
    matches.sort(reverse=True, key=lambda match: match[0])
    longest = matches[0][0]
    longest_matches = [match for match in matches if match[0] == longest]
    if len(longest_matches) != 1:
        return None
    _, mapped_group, mapped_account, nickname = longest_matches[0]
    return str(mapped_group), str(mapped_account), nickname


def check_holdings_timestamp(filename):
    """Return freshness from the authoritative SQL snapshot (filename kept for API compatibility)."""
    return latest_holdings_timestamp() or "No entries in holdings snapshot"


## -- Print raw order data to term for debugging
def debug_insert_order_history(order_data):
    """Debug function to log and return the order data instead of saving it."""
    try:
        # Return the raw data being passed for inspection
        return order_data
    except Exception as e:
        logging.error(f"Error processing order data for debug: {e}")
        return None


def debug_order_data(order_data):
    debug_data = debug_insert_order_history(order_data)
    logger.debug(f"Order data being passed to SQL: {debug_data}")


HOLDINGS_TIMESTAMP = check_holdings_timestamp(HOLDINGS_LOG_CSV)


def _load_account_owners():
    config = load_config()
    group_titles = config.get("account_owners")
    if not group_titles:
        settings_path = CONFIG_DIR / "settings.yml"
        if settings_path.exists():
            with open(settings_path, "r") as file:
                settings_data = yaml.safe_load(file) or {}
            group_titles = settings_data.get("account_owners", {})
        else:
            group_titles = {}
    if isinstance(group_titles, dict):
        return {str(indicator): owner for indicator, owner in group_titles.items()}
    return {}


async def track_ticker_summary(
    ctx,
    ticker,
    show_details=False,
    specific_broker=None,
    holding_logs_file=HOLDINGS_LOG_CSV,
    account_mapping_file=ACCOUNT_MAPPING,
    collect=False,
):
    """Track holdings for ``ticker`` grouped by broker.

    The function loads the latest holdings snapshot, resolves each row to the
    canonical configured group/account identity and builds broker/account
    status dictionaries used by aggregated and detailed Discord views.

    Args:
        ctx: Discord invocation context used for sending embeds.
        ticker (str): Symbol to inspect.
        show_details (bool): Historical argument preserved for compatibility.
        specific_broker (str | None): Optional broker to fetch a detailed view
            for. When provided, a pair of embeds is dispatched with account
            level data.
        holding_logs_file (Path | str): Path to the holdings CSV snapshot.
        account_mapping_file (Path | str): Path to the account mapping JSON,
            only used for error reporting.
        collect (bool): When ``True`` and ``specific_broker`` is ``None`` the
            function returns broker statuses instead of posting to Discord.

    Returns:
        tuple[dict[str, tuple[str, int, int]], str] | None: Broker-level status
        mapping with the latest timestamp when ``collect`` is requested;
        otherwise ``None`` because embeds are sent via ``ctx``.
    """
    holdings = {}
    ticker = _normalize_ticker_symbol(ticker)

    # Load account mappings
    mapped_accounts = load_account_mappings()
    broker_name_lookup = {
        _normalize_identity_field(name).lower(): name for name in mapped_accounts
    }

    try:
        # Read holdings log and keep only the latest row per account + ticker
        latest_rows = {}
        for sql_row in get_current_holdings():
            row = {"Broker Name": sql_row["broker"], "Broker Number": sql_row["broker_number"],
                   "Account Number": sql_row["account_number"], "Stock": sql_row["ticker"],
                   "Quantity": sql_row["quantity"], "Price": sql_row["price"],
                   "Account Total": sql_row["account_total"], "Timestamp": sql_row["observed_at"]}
            broker_name_raw = row.get("Broker Name")
            broker_name_normalized = _normalize_identity_field(broker_name_raw)
            broker_name = broker_name_lookup.get(
                broker_name_normalized.lower(), broker_name_normalized
            )
            if not broker_name:
                continue

            broker_number_raw = row.get("Broker Number")
            account_number_raw = row.get("Account Number")
            broker_number = _normalize_identity_field(broker_number_raw)
            account_number = _normalize_identity_field(account_number_raw)

            # Resolve importer-specific identifiers to the configured account.
            mapped_account = None
            if broker_number and account_number:
                broker_mapping = mapped_accounts.get(broker_name, {})
                mapped_account = _resolve_mapped_account(
                    broker_mapping, broker_number, account_number
                )

            if mapped_account:
                mapped_group, mapped_account_number, _ = mapped_account
                account_key = (mapped_group, mapped_account_number)
            else:
                # Unmapped rows must not alter the configured account totals.
                account_key = (broker_number, account_number)

            timestamp_str = row.get("Timestamp", "")
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                timestamp = datetime.min

            stock_raw = row.get("Stock", "")
            stock = _normalize_ticker_symbol(stock_raw)
            key = (broker_name, account_key, stock)
            if key not in latest_rows or timestamp > latest_rows[key]["_ts"]:
                row["_ts"] = timestamp
                latest_rows[key] = row

        # Build holdings dict from latest rows
        for (broker_name, account_key, stock), row in latest_rows.items():
            stock = stock or row["Stock"].upper().strip()

            try:
                quantity = float(row["Quantity"])
                price = float(row["Price"])
                account_total = float(row["Account Total"])
            except ValueError:
                continue

            if broker_name not in holdings:
                holdings[broker_name] = {}

            if stock == ticker and quantity > 0:
                holdings[broker_name][account_key] = {
                    "status": "✅",
                    "Quantity": quantity,
                    "Price": price,
                    "Account Total": account_total,
                }
            elif account_key not in holdings[broker_name]:
                holdings[broker_name][account_key] = {
                    "status": "❌",
                    "Quantity": "N/A",
                    "Price": "N/A",
                    "Account Total": "N/A",
                }

        latest_timestamp = (
            max(row["_ts"] for row in latest_rows.values()) if latest_rows else None
        )
        timestamp_str = (
            latest_timestamp.strftime("%Y-%m-%d %H:%M:%S") if latest_timestamp else ""
        )

        statuses = compute_broker_statuses(holdings, mapped_accounts)
        # Decide which view to show based on the specific_broker argument
        if collect and not specific_broker:
            return statuses, timestamp_str
        if specific_broker:
            await get_detailed_broker_view(
                ctx, ticker, specific_broker, holdings, mapped_accounts, timestamp_str
            )
        else:
            await get_aggregated_broker_summary(ctx, ticker, statuses, timestamp_str)

    except FileNotFoundError:
        await ctx.send(
            f"Error: The file {holding_logs_file} or {account_mapping_file} was not found."
        )
    except KeyError as e:
        await ctx.send(f"Error: Missing expected column in CSV: {e}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


def compute_broker_statuses(holdings, account_mapping):
    """Return held vs total account counts per broker.

    Args:
        holdings (dict): Parsed holdings keyed by broker and account key.
        account_mapping (dict): Mapping of brokers to their accounts.

    Returns:
        dict[str, tuple[str, int, int]]: Mapping of broker name to a tuple of
        (status_icon, held_accounts, total_accounts).
    """
    results = {}
    for broker_name, group_data in account_mapping.items():
        if isinstance(group_data, dict):
            total_accounts = 0
            held_accounts = 0
            for group_number, accounts in group_data.items():
                if isinstance(accounts, dict):
                    total_accounts += len(accounts)
                    for account_number, account_nickname in accounts.items():
                        account_key = (str(group_number), str(account_number))
                        if (
                            holdings.get(broker_name, {})
                            .get(account_key, {})
                            .get("status")
                            == "✅"
                        ):
                            held_accounts += 1
            if held_accounts == total_accounts:
                status_icon = "✅"
            elif held_accounts == 0:
                status_icon = "❌"
            else:
                status_icon = "🟡"
            results[broker_name] = (status_icon, held_accounts, total_accounts)
    return results


async def get_aggregated_broker_summary(ctx, ticker, statuses, timestamp_str=""):
    """Send an aggregated summary embed for a given ticker."""
    embed = discord.Embed(
        title=f"**{ticker} Holdings Summary**",
        description=f"All brokers summary, checking position for {ticker}.",
        color=discord.Color.blue(),
    )

    for broker_name, (status_icon, held_accounts, total_accounts) in statuses.items():
        embed.add_field(
            name=f"{broker_name} {status_icon}",
            value=f"Position in {held_accounts} of {total_accounts} accounts",
            inline=True,
        )

    embed.set_footer(
        text=f"Try: '..brokerwith {ticker} <broker>' for details. • {timestamp_str}"
    )
    await ctx.send(embed=embed)


async def get_detailed_broker_view(
    ctx, ticker, specific_broker, holdings, account_mapping, timestamp_str=""
):
    """
    Organizes the detailed view for a specific broker, calling separate functions to display:
    - Accounts holding the position.
    - Accounts not holding the position.
    """
    broker_name = next(
        (
            name
            for name in account_mapping
            if _normalize_identity_field(name).lower()
            == _normalize_identity_field(specific_broker).lower()
        ),
        specific_broker,
    )
    logger.debug(f"looking up {broker_name} in mapping")

    logger.debug(f"looking up{broker_name}")

    accounts_with_position = []
    accounts_without_position = []

    if broker_name in account_mapping:
        broker_data = account_mapping[broker_name]

        # Traverse groups and accounts within the specified broker
        for group_number, accounts in broker_data.items():
            if isinstance(accounts, dict):
                for account_number, account_nickname in accounts.items():
                    account_key = (str(group_number), str(account_number))
                    account_entry = holdings.get(broker_name, {}).get(account_key)

                    if account_entry and account_entry.get("status") == "✅":
                        # Account holds the ticker; gather details
                        quantity = account_entry.get("Quantity", "N/A")
                        try:
                            price = f"${float(account_entry.get('Price', 0)):,.2f}"
                            account_total = (
                                f"${float(account_entry.get('Account Total', 0)):,.2f}"
                            )
                        except (ValueError, TypeError):
                            price, account_total = "$0.00", "$0.00"
                        accounts_with_position.append(
                            (
                                account_nickname,
                                account_number[-4:],
                                quantity,
                                price,
                                account_total,
                            )
                        )
                    else:
                        # Account does not hold the ticker
                        accounts_without_position.append(
                            (account_nickname, account_number[-4:])
                        )

        # Send embeds for accounts with and without position
        await send_accounts_with_position_embed(
            ctx, broker_name, ticker, accounts_with_position, timestamp_str
        )
        await send_accounts_without_position_embed(
            ctx, broker_name, ticker, accounts_without_position, timestamp_str
        )
    else:
        await ctx.send(f"No broker found for {broker_name}.")


async def send_accounts_with_position_embed(
    ctx, broker_name, ticker, accounts_with_position, timestamp_str=""
):
    """
    Creates and sends an embed for accounts that hold the ticker position.
    """
    if accounts_with_position:
        # Embed for accounts with the position
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            color=discord.Color.green(),
        )
        # Add account details for each holding position
        for (
            nickname,
            last_four,
            quantity,
            price,
            account_total,
        ) in accounts_with_position:
            embed_with_position.add_field(
                name=f"{nickname} ✅",
                value=(
                    f"Account: {last_four}\n"
                    f"Quantity: {quantity}\n"
                    f"Price: {price}\n"
                    f"Account Total: {account_total}"
                ),
                inline=True,
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_with_position.set_footer(
            text=f"Detailed holdings for {ticker} • {timestamp_str}"
        )
        await ctx.send(embed=embed_with_position)
    else:
        # Embed indicating no holdings
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            description="No accounts hold this position",
            color=discord.Color.red(),
        )
        embed_with_position.set_footer(text=timestamp_str)
        await ctx.send(embed=embed_with_position)


async def send_accounts_without_position_embed(
    ctx, broker_name, ticker, accounts_without_position, timestamp_str=""
):
    """
    Creates and sends an embed for accounts that do not hold the ticker position.
    """
    if accounts_without_position:
        # Create an embed for accounts without the position
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            color=discord.Color.blue(),
        )
        # Add each account that does not hold the position
        for nickname, last_four in accounts_without_position:
            embed_without_position.add_field(
                name=f"{nickname} ❌",
                value=f"Account: {last_four}\nNo position in {ticker}",
                inline=True,
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_without_position.set_footer(
            text=f"Accounts without holdings for {ticker} • {timestamp_str}"
        )
        await ctx.send(embed=embed_without_position)
    else:
        # Optional embed if all accounts hold the position (for cases where there are no non-holding accounts)
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            description="All accounts hold this position",
            color=discord.Color.green(),
        )
        embed_without_position.set_footer(text=timestamp_str)
        await ctx.send(embed=embed_without_position)


async def all_brokers(ctx):
    account_mapping = load_account_mappings()
    try:
        active_brokers = list(account_mapping.keys())
        chunk_size = 9
        for i in range(0, len(active_brokers), chunk_size):
            embed = discord.Embed(
                title="**Active Brokers**", color=discord.Color.blue()
            )
            chunk_brokers = active_brokers[i : i + chunk_size]
            for broker in chunk_brokers:
                broker_data = account_mapping.get(broker)
                if not isinstance(broker_data, dict):
                    await ctx.send(f"Error: Broker '{broker}' has invalid data.")
                    continue

                total_holdings, account_count = 0, 0
                for group_number, accounts in broker_data.items():
                    try:
                        group_account_count, group_total = sum_account_totals(
                            broker, group_number, accounts
                        )
                        account_count += group_account_count
                        total_holdings += group_total
                    except ValueError as ve:
                        logging.error(
                            f"Value error for broker {broker}, group {group_number}: {ve}"
                        )
                        continue

                embed.add_field(
                    name=broker,
                    value=f"{account_count} accounts\nTotal: ${total_holdings:,.2f}",
                    inline=True,
                )

            await ctx.send(embed=embed)
            await asyncio.sleep(1)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
        logging.error(f"Exception in all_brokers: {e}")


# -- Get Totals for Specific Broker
def get_account_totals(broker, group_number=None, account_number=None):
    """Return SQL-backed totals keyed by account number."""
    totals = {}
    for row in get_current_holdings():
        if row["broker"].lower() != broker.lower():
            continue
        if group_number and row["broker_number"] != str(group_number):
            continue
        if account_number and row["account_number"] != str(account_number):
            continue
        totals[row["account_number"]] = float(row["account_total"] or 0)
    return totals


def sum_account_totals(broker, group_number, accounts):
    """Sum current SQL totals for configured accounts in a broker group."""
    totals = get_account_totals(broker, group_number)
    matching = [float(totals[a]) for a in accounts if a in totals]
    return len(matching), sum(matching)


def calculate_broker_totals(account_mapping):
    """Calculate account counts and totals using the current SQL snapshot."""
    result = {}
    for broker, groups in account_mapping.items():
        result[broker] = {}
        for group, accounts in groups.items():
            count, total = sum_account_totals(broker, group, accounts)
            result[broker][group] = {"account_count": count, "total_holdings": total}
    return result


def all_broker_accounts(broker):
    """Retrieve configured accounts for a broker."""
    mappings = load_account_mappings()
    if broker not in mappings:
        return f"Broker '{broker}' not found. Available brokers: {list(mappings.keys())}"
    return mappings[broker].get("accounts", [])


async def all_account_nicknames(ctx, broker):
    """Send configured account nicknames with totals from current SQL state."""
    mappings = load_account_mappings()
    normalized = {key.lower(): key for key in mappings}
    if broker.lower() not in normalized:
        await ctx.send(f"Broker {broker} not found. Available brokers: {', '.join(mappings)}")
        return
    original = normalized[broker.lower()]
    groups = mappings[original]
    total = sum(sum_account_totals(original, group, accounts)[1] for group, accounts in groups.items())
    embed = discord.Embed(title=f"**{original}**", description=f"All active accounts. Total Holdings: ${total:,.2f}", color=discord.Color.blue())
    for group, accounts in groups.items():
        account_totals = get_account_totals(original, group)
        for account, nickname in accounts.items():
            embed.add_field(name=f"{group} - {nickname}", value=f"Total: ${account_totals.get(account, 0.0):,.2f}", inline=True)
    await ctx.send(embed=embed)


def all_account_numbers(broker):
    """Return configured account numbers for a broker."""
    accounts = all_broker_accounts(broker)
    if isinstance(accounts, str):
        return accounts
    return [account["account_number"] for account in accounts]


def all_brokers_summary_by_owner(specific_broker=None):
    """Summarize current SQL account totals grouped by configured owner."""
    group_titles = _load_account_owners()
    brokers_summary = {}
    account_mapping = load_account_mappings()
    processed_accounts = set()
    for row in get_current_holdings():
        broker_name = row["broker"]
        if specific_broker and broker_name.lower() != specific_broker.lower():
            continue
        account_number = row["account_number"]
        if (broker_name, account_number) in processed_accounts:
            continue
        try:
            total = float(row["account_total"] or 0)
        except (ValueError, TypeError):
            continue
        processed_accounts.add((broker_name, account_number))
        nickname = ""
        if broker_name in account_mapping:
            for _group, accounts in account_mapping[broker_name].items():
                if account_number in accounts:
                    nickname = accounts[account_number]
                    break
        owner = next((name for indicator, name in group_titles.items() if indicator in nickname), "Uncategorized")
        if broker_name not in brokers_summary:
            brokers_summary[broker_name] = {name: 0.0 for name in group_titles.values()}
            brokers_summary[broker_name]["Uncategorized"] = 0.0
        brokers_summary[broker_name][owner] += total
    return brokers_summary


def generate_broker_summary_embed(specific_broker=None):
    """Return a Discord embed summarizing holdings by owner for each broker."""

    brokers_summary = all_brokers_summary_by_owner(specific_broker)
    account_mapping = load_account_mappings()
    broker_label = (
        specific_broker.upper()
        if specific_broker and specific_broker.lower() in ["bbae", "dspac"]
        else specific_broker.capitalize() if specific_broker else "All Active Brokers"
    )

    embed = discord.Embed(
        title=f"**{broker_label} Summary**", color=discord.Color.blue()
    )

    for broker_name, owner_totals in brokers_summary.items():
        account_owner_count = sum(
            len(accounts)
            for _group, accounts in account_mapping.get(broker_name, {}).items()
        )
        broker_total = sum(owner_totals.values())

        filtered_totals = {o: t for o, t in owner_totals.items() if t != 0}
        if not filtered_totals:
            continue

        broker_summary = (
            f"({account_owner_count} Owner groups, Total: ${broker_total:,.2f})\n"
        )
        for owner, total in filtered_totals.items():
            broker_summary += f"{owner}: ${total:,.2f}\n"

        formatted_name = (
            broker_name.upper()
            if broker_name.lower() in ["bbae", "dspac"]
            else broker_name.capitalize()
        )
        embed.add_field(name=formatted_name, value=broker_summary.strip(), inline=True)

        if specific_broker:
            break

    return embed


def aggregate_owner_totals():
    """Return total holdings aggregated by owner across all brokers."""

    summary = all_brokers_summary_by_owner()
    owner_totals = {}
    for broker_totals in summary.values():
        for owner, total in broker_totals.items():
            owner_totals[owner] = owner_totals.get(owner, 0.0) + total
    return owner_totals


def generate_owner_totals_embed():
    """Create a Discord embed showing aggregated holdings by owner."""

    owner_totals = aggregate_owner_totals()
    embed = discord.Embed(
        title="**Owner Totals Across Brokers**", color=discord.Color.blue()
    )
    for owner, total in sorted(owner_totals.items(), key=lambda x: x[1], reverse=True):
        embed.add_field(name=owner, value=f"${total:,.2f}", inline=True)
    return embed


def get_fennel_account_number(account_str):
    """Extract Fennel account number by combining the first and second number from the string."""
    parts = account_str.split()
    if len(parts) >= 4 and parts[0].lower() == "fennel":
        # Combine the first number and the second number to form account number
        newpart = parts[3].split(")")[0]
        account_number = parts[1] + newpart
        return account_number
    elif len(parts) >= 4 and parts[0].lower() == "fidelity":
        newpart = parts[3].split(")")[0]
        account_number = parts[1] + newpart
        return account_number
    return account_str  # Default behavior for non-Fennel accounts


async def send_large_message_chunks(ctx, message):
    logger.warning("send_large_message_chunks is deprecated.")

    # Discord messages have a max character limit of 2000
    max_length = 2000

    # Split the message by line breaks
    lines = message.split("\n")

    current_chunk = ""
    for line in lines:
        # Check if adding the next line would exceed the character limit
        if (
            len(current_chunk) + len(line) + 1 > max_length
        ):  # +1 for the added newline character
            await ctx.send(current_chunk)  # Send the current chunk
            current_chunk = ""  # Reset the chunk

        # Add the line to the current chunk
        if current_chunk:
            current_chunk += "\n" + line
        else:
            current_chunk = line

    # Send any remaining text in the current chunk
    if current_chunk:
        await ctx.send(current_chunk)


def get_order_details(broker, account_number, ticker):
    """Return the newest matching order detail from authoritative SQL history."""
    from rsassistant.persistence.orders import list_order_history

    ticker = _normalize_ticker_symbol(ticker)
    account_number = _normalize_identity_field(account_number)
    for row in list_order_history(ticker=ticker, broker=broker):
        stored_account = _normalize_identity_field(row["account_number"])
        if stored_account == account_number or stored_account.endswith(account_number):
            return (
                f"{row['action'].capitalize()} {row['quantity']} {ticker} "
                f"{row['date']}"
            )
    return None


# -- DEV Functions


def update_file_version(config_path, new_version):
    """
    Update the file_version in the given YAML configuration file.

    Args:
        config_path (str or Path): Path to the YAML configuration file.
        new_version (str): The new file version to set.
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load the current YAML data
    with open(config_path, "r") as file:
        config_data = yaml.safe_load(file)

    # Update the file_version
    config_data["general_settings"]["file_version"] = new_version

    # Save the updated YAML data back to the file
    with open(config_path, "w") as file:
        yaml.safe_dump(config_data, file)

    logging.info(f"Updated file_version to {new_version} in {config_path}")


def get_file_version(config_path):
    """
    Retrieves the current file version from the configuration file.

    Args:
        config_path (str): Path to the settings.yaml file.

    Returns:
        str: Current file version if successful, None otherwise.
    """
    try:
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)
            return config.get("general_settings", {}).get("file_version")
    except Exception as e:
        logging.error(f"Failed to get file version: {e}")
        return None
