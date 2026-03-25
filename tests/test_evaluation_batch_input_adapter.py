from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from trade_simulator.evaluation_batch_input_adapter import (
    build_generated_case_iterator_factory,
    count_generated_cases,
    load_batch_input_adapter_config,
    load_case_templates_json,
    load_periods_from_csv,
    resolve_batch_execution_inputs,
)
from trade_simulator.evaluation_batch_input_adapter_cli import main as evaluation_batch_input_main
from trade_simulator.evaluation_batch_runner import run_evaluation_batch


def _write_periods_csv(path: Path) -> None:
    rows = [
        {
            "period_id": "p1",
            "source": "binance_spot",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-01T03:00:00Z",
            "period_signature": "",
        },
        {
            "period_id": "p2",
            "source": "binance_spot",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "start": "2024-02-01T00:00:00Z",
            "end": "2024-02-01T03:00:00Z",
            "period_signature": "",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["period_id", "source", "symbol", "interval", "start", "end", "period_signature"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_case_templates_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "template_name": "threshold_base",
                    "case": {
                        "strategy": "threshold",
                        "initial_cash": 1000,
                        "fee_rate": 0.0,
                        "slippage_rate": 0.0,
                        "entry_threshold": 0.01,
                        "exit_threshold": -0.01,
                    },
                },
                {
                    "template_name": "threshold_cost",
                    "case": {
                        "strategy": "threshold",
                        "initial_cash": 1000,
                        "fee_rate": 0.001,
                        "slippage_rate": 0.001,
                        "entry_threshold": 0.01,
                        "exit_threshold": -0.01,
                    },
                },
            ]
        ),
        encoding="utf-8",
    )


def _write_grids_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["grid_id", "template_name", "overrides_json", "enabled"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_sqlite_rows(db_path: Path, query: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return list(connection.execute(query))
    finally:
        connection.close()


def _sample_rows() -> list[dict[str, object]]:
    return [
        {"timestamp": "2024-01-01T00:00:00Z", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10"},
        {"timestamp": "2024-01-01T01:00:00Z", "open": "100", "high": "103", "low": "99", "close": "102", "volume": "11"},
        {"timestamp": "2024-01-01T02:00:00Z", "open": "102", "high": "104", "low": "101", "close": "101", "volume": "12"},
    ]


def test_load_periods_and_case_templates_from_adapter_inputs(tmp_path: Path) -> None:
    periods_csv_path = tmp_path / "periods.csv"
    templates_json_path = tmp_path / "templates.json"
    _write_periods_csv(periods_csv_path)
    _write_case_templates_json(templates_json_path)

    periods = load_periods_from_csv(periods_csv_path, period_limit=1)
    templates = load_case_templates_json(templates_json_path)

    assert len(periods) == 1
    assert periods[0]["period_id"] == "p1"
    assert set(templates.keys()) == {"threshold_base", "threshold_cost"}


def test_generated_case_iterator_builds_unique_case_names_and_case_limit(tmp_path: Path) -> None:
    templates_json_path = tmp_path / "templates.json"
    grids_csv_path = tmp_path / "grids.csv"
    _write_case_templates_json(templates_json_path)
    _write_grids_csv(
        grids_csv_path,
        [
            {
                "grid_id": "g1",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.01, "exit_threshold": -0.01}),
                "enabled": "true",
            },
            {
                "grid_id": "g2",
                "template_name": "threshold_cost",
                "overrides_json": json.dumps({"entry_threshold": 0.02, "exit_threshold": -0.02}),
                "enabled": "true",
            },
        ],
    )

    templates = load_case_templates_json(templates_json_path)
    count = count_generated_cases(case_templates=templates, grids_csv_path=grids_csv_path, case_limit=1)
    iterator = build_generated_case_iterator_factory(
        case_templates=templates,
        grids_csv_path=grids_csv_path,
        case_limit=2,
    )
    generated_cases = list(iterator())

    assert count == 1
    assert [case["name"] for case in generated_cases] == ["threshold_base__g1", "threshold_cost__g2"]
    assert all(case["simulation_name"] == case["name"] for case in generated_cases)


def test_generated_case_iterator_rejects_duplicate_generated_case_names(tmp_path: Path) -> None:
    templates_json_path = tmp_path / "templates.json"
    grids_csv_path = tmp_path / "grids.csv"
    _write_case_templates_json(templates_json_path)
    _write_grids_csv(
        grids_csv_path,
        [
            {
                "grid_id": "same",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.01}),
                "enabled": "true",
            },
            {
                "grid_id": "same",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.02}),
                "enabled": "true",
            },
        ],
    )

    templates = load_case_templates_json(templates_json_path)
    with pytest.raises(ValueError, match="generated case_name must be unique"):
        count_generated_cases(case_templates=templates, grids_csv_path=grids_csv_path)


def test_resolve_batch_execution_inputs_applies_limits_and_exposes_factory(tmp_path: Path) -> None:
    periods_csv_path = tmp_path / "periods.csv"
    templates_json_path = tmp_path / "templates.json"
    grids_csv_path = tmp_path / "grids.csv"
    _write_periods_csv(periods_csv_path)
    _write_case_templates_json(templates_json_path)
    _write_grids_csv(
        grids_csv_path,
        [
            {
                "grid_id": "g1",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.01}),
                "enabled": "true",
            },
            {
                "grid_id": "g2",
                "template_name": "threshold_cost",
                "overrides_json": json.dumps({"entry_threshold": 0.02}),
                "enabled": "true",
            },
        ],
    )

    adapter_config = load_batch_input_adapter_config(
        {
            "input": {
                "periods_csv_path": str(periods_csv_path),
                "case_templates_json_path": str(templates_json_path),
                "grids_csv_path": str(grids_csv_path),
                "period_limit": 1,
                "case_limit": 1,
            },
            "execution": {
                "output_csv_path": str(tmp_path / "results.csv"),
                "case_chunk_size": 3,
                "dry_run": True,
            },
        }
    )

    resolved = resolve_batch_execution_inputs(adapter_config)
    generated_cases = list(resolved["case_iterator_factory"]())

    assert len(resolved["periods"]) == 1
    assert resolved["total_cases"] == 1
    assert generated_cases[0]["name"] == "threshold_base__g1"
    assert resolved["case_chunk_size"] == 3
    assert resolved["dry_run"] is True


def test_run_evaluation_batch_supports_adapter_case_iterator_and_keeps_csv_db_aligned(tmp_path: Path) -> None:
    periods_csv_path = tmp_path / "periods.csv"
    templates_json_path = tmp_path / "templates.json"
    grids_csv_path = tmp_path / "grids.csv"
    _write_periods_csv(periods_csv_path)
    _write_case_templates_json(templates_json_path)
    _write_grids_csv(
        grids_csv_path,
        [
            {
                "grid_id": "g1",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.01}),
                "enabled": "true",
            },
            {
                "grid_id": "g2",
                "template_name": "threshold_cost",
                "overrides_json": json.dumps({"entry_threshold": 0.02}),
                "enabled": "true",
            },
            {
                "grid_id": "g3",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.03}),
                "enabled": "true",
            },
        ],
    )
    resolved = resolve_batch_execution_inputs(
        load_batch_input_adapter_config(
            {
                "input": {
                    "periods_csv_path": str(periods_csv_path),
                    "case_templates_json_path": str(templates_json_path),
                    "grids_csv_path": str(grids_csv_path),
                },
                "execution": {
                    "output_csv_path": str(tmp_path / "results.csv"),
                    "results_db_path": str(tmp_path / "results.sqlite3"),
                    "cache_root": str(tmp_path / "cache"),
                    "shared_state_db_path": str(tmp_path / "shared.sqlite3"),
                    "case_chunk_size": 2,
                },
            }
        )
    )

    result = run_evaluation_batch(
        periods=resolved["periods"],
        case_iterator_factory=resolved["case_iterator_factory"],
        total_cases=resolved["total_cases"],
        output_csv_path=resolved["output_csv_path"],
        results_db_path=resolved["results_db_path"],
        cache_root=resolved["cache_root"],
        shared_state_db_path=resolved["shared_state_db_path"],
        case_chunk_size=resolved["case_chunk_size"],
        config_fingerprint_payload=resolved["config_fingerprint_payload"],
        fetcher=lambda **kwargs: _sample_rows(),
    )

    csv_rows = list(csv.DictReader((tmp_path / "results.csv").open("r", encoding="utf-8", newline="")))
    db_rows = _read_sqlite_rows(tmp_path / "results.sqlite3", "SELECT case_name FROM evaluation_results ORDER BY case_name")

    assert result["total_periods"] == 2
    assert result["total_cases"] == 3
    assert result["total_rows"] == 6
    assert len(csv_rows) == 6
    assert len(db_rows) == 6
    assert sorted(row["case_name"] for row in csv_rows) == [row["case_name"] for row in db_rows]


def test_run_evaluation_batch_from_inputs_dry_run_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    periods_csv_path = tmp_path / "periods.csv"
    templates_json_path = tmp_path / "templates.json"
    grids_csv_path = tmp_path / "grids.csv"
    config_path = tmp_path / "input_config.json"
    _write_periods_csv(periods_csv_path)
    _write_case_templates_json(templates_json_path)
    _write_grids_csv(
        grids_csv_path,
        [
            {
                "grid_id": "g1",
                "template_name": "threshold_base",
                "overrides_json": json.dumps({"entry_threshold": 0.01}),
                "enabled": "true",
            },
            {
                "grid_id": "g2",
                "template_name": "threshold_cost",
                "overrides_json": json.dumps({"entry_threshold": 0.02}),
                "enabled": "true",
            },
        ],
    )
    config_path.write_text(
        json.dumps(
            {
                "input": {
                    "periods_csv_path": str(periods_csv_path),
                    "case_templates_json_path": str(templates_json_path),
                    "grids_csv_path": str(grids_csv_path),
                    "period_limit": 1,
                    "case_limit": 1,
                },
                "execution": {
                    "output_csv_path": str(tmp_path / "results.csv"),
                    "results_db_path": str(tmp_path / "results.sqlite3"),
                    "case_chunk_size": 4,
                    "dry_run": True,
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = evaluation_batch_input_main(["--config", str(config_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["planned_rows"] == 1
    assert payload["case_chunk_size"] == 4
