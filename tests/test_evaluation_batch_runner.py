from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from trade_simulator.evaluation_batch_runner import (
    EVALUATION_BATCH_RESULT_COLUMNS,
    load_evaluation_batch_config,
    run_evaluation_batch,
)
from trade_simulator.evaluation_batch_runner_cli import main as evaluation_batch_main


def _sample_rows_a() -> list[dict[str, object]]:
    return [
        {"timestamp": "2024-01-01T00:00:00Z", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
        {"timestamp": "2024-01-01T01:00:00Z", "open": "100", "high": "103", "low": "99", "close": "102", "volume": "11"},
        {"timestamp": "2024-01-01T02:00:00Z", "open": "102", "high": "104", "low": "101", "close": "101", "volume": "12"},
    ]


def _sample_rows_b() -> list[dict[str, object]]:
    return [
        {"timestamp": "2024-02-01T00:00:00Z", "open": "200", "high": "201", "low": "199", "close": "200", "volume": "20"},
        {"timestamp": "2024-02-01T01:00:00Z", "open": "200", "high": "202", "low": "199", "close": "201", "volume": "21"},
        {"timestamp": "2024-02-01T02:00:00Z", "open": "201", "high": "203", "low": "200", "close": "202", "volume": "22"},
    ]


def _threshold_case(name: str) -> dict[str, object]:
    return {
        "name": name,
        "strategy": "threshold",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "entry_threshold": 0.01,
        "exit_threshold": -0.005,
    }


def _period(period_id: str, start: str, end: str) -> dict[str, str]:
    return {
        "period_id": period_id,
        "source": "binance_spot",
        "symbol": "BTCUSDT",
        "interval": "1h",
        "start": start,
        "end": end,
    }


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_run_evaluation_batch_runs_two_periods_and_multiple_cases(tmp_path: Path) -> None:
    fetch_calls: list[tuple[str, str]] = []

    def fetcher(**kwargs):
        fetch_calls.append((kwargs["window_start"], kwargs["window_end"]))
        if kwargs["window_start"] == "2024-01-01T00:00:00Z":
            return _sample_rows_a()
        return _sample_rows_b()

    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[
            _period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z"),
            _period("p2", "2024-02-01T00:00:00Z", "2024-02-01T03:00:00Z"),
        ],
        cases=[_threshold_case("case_a"), _threshold_case("case_b")],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_calls == [
        ("2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z"),
        ("2024-02-01T00:00:00Z", "2024-02-01T03:00:00Z"),
    ]
    assert result["total_periods"] == 2
    assert result["total_cases"] == 2
    assert result["total_rows"] == 4
    assert result["succeeded_rows"] == 4
    rows = _read_csv_rows(csv_path)
    assert len(rows) == 4
    assert set(rows[0].keys()) == set(EVALUATION_BATCH_RESULT_COLUMNS)


def test_run_evaluation_batch_reuses_market_data_within_same_period(tmp_path: Path) -> None:
    fetch_count = 0

    def fetcher(**kwargs):
        nonlocal fetch_count
        fetch_count += 1
        return _sample_rows_a()

    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[_threshold_case("case_a"), _threshold_case("case_b"), _threshold_case("case_c")],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_count == 1
    assert result["total_rows"] == 3
    rows = _read_csv_rows(csv_path)
    assert all(row["returns_count"] == "2" for row in rows)
    assert all(row["price_basis"] == "close_to_close" for row in rows)


def test_run_evaluation_batch_keeps_running_when_one_case_fails(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[
            _threshold_case("case_ok"),
            {
                "name": "case_bad",
                "strategy": "threshold",
                "initial_cash": 1000,
                "fee_rate": 0.0,
                "slippage_rate": 0.0,
            },
        ],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _sample_rows_a(),
    )

    assert result["succeeded_rows"] == 1
    assert result["failed_rows"] == 1
    rows = _read_csv_rows(csv_path)
    failed_rows = [row for row in rows if row["status"] == "failed"]
    assert len(failed_rows) == 1
    assert failed_rows[0]["case_name"] == "case_bad"
    assert failed_rows[0]["error_code"] == "ValueError"


def test_run_evaluation_batch_writes_failed_row_for_each_case_when_period_market_data_fails(tmp_path: Path) -> None:
    fetch_calls = 0

    def fetcher(**kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        if kwargs["window_start"] == "2024-01-01T00:00:00Z":
            raise RuntimeError("period fetch failed")
        return _sample_rows_b()

    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[
            _period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z"),
            _period("p2", "2024-02-01T00:00:00Z", "2024-02-01T03:00:00Z"),
        ],
        cases=[_threshold_case("case_a"), _threshold_case("case_b")],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_calls == 2
    assert result["total_rows"] == 4
    assert result["failed_rows"] == 2
    rows = _read_csv_rows(csv_path)
    failed_rows = [row for row in rows if row["period_id"] == "p1"]
    assert len(failed_rows) == 2
    assert all(row["status"] == "failed" for row in failed_rows)
    assert all(row["error_code"] == "RuntimeError" for row in failed_rows)
    assert rows[-1]["status"] == "completed"


def test_run_evaluation_batch_supports_single_period_single_case_boundary(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[_threshold_case("case_a")],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _sample_rows_a(),
    )

    assert result["total_periods"] == 1
    assert result["total_cases"] == 1
    assert result["total_rows"] == 1


def test_run_evaluation_batch_supports_multiple_periods_single_case_boundary(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    result = run_evaluation_batch(
        periods=[
            _period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z"),
            _period("p2", "2024-02-01T00:00:00Z", "2024-02-01T03:00:00Z"),
        ],
        cases=[_threshold_case("case_a")],
        output_csv_path=csv_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _sample_rows_a() if kwargs["window_start"] == "2024-01-01T00:00:00Z" else _sample_rows_b(),
    )

    assert result["total_periods"] == 2
    assert result["total_cases"] == 1
    assert result["total_rows"] == 2


def test_load_evaluation_batch_config_reads_minimal_shape() -> None:
    loaded = load_evaluation_batch_config(
        {
            "periods": [_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
            "cases": [_threshold_case("case_a")],
            "output_csv_path": "var/results.csv",
        }
    )

    assert loaded["output_csv_path"] == "var/results.csv"
    assert loaded["periods"][0]["period_id"] == "p1"
    assert loaded["cases"][0]["name"] == "case_a"


def test_evaluation_batch_runner_cli_prints_summary_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "batch.json"
    config_path.write_text(
        json.dumps(
            {
                "periods": [_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
                "cases": [_threshold_case("case_a")],
                "output_csv_path": str(tmp_path / "results.csv"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "trade_simulator.evaluation_batch_runner_cli.run_evaluation_batch",
        lambda **kwargs: {
            "total_periods": 1,
            "total_cases": 1,
            "total_rows": 1,
            "succeeded_rows": 1,
            "failed_rows": 0,
            "output_csv_path": kwargs["output_csv_path"],
        },
    )

    exit_code = evaluation_batch_main(["--config", str(config_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_rows"] == 1
