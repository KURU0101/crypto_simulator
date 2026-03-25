from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from trade_simulator.evaluation_batch_runner import run_evaluation_batch


def _sample_rows() -> list[dict[str, object]]:
    return [
        {"timestamp": "2024-01-01T00:00:00Z", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
        {"timestamp": "2024-01-01T01:00:00Z", "open": "100", "high": "103", "low": "99", "close": "102", "volume": "11"},
        {"timestamp": "2024-01-01T02:00:00Z", "open": "102", "high": "104", "low": "101", "close": "101", "volume": "12"},
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


def _fetch_run_row(db_path: Path, run_id: str) -> dict[str, object]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM evaluation_runs WHERE run_id = ?", (run_id,)).fetchone()
        assert row is not None
        return dict(row)


def _fetch_result_rows(db_path: Path, run_id: str) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM evaluation_results WHERE run_id = ? ORDER BY period_id, case_name",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def test_run_evaluation_batch_writes_success_rows_to_db_and_run_meta(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    db_path = tmp_path / "results.sqlite3"

    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[_threshold_case("case_a")],
        output_csv_path=csv_path,
        results_db_path=db_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        config_path="config/evaluation_batch.example.json",
        fetcher=lambda **kwargs: _sample_rows(),
    )

    assert result["run_status"] == "completed"
    assert result["planned_rows"] == 1
    assert result["results_db_path"] == str(db_path)
    run_row = _fetch_run_row(db_path, result["run_id"])
    assert run_row["status"] == "completed"
    assert run_row["config_path"] == "config/evaluation_batch.example.json"
    assert run_row["planned_rows"] == 1
    assert run_row["succeeded_rows"] == 1
    assert run_row["failed_rows"] == 0
    assert run_row["output_csv_path"] == str(csv_path)
    result_rows = _fetch_result_rows(db_path, result["run_id"])
    assert len(result_rows) == 1
    assert result_rows[0]["status"] == "completed"
    assert result_rows[0]["case_name"] == "case_a"


def test_run_evaluation_batch_writes_failed_case_row_to_db(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    db_path = tmp_path / "results.sqlite3"

    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[
            _threshold_case("case_ok"),
            {"name": "case_bad", "strategy": "threshold", "initial_cash": 1000},
        ],
        output_csv_path=csv_path,
        results_db_path=db_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _sample_rows(),
    )

    assert result["run_status"] == "completed_with_failures"
    run_row = _fetch_run_row(db_path, result["run_id"])
    assert run_row["failed_rows"] == 1
    result_rows = _fetch_result_rows(db_path, result["run_id"])
    assert len(result_rows) == 2
    failed_rows = [row for row in result_rows if row["status"] == "failed"]
    assert len(failed_rows) == 1
    assert failed_rows[0]["case_name"] == "case_bad"
    assert failed_rows[0]["error_code"] == "ValueError"


def test_run_evaluation_batch_writes_period_failure_rows_to_db(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    db_path = tmp_path / "results.sqlite3"

    def fetcher(**kwargs):
        if kwargs["window_start"] == "2024-01-01T00:00:00Z":
            raise RuntimeError("period fetch failed")
        return _sample_rows()

    result = run_evaluation_batch(
        periods=[
            _period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z"),
            _period("p2", "2024-02-01T00:00:00Z", "2024-02-01T03:00:00Z"),
        ],
        cases=[_threshold_case("case_a"), _threshold_case("case_b")],
        output_csv_path=csv_path,
        results_db_path=db_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    run_row = _fetch_run_row(db_path, result["run_id"])
    assert run_row["status"] == "completed_with_failures"
    assert run_row["failed_rows"] == 2
    result_rows = _fetch_result_rows(db_path, result["run_id"])
    failed_rows = [row for row in result_rows if row["period_id"] == "p1"]
    assert len(failed_rows) == 2
    assert all(row["status"] == "failed" for row in failed_rows)
    assert all(row["error_code"] == "RuntimeError" for row in failed_rows)


def test_run_evaluation_batch_keeps_csv_and_db_row_counts_aligned_for_chunked_run(
    tmp_path: Path, monkeypatch
) -> None:
    from trade_simulator import evaluation_batch_runner as batch_runner_module

    inserted_chunk_sizes: list[int] = []
    original_insert_result_rows = batch_runner_module.insert_evaluation_result_rows

    def recording_insert_result_rows(db_path, *, run_id, rows):
        inserted_chunk_sizes.append(len(rows))
        return original_insert_result_rows(db_path, run_id=run_id, rows=rows)

    monkeypatch.setattr(
        "trade_simulator.evaluation_batch_runner.insert_evaluation_result_rows",
        recording_insert_result_rows,
    )

    csv_path = tmp_path / "results.csv"
    db_path = tmp_path / "results.sqlite3"
    result = run_evaluation_batch(
        periods=[_period("p1", "2024-01-01T00:00:00Z", "2024-01-01T03:00:00Z")],
        cases=[
            _threshold_case("case_a"),
            _threshold_case("case_b"),
            _threshold_case("case_c"),
            _threshold_case("case_d"),
            _threshold_case("case_e"),
        ],
        output_csv_path=csv_path,
        results_db_path=db_path,
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        case_chunk_size=2,
        fetcher=lambda **kwargs: _sample_rows(),
    )

    csv_rows = _read_csv_rows(csv_path)
    db_rows = _fetch_result_rows(db_path, result["run_id"])
    run_row = _fetch_run_row(db_path, result["run_id"])
    assert inserted_chunk_sizes == [2, 2, 1]
    assert len(csv_rows) == 5
    assert len(db_rows) == 5
    assert run_row["planned_rows"] == 5
    assert run_row["succeeded_rows"] == 5
    assert run_row["failed_rows"] == 0
