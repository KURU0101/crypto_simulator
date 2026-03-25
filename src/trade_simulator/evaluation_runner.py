from __future__ import annotations

from pathlib import Path

from trade_simulator.comparison import run_case, summarize_case_result
from trade_simulator.data.ohlcv import build_close_to_close_returns
from trade_simulator.evaluation_market_data import resolve_evaluation_market_data


class EvaluationRunnerError(Exception):
    """Base exception for single-case evaluation runner failures."""


class EmptyReturnsError(EvaluationRunnerError):
    """Raised when OHLCV data cannot produce a non-empty returns series."""


def prepare_single_case(case_config: object) -> dict:
    if not isinstance(case_config, dict):
        raise ValueError("case config must be a dict")
    if "name" not in case_config:
        raise ValueError("case config must include name")
    if not isinstance(case_config["name"], str) or not case_config["name"].strip():
        raise ValueError("case name must be a non-empty string")
    prepared_case = dict(case_config)
    if "simulation_name" not in prepared_case:
        prepared_case["simulation_name"] = prepared_case["name"]
    return prepared_case


def build_returns_payload_from_rows(ohlcv_rows: object) -> dict:
    returns_payload = build_close_to_close_returns(ohlcv_rows)
    if not returns_payload["returns"]:
        raise EmptyReturnsError("returns must not be empty for evaluation")
    return returns_payload


def evaluate_prepared_case_with_returns(
    *,
    prepared_case: dict,
    returns_payload: dict[str, object],
) -> dict[str, object]:
    executable_case = dict(prepared_case)
    executable_case["returns"] = list(returns_payload["returns"])

    case_name = str(prepared_case["name"])
    execution_config = {key: value for key, value in executable_case.items() if key != "name"}
    result = run_case(execution_config)
    summary = summarize_case_result(case_name, result)
    return {
        "case_name": case_name,
        "returns_count": len(returns_payload["returns"]),
        "price_basis": returns_payload["price_basis"],
        "summary": summary,
    }


def _build_output_payload(
    *,
    market_data_result: dict[str, object],
    case_name: str,
    returns_payload: dict[str, object],
    summary: dict[str, object],
) -> dict[str, object]:
    return {
        "acquisition_key": market_data_result["acquisition_key"],
        "artifact_path": market_data_result["artifact_path"],
        "artifact_kind": market_data_result["artifact_kind"],
        "source": market_data_result["source"],
        "symbol": market_data_result["symbol"],
        "interval": market_data_result["interval"],
        "window_start": market_data_result["window_start"],
        "window_end": market_data_result["window_end"],
        "fetched": market_data_result["fetched"],
        "reused_existing_artifact": market_data_result["reused_existing_artifact"],
        "case_name": case_name,
        "returns_count": len(returns_payload["returns"]),
        "price_basis": returns_payload["price_basis"],
        "summary": summary,
    }


def run_single_case_evaluation(
    *,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    case_config: object,
    cache_root: str | Path = "var/cache/market_data/ohlcv",
    shared_state_db_path: str | Path = "var/cache/market_data/shared_state.sqlite3",
    period_signature: str = "",
    fetcher=None,
) -> dict[str, object]:
    prepared_case = prepare_single_case(case_config)
    market_data_result = resolve_evaluation_market_data(
        source=source,
        symbol=symbol,
        interval=interval,
        window_start=window_start,
        window_end=window_end,
        cache_root=cache_root,
        shared_state_db_path=shared_state_db_path,
        period_signature=period_signature,
        fetcher=fetcher,
    )
    returns_payload = build_returns_payload_from_rows(market_data_result["rows"])
    case_result = evaluate_prepared_case_with_returns(
        prepared_case=prepared_case,
        returns_payload=returns_payload,
    )
    return _build_output_payload(
        market_data_result=market_data_result,
        case_name=str(case_result["case_name"]),
        returns_payload=returns_payload,
        summary=case_result["summary"],
    )
