from __future__ import annotations

import json

from trade_simulator.config import load_config
from trade_simulator.sns_collector import build_sns_collector_parser, run_sns_collector


def main(argv: list[str] | None = None) -> int:
    parser = build_sns_collector_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = run_sns_collector(config)
    print(json.dumps(result["observation"], ensure_ascii=False, indent=2))
    return 0 if result["observation"]["status"] == "completed" else 1
