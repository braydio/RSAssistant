"""Order planning that can run without Discord message/context objects."""

from __future__ import annotations

from rsassistant.services.alert_processing import normalize_broker_name


def build_watchlist_autobuy_commands(missing_by_account, queued_pairs, ignored_brokers):
    """Plan unique watchlist autobuy commands without sending Discord messages."""
    queued = {
        (str(ticker).upper(), normalize_broker_name(broker))
        for ticker, broker in queued_pairs
    }
    ignored = {normalize_broker_name(broker) for broker in ignored_brokers}
    commands = []
    skipped = set()
    for account_label, tickers in missing_by_account.items():
        broker = normalize_broker_name(account_label.split(" ", 1)[0])
        if not broker or broker in ignored:
            continue
        for ticker in sorted(
            {str(value).strip().upper() for value in tickers if value}
        ):
            pair = (ticker, broker)
            if pair in queued:
                skipped.add(pair)
                continue
            command = f"!rsa buy 1 {ticker} {broker} false"
            commands.append((ticker, broker, command))
            queued.add(pair)
    return commands, sorted(skipped)


def build_autobuy_orders(ticker: str, quantity, config: dict):
    """Build standard and broker-override order specs from configuration."""
    standard_order = config.get("standard_order") or {}
    overrides = [
        item for item in (config.get("overrides") or []) if isinstance(item, dict)
    ]
    excluded_brokers = [
        broker
        for item in overrides
        if (broker := (item.get("broker") or "").strip())
    ]
    broker_parts = ["all"]
    if excluded_brokers:
        broker_parts.extend(["not", *excluded_brokers])
    standard_broker = " ".join(broker_parts)
    standard_quantity = standard_order.get("quantity")
    if standard_quantity in (None, ""):
        standard_quantity = quantity
    orders = [
        {
            "ticker": ticker,
            "broker": standard_broker,
            "quantity": standard_quantity,
            "kind": "standard",
            "excluded_brokers": excluded_brokers,
        }
    ]
    for item in overrides:
        broker = (item.get("broker") or "").strip()
        if not broker:
            continue
        override_quantity = item.get("quantity")
        if override_quantity in (None, ""):
            override_quantity = quantity
        orders.append(
            {
                "ticker": ticker,
                "broker": broker,
                "quantity": override_quantity,
                "kind": "override",
                "excluded_brokers": [],
            }
        )
    return orders
