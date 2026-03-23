from __future__ import annotations

import argparse
import json

from trade_simulator.comparison import run_comparisons
from trade_simulator.config import load_config
from trade_simulator.data.ohlcv import load_returns_from_ohlcv_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strategy comparisons using returns built from local OHLCV data.")
    parser.add_argument("--config", required=True, help="Path to a real-data comparison JSON config file.")
    return parser


def load_real_data_comparison_config(config_path: str) -> tuple[dict, list[dict]]:
    config = load_config(config_path)

    if not isinstance(config, dict):
        raise ValueError("real-data comparison config must be a dict")
    if "data_source" not in config:
        raise ValueError("real-data comparison config must include data_source")
    if "cases" not in config:
        raise ValueError("real-data comparison config must include cases")
    if not isinstance(config["data_source"], dict):
        raise ValueError("data_source must be a dict")
    if not isinstance(config["cases"], list):
        raise ValueError("cases must be a list")

    return config["data_source"], config["cases"]


def prepare_cases_with_real_data_returns(data_source: dict, cases: list[dict]) -> tuple[dict, list[dict]]:
    if "ohlcv_csv_path" not in data_source:
        raise ValueError("data_source must include ohlcv_csv_path")

    returns_payload = load_returns_from_ohlcv_csv(data_source["ohlcv_csv_path"])
    prepared_cases = []

    for case in cases:
        prepared_case = dict(case)
        prepared_case["returns"] = list(returns_payload["returns"])
        if "simulation_name" not in prepared_case and "name" in prepared_case:
            prepared_case["simulation_name"] = prepared_case["name"]
        prepared_cases.append(prepared_case)

    data_summary = {
        "symbol": data_source.get("symbol", "BTC/USDT"),
        "ohlcv_csv_path": data_source["ohlcv_csv_path"],
        "price_basis": returns_payload["price_basis"],
        "ohlcv_points": len(returns_payload["timestamps"]),
        "returns_count": len(returns_payload["returns"]),
        "return_timestamps": returns_payload["return_timestamps"],
    }

    return data_summary, prepared_cases


def format_real_data_comparison_results(data_summary: dict, results: list[dict]) -> str:
    payload = {
        "data_source": data_summary,
        "results": results,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    data_source, cases = load_real_data_comparison_config(args.config)
    data_summary, prepared_cases = prepare_cases_with_real_data_returns(data_source, cases)
    results = run_comparisons(prepared_cases)
    print(format_real_data_comparison_results(data_summary, results))
    return 0
