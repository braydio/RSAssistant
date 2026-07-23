import asyncio
import unittest
from unittest.mock import patch

from rsassistant.bot.cogs import reporting


class ReportingCogTest(unittest.TestCase):
    def test_top_holdings_imports_before_render(self):
        events = []
        cog = reporting.ReportingCog(object())

        async def fake_send(_ctx, range):
            events.append(("render", range))

        with (
            patch.object(
                reporting,
                "import_holdings_if_updated",
                lambda: events.append("import"),
            ),
            patch.object(reporting, "send_top_holdings_embed", fake_send),
        ):
            asyncio.run(cog.top_holdings_command.callback(cog, object(), 5))

        self.assertEqual(events, ["import", ("render", 5)])


if __name__ == "__main__":
    unittest.main()
