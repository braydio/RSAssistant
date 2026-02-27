#!/usr/bin/env python3
"""One-shot debug utility for reverse-split source parsing."""

from __future__ import annotations

import argparse
import sys

import requests
from bs4 import BeautifulSoup


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and inspect source text extraction stages used before OpenAI parsing."
        )
    )
    parser.add_argument("url", help="Source URL to inspect.")
    parser.add_argument(
        "--ticker",
        help="Optional ticker hint for context trimming.",
        default=None,
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=6000,
        help="Character budget used for OpenAI-bound clipping (default: 6000).",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=1200,
        help="How many characters of previews to print (default: 1200).",
    )
    return parser


def _contains_terms(text: str) -> dict[str, bool]:
    lowered = (text or "").lower()
    return {
        "reverse_split": (
            "reverse split" in lowered or "reverse stock split" in lowered
        ),
        "fractional_share": (
            "fractional share" in lowered or "fractional shares" in lowered
        ),
        "cash_in_lieu": "cash in lieu" in lowered,
        "rounded_up": "rounded up" in lowered or "round up" in lowered,
    }


def main() -> int:
    args = _build_parser().parse_args()
    try:
        from utils.openai_utils import _clip_notice_text
        from utils.policy_resolver import SplitPolicyResolver
    except Exception as exc:
        print(
            "import_error=Unable to import project parsers. "
            "Activate the project venv and install requirements first.",
            file=sys.stderr,
        )
        print(f"details={exc}", file=sys.stderr)
        return 2

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Safari/537.36"
        )
    }

    try:
        with requests.get(args.url, headers=headers, timeout=15) as response:
            response.raise_for_status()
            html = response.text or ""
    except Exception as exc:
        print(f"fetch_error={exc}", file=sys.stderr)
        return 1

    raw_text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    extracted = SplitPolicyResolver._extract_main_text(html)
    trimmed = SplitPolicyResolver._trim_to_context(extracted, ticker=args.ticker)
    llm_clip = _clip_notice_text(trimmed, max_chars=args.max_chars)

    print(f"url={args.url}")
    print(f"ticker={args.ticker or 'N/A'}")
    print(f"raw_html_chars={len(html)}")
    print(f"raw_text_chars={len(raw_text)}")
    print(f"extracted_chars={len(extracted)}")
    print(f"trimmed_chars={len(trimmed)}")
    print(f"llm_clip_chars={len(llm_clip)}")

    for stage_name, stage_text in [
        ("raw_text", raw_text),
        ("extracted", extracted),
        ("trimmed", trimmed),
        ("llm_clip", llm_clip),
    ]:
        terms = _contains_terms(stage_text)
        print(
            f"{stage_name}_has_terms="
            f"reverse_split:{terms['reverse_split']},"
            f"fractional_share:{terms['fractional_share']},"
            f"cash_in_lieu:{terms['cash_in_lieu']},"
            f"rounded_up:{terms['rounded_up']}"
        )

    preview_chars = max(args.preview_chars, 0)
    print("\n--- llm_clip_preview_start ---")
    print(llm_clip[:preview_chars])
    print("--- llm_clip_preview_end ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
