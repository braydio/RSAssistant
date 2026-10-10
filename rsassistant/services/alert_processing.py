"""Pure decisions and formatting used by reverse-split and holdings alerts."""

from __future__ import annotations

from datetime import datetime
import logging

from utils.policy_resolver import SplitPolicyResolver

logger = logging.getLogger(__name__)


def should_tag_alert(ticker: str, quantity: float, requirements: dict) -> bool:
    """Return whether an alert meets the configured ticker quantity rule."""
    if not requirements:
        return True
    ticker = str(ticker or "").upper()
    if ticker not in requirements:
        return False
    minimum = requirements[ticker]
    return minimum is None or quantity >= minimum


def should_tag_entries(entries, requirements: dict) -> bool:
    """Return whether any holdings alert entry meets its mention rule."""
    if not entries:
        return False
    if not requirements:
        return True
    for entry in entries:
        ticker = str(entry.get("ticker", "")).upper()
        try:
            quantity = float(entry.get("quantity", 0) or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        if ticker and should_tag_alert(ticker, quantity, requirements):
            return True
    return False


def format_account_label(broker: str, account_name: str) -> str:
    """Combine a broker and account label without repeating the broker."""
    broker_prefix = (broker or "").strip()
    normalized_account = (account_name or "").strip()
    if not broker_prefix:
        return normalized_account
    if normalized_account.lower().startswith(broker_prefix.lower()):
        return normalized_account
    if not normalized_account:
        return broker_prefix
    return f"{broker_prefix} {normalized_account}".strip()


def resolve_round_up_snippet(policy_info, max_length: int):
    """Return a trimmed snippet describing the round-up policy, if present."""
    if not policy_info or max_length <= 0:
        return None
    snippet = policy_info.get("snippet")
    if snippet:
        return snippet.strip()[:max_length]
    body_text = policy_info.get("body_text")
    if not body_text:
        return None
    extracted = SplitPolicyResolver.extract_round_up_snippet(body_text)
    if not extracted:
        return None
    extracted = extracted.strip()
    fractional_clause = extracted.lower().find("fractional share")
    if fractional_clause >= 0:
        extracted = extracted[fractional_clause:]
        if len(extracted) > max_length:
            extracted = extracted[:max_length].rsplit(" ", 1)[0]
    return extracted[:max_length]


def format_watch_date(split_date: str) -> str:
    """Normalize an ISO split date to M/D for the watchlist command."""
    if not split_date:
        return split_date
    try:
        parsed = datetime.fromisoformat(split_date).date()
    except ValueError:
        return split_date
    return f"{parsed.month}/{parsed.day}"


def resolve_round_up_confirmation(policy_info: dict) -> bool:
    """Resolve round-up confirmation, preferring an explicit LLM result."""
    llm_policy = (policy_info.get("llm_details") or {}).get(
        "fractional_share_policy"
    )
    if llm_policy:
        return llm_policy in {"rounded_to_nearest_whole", "rounded_up"}
    return bool(policy_info.get("round_up_confirmed"))


def resolve_fractional_handling_text(policy_info: dict) -> str:
    """Return the resolved fractional share handling text."""
    llm_policy = (policy_info.get("llm_details") or {}).get(
        "fractional_share_policy"
    )
    if llm_policy:
        return llm_policy
    return (
        policy_info.get("sec_policy")
        or policy_info.get("policy")
        or "Policy not clearly stated."
    )


def normalize_broker_name(broker: str) -> str:
    """Normalize broker identifiers for comparisons and queued commands."""
    return str(broker or "").strip().upper()


def compute_account_missing_tickers(parsed_holdings, watchlist_tickers):
    """Return watchlist tickers absent from each account's parsed holdings."""
    watchlist = {str(ticker).upper() for ticker in watchlist_tickers}
    account_holdings = {}
    for holding in parsed_holdings:
        key = f"{holding['broker']} {holding['account_name']} ({holding['account']})"
        account_holdings.setdefault(key, set()).add(holding["ticker"].upper())
    return {
        account: sorted(watchlist - tickers)
        for account, tickers in account_holdings.items()
        if watchlist - tickers
    }


def collect_holdings_alert_data(
    parsed_holdings,
    *,
    threshold: float,
    ignored_tickers,
    is_broker_ignored,
    is_tracked_reverse_split,
    record_action_today,
    areb_ticker: str,
    areb_quantity_threshold: float,
    auto_sell: bool,
):
    """Classify parsed holdings using injected policy/persistence boundaries.

    The callbacks contain broker, split-watch, and once-per-day persistence
    policy. This service only receives plain holdings and returns plain alert
    data; it performs no messaging or Discord work.
    """
    alert_entries = []
    sell_commands = []
    areb_alerts = []
    one_share_positions = []
    round_ups_found = False

    for holding in parsed_holdings:
        try:
            ticker = str(holding.get("ticker", "")).upper()
            if not ticker or ticker == "CASH AND SWEEP FUNDS":
                continue

            broker = str(holding.get("broker", "")).strip()
            account_name = str(
                holding.get("account_name", holding.get("account", ""))
            )
            price = float(holding.get("price", 0) or 0)
            quantity = float(holding.get("quantity", 0) or 0)

            if ticker == areb_ticker and quantity > areb_quantity_threshold:
                if not is_broker_ignored(broker):
                    action_key = f"{ticker}_AREB_THRESHOLD"
                    if record_action_today(broker, account_name, action_key):
                        areb_alerts.append(
                            {
                                "broker": broker,
                                "account_name": account_name,
                                "quantity": quantity,
                                "price": price,
                            }
                        )

            if ticker in ignored_tickers or is_broker_ignored(broker):
                continue
            if (
                price >= threshold
                and quantity == 1
                and is_tracked_reverse_split(ticker)
            ):
                one_share_positions.append((broker, ticker, price))
                round_ups_found = True
            if price < threshold or quantity <= 0:
                continue
            if not record_action_today(broker, account_name, ticker):
                continue

            alert_entries.append(
                {
                    "broker": broker,
                    "account_name": account_name,
                    "ticker": ticker,
                    "price": price,
                    "quantity": quantity,
                }
            )
            if auto_sell:
                sell_commands.append(
                    f"!rsa sell {quantity} {ticker} {broker} false"
                )
        except Exception as exc:
            logger.error(
                "Monitor/auto-sell step failed for holding %s: %s", holding, exc
            )

    return {
        "alert_entries": alert_entries,
        "sell_commands": sell_commands,
        "areb_alerts": areb_alerts,
        "one_share_positions": one_share_positions,
        "reverse_split_round_ups_found": round_ups_found,
    }


def build_policy_summary(ticker, policy_info, fallback_url):
    """Render a policy summary from plain values for delivery by the bot."""
    summary = f"**Reverse Split Alert** for `{ticker}`\n"
    summary += f"[NASDAQ Notice]({policy_info.get('nasdaq_url', fallback_url)})\n"
    if policy_info.get("press_url"):
        summary += f"[Press Release]({policy_info['press_url']})\n"
    if policy_info.get("sec_url"):
        summary += f"[SEC Filing]({policy_info['sec_url']})\n"
    llm_details = policy_info.get("llm_details") or {}
    effective_date = llm_details.get("effective_date") or policy_info.get(
        "effective_date"
    )
    if effective_date:
        summary += f"**Effective Date:** {effective_date}\n"
    split_ratio = llm_details.get("split_ratio") or policy_info.get("split_ratio")
    if split_ratio:
        summary += f"**Split Ratio:** {split_ratio}\n"
    llm_policy = llm_details.get("fractional_share_policy") or policy_info.get(
        "fractional_share_policy"
    )
    if llm_policy:
        summary += f"**Fractional Share Policy (LLM):** {llm_policy}"
    if policy_info.get("snippet"):
        summary += f"\n> {policy_info['snippet']}"
    return summary


