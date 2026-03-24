from __future__ import annotations

import argparse
import json

from trade_simulator.config import load_config
from trade_simulator.evaluation_batch_runner import load_evaluation_batch_config, run_evaluation_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multiple periods and multiple cases with per-period market-data reuse.")
    parser.add_argument("--config", required=True, help="Path to a batch evaluation JSON config file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    batch_config = load_evaluation_batch_config(config)
    result = run_evaluation_batch(
        periods=batch_config["periods"],
        cases=batch_config["cases"],
        output_csv_path=batch_config["output_csv_path"],
        cache_root=batch_config["cache_root"],
        shared_state_db_path=batch_config["shared_state_db_path"],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
