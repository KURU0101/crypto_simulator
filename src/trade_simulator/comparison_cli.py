from __future__ import annotations

import argparse
import json

from trade_simulator.comparison import run_comparisons
from trade_simulator.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run comparison cases for the trade simulator.")
    parser.add_argument("--config", required=True, help="Path to a comparison JSON config file.")
    return parser


def load_comparison_cases(config_path: str) -> list[dict]:
    config = load_config(config_path)

    if isinstance(config, list):
        return config

    if not isinstance(config, dict) or "cases" not in config:
        raise ValueError("comparison config must be a list or include a cases list")

    cases = config["cases"]
    if not isinstance(cases, list):
        raise ValueError("comparison config cases must be a list")

    return cases


def format_comparison_results(results: list[dict]) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cases = load_comparison_cases(args.config)
    results = run_comparisons(cases)
    print(format_comparison_results(results))
    return 0
