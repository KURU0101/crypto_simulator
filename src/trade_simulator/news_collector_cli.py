from __future__ import annotations

import json

from trade_simulator.config import load_config
from trade_simulator.news_collector import build_news_collector_parser, run_news_collector


def main(argv: list[str] | None = None) -> int:
    parser = build_news_collector_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = run_news_collector(config)
    print(json.dumps(result["observation"], ensure_ascii=False, indent=2))
    return 0 if result["observation"]["status"] == "completed" else 1
