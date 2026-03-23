from __future__ import annotations

import argparse
import json

from trade_simulator.config import load_config
from trade_simulator.data import select_data_source
from trade_simulator.pseudo_realtime_replay import run_pseudo_realtime_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pseudo-realtime replay using a source OHLCV csv and a work csv.")
    parser.add_argument("--config", required=True, help="Path to a pseudo-realtime replay JSON config file.")
    parser.add_argument("--symbol", help="Configured symbol to replay. Defaults to data_sources.default_symbol.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.symbol is not None:
        selected_source = select_data_source(config, symbol=args.symbol)
        if "data_sources" not in config:
            config["data_sources"] = {
                "default_symbol": selected_source["symbol"],
                "symbols": [config["data_source"]],
            }
        config["data_sources"]["default_symbol"] = selected_source["symbol"]
    result = run_pseudo_realtime_replay(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
