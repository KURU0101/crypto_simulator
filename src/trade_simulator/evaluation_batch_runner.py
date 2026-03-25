from __future__ import annotations

import csv
from itertools import islice
from pathlib import Path

from trade_simulator.evaluation_market_data import (
    build_market_data_acquisition_key,
    resolve_evaluation_market_data,
)
from trade_simulator.evaluation_runner import (
    build_returns_payload_from_rows,
    evaluate_prepared_case_with_returns,
    prepare_single_case,
)


DEFAULT_CASE_CHUNK_SIZE = 100
EVALUATION_BATCH_RESULT_COLUMNS = (
    "period_id",
    "source",
    "symbol",
    "interval",
    "window_start",
    "window_end",
    "acquisition_key",
    "artifact_path",
    "fetched",
    "reused_existing_artifact",
    "case_name",
    "status",
    "error_code",
    "error_message",
    "returns_count",
    "price_basis",
    "final_value",
    "trade_count",
    "completed_trade_count",
    "open_trade_count",
    "win_rate",
    "realized_pnl_total",
    "average_holding_period",
    "total_cost_amount",
)


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int")
    return value


def _validate_batch_period(period_config: object, index: int) -> dict:
    if not isinstance(period_config, dict):
        raise ValueError(f"periods[{index}] must be a dict")
    required_keys = ("period_id", "source", "symbol", "start", "end", "interval")
    for key in required_keys:
        if key not in period_config:
            raise ValueError(f"periods[{index}] must include {key}")
        if not isinstance(period_config[key], str) or not str(period_config[key]).strip():
            raise ValueError(f"periods[{index}].{key} must be a non-empty string")
    normalized = dict(period_config)
    normalized["period_id"] = str(period_config["period_id"]).strip()
    normalized["source"] = str(period_config["source"]).strip()
    normalized["symbol"] = str(period_config["symbol"]).strip()
    normalized["start"] = str(period_config["start"]).strip()
    normalized["end"] = str(period_config["end"]).strip()
    normalized["interval"] = str(period_config["interval"]).strip()
    normalized["period_signature"] = str(period_config.get("period_signature", "")).strip()
    return normalized


def load_evaluation_batch_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("evaluation batch config must be a dict")
    if "periods" not in config or not isinstance(config["periods"], list):
        raise ValueError("evaluation batch config must include periods as a list")
    if "cases" not in config or not isinstance(config["cases"], list):
        raise ValueError("evaluation batch config must include cases as a list")
    if "output_csv_path" not in config or not isinstance(config["output_csv_path"], str) or not config["output_csv_path"].strip():
        raise ValueError("evaluation batch config must include output_csv_path")

    periods = [_validate_batch_period(period, index) for index, period in enumerate(config["periods"])]
    cases = [prepare_single_case(case) for case in config["cases"]]
    if not periods:
        raise ValueError("periods must not be empty")
    if not cases:
        raise ValueError("cases must not be empty")

    return {
        "periods": periods,
        "cases": cases,
        "output_csv_path": str(config["output_csv_path"]).strip(),
        "cache_root": str(config.get("cache_root", "var/cache/market_data/ohlcv")),
        "shared_state_db_path": str(config.get("shared_state_db_path", "var/cache/market_data/shared_state.sqlite3")),
        "case_chunk_size": _validate_positive_int(config.get("case_chunk_size", DEFAULT_CASE_CHUNK_SIZE), "case_chunk_size"),
        "dry_run": bool(config.get("dry_run", False)),
    }


def _build_market_data_error_row(
    *,
    period: dict,
    case_name: str,
    acquisition_key: str,
    error: Exception,
) -> dict[str, object]:
    return {
        "period_id": period["period_id"],
        "source": period["source"],
        "symbol": period["symbol"],
        "interval": period["interval"],
        "window_start": period["start"],
        "window_end": period["end"],
        "acquisition_key": acquisition_key,
        "artifact_path": "",
        "fetched": "",
        "reused_existing_artifact": "",
        "case_name": case_name,
        "status": "failed",
        "error_code": type(error).__name__,
        "error_message": str(error),
        "returns_count": 0,
        "price_basis": "",
        "final_value": "",
        "trade_count": "",
        "completed_trade_count": "",
        "open_trade_count": "",
        "win_rate": "",
        "realized_pnl_total": "",
        "average_holding_period": "",
        "total_cost_amount": "",
    }


def _build_case_error_row(
    *,
    period: dict,
    market_data_result: dict[str, object],
    returns_payload: dict[str, object],
    case_name: str,
    error: Exception,
) -> dict[str, object]:
    return {
        "period_id": period["period_id"],
        "source": period["source"],
        "symbol": period["symbol"],
        "interval": period["interval"],
        "window_start": period["start"],
        "window_end": period["end"],
        "acquisition_key": market_data_result["acquisition_key"],
        "artifact_path": market_data_result["artifact_path"],
        "fetched": market_data_result["fetched"],
        "reused_existing_artifact": market_data_result["reused_existing_artifact"],
        "case_name": case_name,
        "status": "failed",
        "error_code": type(error).__name__,
        "error_message": str(error),
        "returns_count": len(returns_payload["returns"]),
        "price_basis": returns_payload["price_basis"],
        "final_value": "",
        "trade_count": "",
        "completed_trade_count": "",
        "open_trade_count": "",
        "win_rate": "",
        "realized_pnl_total": "",
        "average_holding_period": "",
        "total_cost_amount": "",
    }


def _build_success_row(
    *,
    period: dict,
    market_data_result: dict[str, object],
    case_result: dict[str, object],
) -> dict[str, object]:
    summary = case_result["summary"]
    return {
        "period_id": period["period_id"],
        "source": period["source"],
        "symbol": period["symbol"],
        "interval": period["interval"],
        "window_start": period["start"],
        "window_end": period["end"],
        "acquisition_key": market_data_result["acquisition_key"],
        "artifact_path": market_data_result["artifact_path"],
        "fetched": market_data_result["fetched"],
        "reused_existing_artifact": market_data_result["reused_existing_artifact"],
        "case_name": case_result["case_name"],
        "status": "completed",
        "error_code": "",
        "error_message": "",
        "returns_count": case_result["returns_count"],
        "price_basis": case_result["price_basis"],
        "final_value": summary["final_value"],
        "trade_count": summary["trade_count"],
        "completed_trade_count": summary["completed_trade_count"],
        "open_trade_count": summary["open_trade_count"],
        "win_rate": summary["win_rate"],
        "realized_pnl_total": summary["realized_pnl_total"],
        "average_holding_period": summary["average_holding_period"],
        "total_cost_amount": summary.get("total_cost_amount", ""),
    }


def _initialize_output_csv(output_csv_path: str | Path) -> Path:
    path = Path(output_csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EVALUATION_BATCH_RESULT_COLUMNS)
        writer.writeheader()
    return path


def _append_csv_rows(output_csv_path: str | Path, rows: list[dict[str, object]]) -> Path:
    path = Path(output_csv_path)
    if not rows:
        return path
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EVALUATION_BATCH_RESULT_COLUMNS)
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EVALUATION_BATCH_RESULT_COLUMNS})
    return path


def _iter_case_chunks(cases: list[dict], case_chunk_size: int):
    iterator = iter(cases)
    while True:
        chunk = list(islice(iterator, case_chunk_size))
        if not chunk:
            return
        yield chunk


def _build_dry_run_result(
    *,
    periods: list[dict],
    cases: list[dict],
    output_csv_path: str | Path,
    case_chunk_size: int,
    cache_root: str | Path,
    shared_state_db_path: str | Path,
) -> dict[str, object]:
    return {
        "dry_run": True,
        "total_periods": len(periods),
        "total_cases": len(cases),
        "planned_rows": len(periods) * len(cases),
        "case_chunk_size": case_chunk_size,
        "output_csv_path": str(output_csv_path),
        "cache_root": str(cache_root),
        "shared_state_db_path": str(shared_state_db_path),
    }


def run_evaluation_batch(
    *,
    periods: list[dict],
    cases: list[dict],
    output_csv_path: str | Path,
    cache_root: str | Path = "var/cache/market_data/ohlcv",
    shared_state_db_path: str | Path = "var/cache/market_data/shared_state.sqlite3",
    case_chunk_size: int = DEFAULT_CASE_CHUNK_SIZE,
    dry_run: bool = False,
    fetcher=None,
) -> dict[str, object]:
    prepared_cases = [prepare_single_case(case) for case in cases]
    resolved_case_chunk_size = _validate_positive_int(case_chunk_size, "case_chunk_size")

    if dry_run:
        return _build_dry_run_result(
            periods=periods,
            cases=prepared_cases,
            output_csv_path=output_csv_path,
            case_chunk_size=resolved_case_chunk_size,
            cache_root=cache_root,
            shared_state_db_path=shared_state_db_path,
        )

    csv_path = _initialize_output_csv(output_csv_path)
    total_rows = 0
    failed_rows = 0
    succeeded_rows = 0

    for period in periods:
        acquisition_key = build_market_data_acquisition_key(
            source=period["source"],
            symbol=period["symbol"],
            interval=period["interval"],
            window_start=period["start"],
            window_end=period["end"],
        )
        try:
            market_data_result = resolve_evaluation_market_data(
                source=period["source"],
                symbol=period["symbol"],
                interval=period["interval"],
                window_start=period["start"],
                window_end=period["end"],
                cache_root=cache_root,
                shared_state_db_path=shared_state_db_path,
                period_signature=period.get("period_signature", ""),
                fetcher=fetcher,
            )
            returns_payload = build_returns_payload_from_rows(market_data_result["rows"])
        except Exception as error:
            for case_chunk in _iter_case_chunks(prepared_cases, resolved_case_chunk_size):
                chunk_rows = [
                    _build_market_data_error_row(
                        period=period,
                        case_name=str(case["name"]),
                        acquisition_key=acquisition_key,
                        error=error,
                    )
                    for case in case_chunk
                ]
                _append_csv_rows(csv_path, chunk_rows)
                total_rows += len(chunk_rows)
                failed_rows += len(chunk_rows)
            continue

        for case_chunk in _iter_case_chunks(prepared_cases, resolved_case_chunk_size):
            chunk_rows: list[dict[str, object]] = []
            for case in case_chunk:
                try:
                    case_result = evaluate_prepared_case_with_returns(
                        prepared_case=case,
                        returns_payload=returns_payload,
                    )
                except Exception as error:
                    chunk_rows.append(
                        _build_case_error_row(
                            period=period,
                            market_data_result=market_data_result,
                            returns_payload=returns_payload,
                            case_name=str(case["name"]),
                            error=error,
                        )
                    )
                    failed_rows += 1
                    continue

                chunk_rows.append(
                    _build_success_row(
                        period=period,
                        market_data_result=market_data_result,
                        case_result=case_result,
                    )
                )
                succeeded_rows += 1
            _append_csv_rows(csv_path, chunk_rows)
            total_rows += len(chunk_rows)

    return {
        "dry_run": False,
        "total_periods": len(periods),
        "total_cases": len(prepared_cases),
        "case_chunk_size": resolved_case_chunk_size,
        "total_rows": total_rows,
        "succeeded_rows": succeeded_rows,
        "failed_rows": failed_rows,
        "output_csv_path": str(csv_path),
    }
