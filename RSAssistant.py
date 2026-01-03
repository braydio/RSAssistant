"""RSAssistant entrypoint wrapper.

Legacy commands have been removed in favor of the modular bot under
`rsassistant/bot`. This file now delegates directly to the modular runtime.
"""

from __future__ import annotations

from rsassistant.bot.core import run_bot


if __name__ == "__main__":
    run_bot()
