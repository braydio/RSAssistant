import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import RSAssistant


def test_brokerwith_alias():
    cmd_bw = RSAssistant.bot.get_command("bw")
    cmd_alias = RSAssistant.bot.get_command("brokerwith")
    assert cmd_bw is cmd_alias
