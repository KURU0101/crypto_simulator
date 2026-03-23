from __future__ import annotations

from trade_simulator.live_decision_runner import (
    build_live_decision_parser,
    format_live_decision_stdout,
    run_live_decision_runner,
    save_live_decision_runner_result,
)
from trade_simulator.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = build_live_decision_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = run_live_decision_runner(config)
    save_live_decision_runner_result(result, result["output"]["output_dir"])
    print(format_live_decision_stdout(result))
    return 0 if result["summary"]["status"] != "failed" else 1
