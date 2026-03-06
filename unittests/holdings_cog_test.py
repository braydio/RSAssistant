import asyncio
from types import SimpleNamespace

from rsassistant.bot.cogs import holdings


class _FakeBot:
    def __init__(self):
        self.cog = None
        self.removed = []

    async def add_cog(self, cog):
        self.cog = cog

    def get_command(self, name):
        if name != "history" or self.cog is None:
            return None
        return SimpleNamespace(cog=self.cog)

    def remove_command(self, name):
        self.removed.append(name)


def test_holdings_setup_removes_history_when_disabled(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr(holdings, "HISTORY_QUERY_ENABLED", False)

    asyncio.run(holdings.setup(bot))

    assert bot.removed == ["history"]


def test_holdings_setup_keeps_history_when_enabled(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr(holdings, "HISTORY_QUERY_ENABLED", True)

    asyncio.run(holdings.setup(bot))

    assert bot.removed == []
