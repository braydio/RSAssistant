#!/usr/bin/env python3
"""Build/inspect the canonical-account mapping (never edits ``Accounts``).

    python scripts/account_identity_report.py            # report only (needs v13 DB)
    python scripts/account_identity_report.py --refresh  # (re)build mapping tables first
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rsassistant.persistence import account_identity  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh:
        print(json.dumps(account_identity.refresh_canonical_map()))
    print(json.dumps(account_identity.mapping_report(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
