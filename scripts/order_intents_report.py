#!/usr/bin/env python3
"""Report order intents lacking broker-activity evidence, grouped by broker.

    python scripts/order_intents_report.py            # report only
    python scripts/order_intents_report.py --backfill # first create needs_review
                                                      # intents from rsa_order_send_log
Backfill is additive and idempotent; it never creates fills or marks anything
filled, and never sends or retries a command.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rsassistant.persistence import order_intents  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args(argv)
    if args.backfill:
        print(f"backfilled intents: {order_intents.backfill_from_send_log()}")
    print(json.dumps(order_intents.unverified_report(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
