from __future__ import annotations

import argparse
import json

from trade_simulator.comparison import run_comparisons
from trade_simulator.config import load_config
from trade_simulator.data import load_data_sources_config, load_returns_by_symbol


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strategy comparisons using returns built from local OHLCV data.")
    parser.add_argument("--config", required=True, help="Path to a real-data comparison JSON config file.")
    parser.add_argument("--symbol", help="Configured symbol to evaluate. Defaults to data_sources.default_symbol.")
    return parser


def load_real_data_comparison_config(config_path: str) -> tuple[dict, list[dict]]:
    config = load_config(config_path)

    if not isinstance(config, dict):
        raise ValueError("real-data comparison config must be a dict")
    if "data_source" not in config and "data_sources" not in config:
        raise ValueError("real-data comparison config must include data_source or data_sources")
    if "cases" not in config:
        raise ValueError("real-data comparison config must include cases")
    if not isinstance(config["cases"], list):
        raise ValueError("cases must be a list")

    data_source_config = {}
    if "data_source" in config:
        data_source_config["data_source"] = config["data_source"]
    if "data_sources" in config:
        data_source_config["data_sources"] = config["data_sources"]

    load_data_sources_config(data_source_config)
    return data_source_config, config["cases"]


def prepare_cases_with_real_data_returns(
    data_source_config: dict,
    cases: list[dict],
    *,
    symbol: str | None = None,
) -> tuple[dict, list[dict]]:
    data_sources = load_data_sources_config(data_source_config)
    selected_symbol = symbol or data_sources["default_symbol"]
    returns_by_symbol = load_returns_by_symbol(data_source_config)
    if selected_symbol not in returns_by_symbol:
        raise ValueError(f"symbol must be one of: {', '.join(data_sources['symbols'])}")

    returns_payload = returns_by_symbol[selected_symbol]
    prepared_cases = []

    for case in cases:
        prepared_case = dict(case)
        prepared_case["returns"] = list(returns_payload["returns"])
        if "simulation_name" not in prepared_case and "name" in prepared_case:
            prepared_case["simulation_name"] = prepared_case["name"]
        prepared_cases.append(prepared_case)

    data_summary = {
        "symbol": selected_symbol,
        "default_symbol": data_sources["default_symbol"],
        "available_symbols": data_sources["symbols"],
        "ohlcv_csv_path": returns_payload["ohlcv_csv_path"],
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
    data_summary, prepared_cases = prepare_cases_with_real_data_returns(data_source, cases, symbol=args.symbol)
    results = run_comparisons(prepared_cases)
    print(format_real_data_comparison_results(data_summary, results))
    return 0
