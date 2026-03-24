from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from trade_simulator.research_manifest import (
    ENGINE_VERSION,
    INPUT_SCHEMA_VERSION,
    build_manifest_rows,
    generate_research_manifest_run,
    load_grid_rows,
    load_period_rows,
    select_eligible_signal_only_grids,
)
from trade_simulator.research_manifest_cli import format_research_manifest_run, main as research_manifest_main


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def _write_valid_periods_csv(path: Path) -> None:
    _write_csv(
        path,
        [
            "period_id",
            "event_date",
            "window_start",
            "window_end",
            "short_name",
            "event_type",
            "symbol",
            "note",
            "overlap_group",
        ],
        [
            [
                "p_alpha",
                "2024-01-10",
                "2024-01-09",
                "2024-01-11",
                "ETF approval",
                "etf",
                "BTCUSD",
                "baseline note",
                "g1",
            ],
            [
                "p_minimal",
                "2024-02-01",
                "2024-02-01",
                "2024-02-01",
                "Single-day event",
                "policy",
                "ETHUSD",
                "same day window",
                "g2",
            ],
        ],
    )


def _write_valid_grids_csv(path: Path) -> None:
    _write_csv(
        path,
        [
            "grid_id",
            "grid_family",
            "consumption_series_name",
            "entry_count_threshold",
            "exit_after_inactive_periods",
            "take_profit",
            "stop_loss",
            "max_hold_minutes",
            "price_spike_limit",
            "volume_multiplier",
            "enabled",
            "note",
        ],
        [
            [
                "g_enabled",
                "signal_only",
                "weighted_matching_signal_count",
                "1.4",
                "2",
                "",
                "",
                "",
                "",
                "",
                "true",
                "eligible row",
            ],
            [
                "g_disabled",
                "signal_only",
                "weighted_matching_signal_count",
                "1.6",
                "1",
                "",
                "",
                "",
                "",
                "",
                "false",
                "disabled row",
            ],
            [
                "g_other_family",
                "minimal",
                "weighted_matching_signal_count",
                "1.8",
                "3",
                "0.03",
                "-0.02",
                "1440",
                "0.05",
                "1.5",
                "true",
                "different family",
            ],
        ],
    )


def test_generate_research_manifest_run_creates_manifest_and_fixed_input_copies(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        run_root_dir=run_root_dir,
        run_id="20260324T010203Z_deadbeef",
    )

    assert result.run_dir == run_root_dir / "20260324T010203Z_deadbeef"
    assert result.periods_copy_path.read_text(encoding="utf-8") == periods_path.read_text(encoding="utf-8")
    assert result.grids_copy_path.read_text(encoding="utf-8") == grids_path.read_text(encoding="utf-8")

    manifest_rows = list(csv.DictReader(result.manifest_path.open("r", encoding="utf-8", newline="")))
    results_rows = list(csv.DictReader(result.results_index_path.open("r", encoding="utf-8", newline="")))
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

    assert len(manifest_rows) == 2
    assert {row["case_id"] for row in manifest_rows} == {
        "p_alpha__g_enabled",
        "p_minimal__g_enabled",
    }
    assert {row["grid_family"] for row in manifest_rows} == {"signal_only"}
    assert {row["consumption_series_name"] for row in manifest_rows} == {"weighted_matching_signal_count"}

    assert len(results_rows) == 2
    assert {row["status"] for row in results_rows} == {"pending"}

    assert metadata == {
        "run_id": "20260324T010203Z_deadbeef",
        "created_at": metadata["created_at"],
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "periods_file_name": "periods.csv",
        "grids_file_name": "grids.csv",
        "period_row_count": 2,
        "grid_row_count": 3,
        "eligible_grid_row_count": 1,
        "manifest_case_count": 2,
    }


def test_signatures_are_stable_and_exclude_note_enabled_and_grid_family(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    period_rows = load_period_rows(periods_path)
    grid_rows = load_grid_rows(grids_path)
    eligible_grid_rows = select_eligible_signal_only_grids(grid_rows)
    manifest_rows = build_manifest_rows(period_rows, eligible_grid_rows, run_id="run_fixed")

    original_period_signature = period_rows[0]["period_signature"]
    original_grid_signature = eligible_grid_rows[0]["grid_signature"]
    original_case_signature = manifest_rows[0]["case_signature"]

    _write_csv(
        periods_path,
        [
            "period_id",
            "event_date",
            "window_start",
            "window_end",
            "short_name",
            "event_type",
            "symbol",
            "note",
            "overlap_group",
        ],
        [
            [
                "p_alpha",
                "2024-01-10",
                "2024-01-09",
                "2024-01-11",
                "ETF approval",
                "etf",
                "BTCUSD",
                "changed note",
                "g1",
            ]
        ],
    )
    _write_csv(
        grids_path,
        [
            "grid_id",
            "grid_family",
            "consumption_series_name",
            "entry_count_threshold",
            "exit_after_inactive_periods",
            "take_profit",
            "stop_loss",
            "max_hold_minutes",
            "price_spike_limit",
            "volume_multiplier",
            "enabled",
            "note",
        ],
        [
            [
                "g_enabled",
                "experimental_family",
                "weighted_matching_signal_count",
                "1.40",
                "2",
                "",
                "",
                "",
                "",
                "",
                "false",
                "changed note",
            ]
        ],
    )

    updated_period_rows = load_period_rows(periods_path)
    updated_grid_rows = load_grid_rows(grids_path)
    updated_manifest_rows = build_manifest_rows(updated_period_rows, updated_grid_rows, run_id="run_fixed")

    assert updated_period_rows[0]["period_signature"] == original_period_signature
    assert updated_grid_rows[0]["grid_signature"] == original_grid_signature
    assert updated_manifest_rows[0]["case_signature"] == original_case_signature


def test_optional_numeric_fields_are_loaded_as_null_for_signal_only_rows(tmp_path: Path) -> None:
    grids_path = tmp_path / "grids.csv"
    _write_valid_grids_csv(grids_path)

    grid_rows = load_grid_rows(grids_path)
    eligible_row = next(row for row in grid_rows if row["grid_id"] == "g_enabled")

    assert eligible_row["take_profit"] is None
    assert eligible_row["stop_loss"] is None
    assert eligible_row["max_hold_minutes"] is None
    assert eligible_row["price_spike_limit"] is None
    assert eligible_row["volume_multiplier"] is None


def test_load_period_rows_rejects_missing_required_column(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_csv(
        periods_path,
        ["period_id", "event_date"],
        [["p_alpha", "2024-01-10"]],
    )

    with pytest.raises(ValueError, match="periods csv missing required columns"):
        load_period_rows(periods_path)


def test_load_period_rows_rejects_duplicate_period_id(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_csv(
        periods_path,
        [
            "period_id",
            "event_date",
            "window_start",
            "window_end",
            "short_name",
            "event_type",
            "symbol",
            "note",
            "overlap_group",
        ],
        [
            ["p_dup", "2024-01-10", "2024-01-09", "2024-01-11", "A", "etf", "BTCUSD", "x", "g1"],
            ["p_dup", "2024-01-12", "2024-01-11", "2024-01-13", "B", "etf", "BTCUSD", "y", "g2"],
        ],
    )

    with pytest.raises(ValueError, match="period_id must be unique: p_dup"):
        load_period_rows(periods_path)


def test_load_grid_rows_rejects_duplicate_grid_id(tmp_path: Path) -> None:
    grids_path = tmp_path / "grids.csv"
    _write_csv(
        grids_path,
        [
            "grid_id",
            "grid_family",
            "consumption_series_name",
            "entry_count_threshold",
            "exit_after_inactive_periods",
            "take_profit",
            "stop_loss",
            "max_hold_minutes",
            "price_spike_limit",
            "volume_multiplier",
            "enabled",
            "note",
        ],
        [
            ["g_dup", "signal_only", "weighted_matching_signal_count", "1.4", "2", "", "", "", "", "", "true", "x"],
            ["g_dup", "signal_only", "weighted_matching_signal_count", "1.5", "3", "", "", "", "", "", "true", "y"],
        ],
    )

    with pytest.raises(ValueError, match="grid_id must be unique: g_dup"):
        load_grid_rows(grids_path)


def test_load_rows_reject_string_null_in_any_field(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_csv(
        periods_path,
        [
            "period_id",
            "event_date",
            "window_start",
            "window_end",
            "short_name",
            "event_type",
            "symbol",
            "note",
            "overlap_group",
        ],
        [["p_alpha", "2024-01-10", "2024-01-09", "2024-01-11", "A", "etf", "BTCUSD", "null", "g1"]],
    )

    with pytest.raises(ValueError, match='must not use the string "null"'):
        load_period_rows(periods_path)


def test_load_grid_rows_rejects_blank_required_numeric_field(tmp_path: Path) -> None:
    grids_path = tmp_path / "grids.csv"
    _write_csv(
        grids_path,
        [
            "grid_id",
            "grid_family",
            "consumption_series_name",
            "entry_count_threshold",
            "exit_after_inactive_periods",
            "take_profit",
            "stop_loss",
            "max_hold_minutes",
            "price_spike_limit",
            "volume_multiplier",
            "enabled",
            "note",
        ],
        [["g_bad", "signal_only", "weighted_matching_signal_count", "", "2", "", "", "", "", "", "true", "x"]],
    )

    with pytest.raises(ValueError, match="entry_count_threshold must be provided"):
        load_grid_rows(grids_path)


def test_select_eligible_signal_only_grids_filters_disabled_and_other_family_rows(tmp_path: Path) -> None:
    grids_path = tmp_path / "grids.csv"
    _write_valid_grids_csv(grids_path)

    eligible_rows = select_eligible_signal_only_grids(load_grid_rows(grids_path))

    assert [row["grid_id"] for row in eligible_rows] == ["g_enabled"]


def test_load_period_rows_accepts_single_day_window(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_csv(
        periods_path,
        [
            "period_id",
            "event_date",
            "window_start",
            "window_end",
            "short_name",
            "event_type",
            "symbol",
            "note",
            "overlap_group",
        ],
        [["p_one_day", "2024-01-10", "2024-01-10", "2024-01-10", "A", "etf", "BTCUSD", "x", "g1"]],
    )

    rows = load_period_rows(periods_path)

    assert rows[0]["window_start"] == "2024-01-10"
    assert rows[0]["event_date"] == "2024-01-10"
    assert rows[0]["window_end"] == "2024-01-10"


def test_research_manifest_cli_prints_run_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    exit_code = research_manifest_main(
        [
            "--periods-csv",
            str(periods_path),
            "--grids-csv",
            str(grids_path),
            "--run-root-dir",
            str(run_root_dir),
            "--run-id",
            "20260324T010203Z_deadbeef",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    rendered = json.loads(captured.out)
    assert rendered["run_id"] == "20260324T010203Z_deadbeef"
    assert rendered["manifest_case_count"] == 2
    assert rendered["run_dir"] == str(run_root_dir / "20260324T010203Z_deadbeef")


def test_format_research_manifest_run_returns_json() -> None:
    rendered = format_research_manifest_run({"run_id": "run_x", "manifest_case_count": 3})

    assert '"run_id": "run_x"' in rendered
    assert '"manifest_case_count": 3' in rendered
