from __future__ import annotations

import argparse
import json

from trade_simulator.config import load_config
from trade_simulator.data import summarize_data_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize configured local OHLCV data sources.")
    parser.add_argument("--config", required=True, help="Path to a JSON config file with data_source or data_sources.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    summary = summarize_data_sources(config)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
