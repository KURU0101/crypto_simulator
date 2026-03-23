from __future__ import annotations

import argparse
import json
from typing import Callable


def build_external_signal_parser(signal_type: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Validate and summarize {signal_type} signal input.")
    parser.add_argument("--input", required=True, help=f"Path to a {signal_type} signal JSON or NDJSON file.")
    parser.add_argument(
        "--mode",
        choices=("summary", "bundle"),
        default="summary",
        help="summary prints only summary and grouped keys, bundle prints the full normalized bundle.",
    )
    return parser


def run_external_signal_cli(
    argv: list[str] | None,
    *,
    signal_type: str,
    loader: Callable[[str], dict],
) -> int:
    parser = build_external_signal_parser(signal_type)
    args = parser.parse_args(argv)

    bundle = loader(args.input)
    if args.mode == "summary":
        payload = {
            "signal_type": bundle["signal_type"],
            "schema_version": bundle["schema_version"],
            "summary": bundle["summary"],
        }
        if "by_symbol" in bundle:
            payload["by_symbol_keys"] = sorted(bundle["by_symbol"])
        if "by_asset" in bundle:
            payload["by_asset_keys"] = sorted(bundle["by_asset"])
        if "by_topic" in bundle:
            payload["by_topic_keys"] = sorted(bundle["by_topic"])
    else:
        payload = bundle

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


__all__ = [
    "build_external_signal_parser",
    "run_external_signal_cli",
]
