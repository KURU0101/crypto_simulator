from __future__ import annotations

import argparse
import json

from trade_simulator.config import load_config
from trade_simulator.evaluation_batch_input_adapter import (
    load_batch_input_adapter_config,
    resolve_batch_execution_inputs,
)
from trade_simulator.evaluation_batch_runner import run_evaluation_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run batch evaluation from periods CSV and case template/grid inputs."
    )
    parser.add_argument("--config", required=True, help="Path to an input-adapter batch evaluation config file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    adapter_config = load_batch_input_adapter_config(config)
    execution_inputs = resolve_batch_execution_inputs(adapter_config)
    result = run_evaluation_batch(
        periods=execution_inputs["periods"],
        case_iterator_factory=execution_inputs["case_iterator_factory"],
        total_cases=execution_inputs["total_cases"],
        output_csv_path=execution_inputs["output_csv_path"],
        cache_root=execution_inputs["cache_root"],
        shared_state_db_path=execution_inputs["shared_state_db_path"],
        results_db_path=execution_inputs["results_db_path"],
        config_path=args.config,
        config_fingerprint_payload=execution_inputs["config_fingerprint_payload"],
        case_chunk_size=execution_inputs["case_chunk_size"],
        dry_run=execution_inputs["dry_run"],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
