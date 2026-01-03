import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import parsing_utils


def test_public_incomplete_message(monkeypatch):
    """Public order messages without account info should create temporary orders."""
    monkeypatch.setattr(
        parsing_utils,
        "account_mapping",
        {"Public": {"4": {"0000": "Test"}}},
        raising=False,
    )
    parsing_utils.incomplete_orders.clear()
    parsing_utils.parse_order_message("Public 4: selling 0.10937 of VLCN")
    key = ("VLCN", "0000")
    assert key in parsing_utils.incomplete_orders
    order = parsing_utils.incomplete_orders[key]
    assert order["broker_name"] == "Public"
    assert order["broker_number"] == "4"
    assert order["action"] == "sell"
    assert pytest.approx(order["quantity"]) == 0.10937


def _setup_price_fetch(monkeypatch, captured, price):
    """Helper to patch price lookup and persistence."""

    monkeypatch.setattr(parsing_utils, "get_last_stock_price", lambda s: price)

    def save_order_to_csv(order_data):
        captured["order_data"] = order_data
        return True

    def record_error_message(*_args, **_kwargs):
        captured["error_called"] = True

    monkeypatch.setattr(parsing_utils, "save_order_to_csv", save_order_to_csv)
    monkeypatch.setattr(parsing_utils, "insert_order_history", lambda *a, **k: True)
    monkeypatch.setattr(parsing_utils, "update_excel_log", lambda *a, **k: True)
    monkeypatch.setattr(parsing_utils, "record_error_message", record_error_message)


def test_handle_complete_order_price_none(monkeypatch):
    """handle_complete_order should log an error and skip saves when price is None."""

    captured = {}
    _setup_price_fetch(monkeypatch, captured, None)

    parsing_utils.parse_order_message("BBAE 1: buy 1 of ABC in xxxx1234: Success")

    assert captured.get("error_called") is True
    assert "order_data" not in captured


def test_handle_complete_order_price_success(monkeypatch):
    """handle_complete_order should persist with the fetched price."""

    captured = {}
    _setup_price_fetch(monkeypatch, captured, 12.5)

    parsing_utils.parse_order_message("BBAE 1: buy 1 of ABC in xxxx1234: Success")

    assert captured.get("order_data"), "order should be saved"
    assert captured["order_data"]["Price"] == 12.5
    assert "error_called" not in captured


def test_process_verified_orders_price_none(monkeypatch):
    """process_verified_orders should log an error and skip saves when price is None."""

    captured = {}
    _setup_price_fetch(monkeypatch, captured, None)

    order = {"action": "buy", "quantity": 1, "stock": "ABC"}
    parsing_utils.process_verified_orders("BBAE", "1", "1234", order)

    assert captured.get("error_called") is True
    assert "order_data" not in captured


def test_alert_channel_message_remote_ticker(monkeypatch):
    """Messages without inline tickers should resolve symbols from linked sources."""

    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    captured = {}

    def fake_get(url, timeout=10):  # pragma: no cover - simple test helper
        captured["url"] = url
        html = (
            "<html><body>bioAffinity Technologies, Inc. "
            "(<span>NasdaqCM</span>: <strong>BIAF</strong>) announced "
            "a reverse stock split.</body></html>"
        )
        return FakeResponse(html)

    monkeypatch.setattr(parsing_utils.requests, "get", fake_get)

    content = (
        "📰 | **bioAffinity Technologies Announces 1-for-30 Reverse Stock Split**\n"
        "https://example.com/release"
    )

    result = parsing_utils.alert_channel_message(content)

    assert result["ticker"] == "BIAF"
    assert result["reverse_split_confirmed"] is True
    assert captured["url"] == "https://example.com/release"


def test_alert_channel_message_remote_ticker_failure(monkeypatch):
    """Ticker remains None when remote fetching raises an error."""

    def fake_get(url, timeout=10):
        raise parsing_utils.RequestException("network error")

    monkeypatch.setattr(parsing_utils.requests, "get", fake_get)

    content = "📰 | **Headline**\nhttps://example.com/pr"
    result = parsing_utils.alert_channel_message(content)

    assert result["ticker"] is None
    assert result["reverse_split_confirmed"] is False


def test_parse_general_embed_account_name_without_duplicate_broker(monkeypatch):
    """General embed parsing should avoid duplicating broker names in account labels."""

    class DummyField:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class DummyEmbed:
        def __init__(self, fields):
            self.fields = fields

    monkeypatch.setattr(
        parsing_utils,
        "account_mapping",
        {"Schwab": {"1": {"8745": "Schwab 1 8745"}}},
        raising=False,
    )

    class DummySplitWatch:
        @staticmethod
        def get_status(_ticker):
            return False

        @staticmethod
        def mark_account_bought(_ticker, _account_name):
            return None

    monkeypatch.setattr(parsing_utils, "split_watch_utils", DummySplitWatch)

    embed = DummyEmbed(
        [DummyField("Schwab 1 (8745)", "ABC: 1.00 @ $2.00 = $2.00\nTotal: $2.00")]
    )

    holdings = parsing_utils.parse_general_embed_message(embed)

    assert len(holdings) == 1
    assert holdings[0]["account_name"] == "Schwab 1 8745"
    assert holdings[0]["broker"] == "Schwab"


def test_parse_webull_embed_account_name_without_duplicate_broker(monkeypatch):
    """Webull embed parsing should not prepend the broker when nickname already includes it."""

    class DummyField:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class DummyEmbed:
        def __init__(self, fields):
            self.fields = fields

    monkeypatch.setattr(
        parsing_utils,
        "account_mapping",
        {"Webull": {"1": {"AB12": "Webull Flex"}}},
        raising=False,
    )

    class DummySplitWatch:
        @staticmethod
        def get_status(_ticker):
            return False

        @staticmethod
        def mark_account_bought(_ticker, _account_name):
            return None

    monkeypatch.setattr(parsing_utils, "split_watch_utils", DummySplitWatch)

    embed = DummyEmbed(
        [DummyField("Webull 1 xxxxAB12", "XYZ: 2.00 @ $3.00 = $6.00\nTotal: $6.00")]
    )

    holdings = parsing_utils.parse_webull_embed_message(embed)

    assert len(holdings) == 1
    assert holdings[0]["account_name"] == "Webull Flex"
    assert holdings[0]["broker"] == "Webull"
