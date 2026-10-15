#!/usr/bin/env python3
"""Docker health probe: the heartbeat file must be non-empty and recently updated.

The heartbeat is written every 60s by ``utils.logging_setup.start_heartbeat_writer``.
The probe is read-only and exits 0 (healthy) or 1 (missing/empty/stale).
"""

import os
import sys
import time

HEARTBEAT = os.path.join(
    os.getenv("VOLUMES_DIR", "/app/volumes"), "logs", "heartbeat.txt"
)
MAX_AGE_SECONDS = float(os.getenv("HEARTBEAT_MAX_AGE_SECONDS", "180"))


def main() -> int:
    try:
        stat = os.stat(HEARTBEAT)
    except OSError:
        print("heartbeat missing", file=sys.stderr)
        return 1
    if stat.st_size == 0:
        print("heartbeat empty", file=sys.stderr)
        return 1
    age = time.time() - stat.st_mtime
    if age > MAX_AGE_SECONDS:
        print(f"heartbeat stale ({age:.0f}s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
