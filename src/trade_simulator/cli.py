from __future__ import annotations

import argparse
import json

from trade_simulator.config import load_config
from trade_simulator.simulation import simulate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a minimal trade simulation.")
    parser.add_argument("--config", required=True, help="Path to a JSON config file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = simulate(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
