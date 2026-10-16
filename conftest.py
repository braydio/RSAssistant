"""Pytest bootstrap: keep tests away from the real ``volumes`` directory.

``utils.config_utils`` resolves ``VOLUMES_DIR`` (and so the production SQLite
database and logs) at import time. Without an override, a test run writes
fixture rows such as account ``B`` into ``volumes/db/rsa_database.db``. This
module points ``VOLUMES_DIR`` at a throwaway directory before any test module
imports the application.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_REAL_VOLUMES = (Path(__file__).resolve().parent / "volumes").resolve()


def _isolate_volumes() -> None:
    configured = os.environ.get("VOLUMES_DIR")
    if configured and Path(configured).expanduser().resolve() != _REAL_VOLUMES:
        return
    scratch = tempfile.mkdtemp(prefix="rsa-test-volumes-")
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    os.environ["VOLUMES_DIR"] = scratch


_isolate_volumes()
