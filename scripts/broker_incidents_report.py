#!/usr/bin/env python3
"""Print open broker incidents (shared infrastructure incidents listed once)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rsassistant.persistence import broker_incidents  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(broker_incidents.open_incidents(), indent=1))
