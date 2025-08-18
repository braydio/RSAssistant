import json
from pathlib import Path

from utils import config_utils


def test_get_account_nickname_creates_mapping(tmp_path, monkeypatch):
    tmp_mapping = tmp_path / "account_mapping.json"
    monkeypatch.setattr(config_utils, "ACCOUNT_MAPPING", tmp_mapping)

    nickname = config_utils.get_account_nickname("TestBroker", "1", "1234")
    assert nickname == "TestBroker 1 1234"

    with open(tmp_mapping, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data == {"TestBroker": {"1": {"1234": "TestBroker 1 1234"}}}
