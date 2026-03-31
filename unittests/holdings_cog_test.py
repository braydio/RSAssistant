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


class _FakeChannel:
    def __init__(self, channel_id=1, mention="#holdings"):
        self.id = channel_id
        self.mention = mention
        self.sent_embeds = []

    async def send(self, embed=None):
        self.sent_embeds.append(embed)


class _FakeCtx:
    def __init__(self, channel):
        self.channel = channel
        self.messages = []

    async def send(self, message=None, embed=None):
        self.messages.append({"message": message, "embed": embed})


def test_holdings_snapshot_imports_before_render(monkeypatch):
    events = []
    bot = _FakeBot()
    cog = holdings.HoldingsCog(bot)
    ctx_channel = _FakeChannel(channel_id=10, mention="#ctx")
    ctx = _FakeCtx(ctx_channel)
    target_channel = _FakeChannel(channel_id=20, mention="#target")

    def _fake_import():
        events.append("import")
        return 1

    def _fake_build(broker_filter=None, top_n=5):
        events.append(("build", broker_filter, top_n))
        return [object()], None

    monkeypatch.setattr(holdings, "DISCORD_HOLDINGS_CHANNEL", 20)
    monkeypatch.setattr(holdings, "resolve_reply_channel", lambda bot, channel_id: target_channel)
    monkeypatch.setattr(holdings, "import_holdings_if_updated", _fake_import)
    monkeypatch.setattr(holdings, "build_holdings_snapshot_embeds", _fake_build)

    asyncio.run(cog.holdings_snapshot.callback(cog, ctx, "vanguard", "3"))

    assert events == ["import", ("build", "vanguard", 3)]
    assert len(target_channel.sent_embeds) == 1
    assert ctx.messages == [{"message": "Holdings snapshot posted to #target.", "embed": None}]
