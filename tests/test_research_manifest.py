from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from trade_simulator.research_manifest import (
    ALLOWED_RESULT_STATUSES,
    CACHE_KEY_VERSION,
    CACHE_METADATA_SCHEMA_VERSION,
    DEFAULT_SHARED_CACHE_METADATA_PATH,
    DEFAULT_SHARED_STATE_DB_PATH,
    ENGINE_VERSION,
    INPUT_SCHEMA_VERSION,
    RESULT_STATUS_PENDING,
    RESULT_STATUS_RUNNING,
    SHARED_STATE_SCHEMA_VERSION,
    build_case_acquisition_links,
    build_cache_metadata_snapshot_rows,
    build_initial_cache_metadata_rows,
    build_unresolved_acquisition_rows,
    build_acquisition_cache_key,
    build_acquisition_manifest_rows,
    claim_shared_cache_entry,
    complete_shared_cache_entry,
    delete_legacy_shared_cache_metadata_csv,
    fail_shared_cache_entry,
    fetch_acquisition_payload,
    build_manifest_rows,
    find_shared_cache_entry,
    generate_research_manifest_run,
    heartbeat_shared_cache_entry,
    orchestrate_research_acquisition,
    find_cache_metadata_row,
    get_shared_state_schema_version,
    initialize_shared_state_db,
    is_shared_cache_entry_stale,
    load_cache_metadata_rows,
    load_shared_cache_entries,
    load_shared_cache_metadata_rows,
    load_grid_rows,
    load_period_rows,
    save_shared_cache_metadata_rows,
    select_eligible_signal_only_grids,
    upsert_shared_cache_entry,
    update_cache_metadata_status,
    update_shared_cache_entry_status,
    upsert_cache_metadata_row,
    validate_acquisition_status,
    validate_acquisition_status_transition,
    validate_error_code,
    validate_result_status,
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


def _seed_shared_cache_entry(db_path: Path, *, status: str = "pending", retryable: bool = False, auto_retry_count: int = 0) -> dict[str, str]:
    base_kwargs = {
        "cache_key": "cache_a",
        "source_family": "news",
        "symbol": "BTCUSD",
        "period_id": "p_alpha",
        "period_signature": "sig_alpha",
        "status": status,
        "created_at": "2026-03-24T00:00:00Z",
        "updated_at": "2026-03-24T00:00:00Z",
        "auto_retry_count": auto_retry_count,
        "retryable": retryable,
    }
    if status == "running":
        base_kwargs.update(
            {
                "claimed_at": "2026-03-24T00:00:00Z",
                "claimed_by": "worker-a",
                "lease_expires_at": "2026-03-24T00:10:00Z",
                "last_heartbeat_at": "2026-03-24T00:00:00Z",
            }
        )
    if status == "failed":
        base_kwargs["last_error_code"] = "runtime_error"
    return upsert_shared_cache_entry(db_path, **base_kwargs)


def test_generate_research_manifest_run_creates_manifest_and_fixed_input_copies(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news", "sns"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    assert result.run_dir == run_root_dir / "20260324T010203Z_deadbeef"
    assert result.periods_copy_path.read_text(encoding="utf-8") == periods_path.read_text(encoding="utf-8")
    assert result.grids_copy_path.read_text(encoding="utf-8") == grids_path.read_text(encoding="utf-8")

    manifest_rows = list(csv.DictReader(result.manifest_path.open("r", encoding="utf-8", newline="")))
    results_rows = list(csv.DictReader(result.results_index_path.open("r", encoding="utf-8", newline="")))
    acquisition_rows = list(csv.DictReader(result.acquisition_manifest_path.open("r", encoding="utf-8", newline="")))
    link_rows = list(csv.DictReader(result.case_acquisition_links_path.open("r", encoding="utf-8", newline="")))
    cache_metadata_rows = list(csv.DictReader(result.cache_metadata_path.open("r", encoding="utf-8", newline="")))
    unresolved_rows = list(csv.DictReader(result.unresolved_acquisitions_path.open("r", encoding="utf-8", newline="")))
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

    assert len(manifest_rows) == 2
    assert {row["case_id"] for row in manifest_rows} == {
        "p_alpha__g_enabled",
        "p_minimal__g_enabled",
    }
    assert {row["grid_family"] for row in manifest_rows} == {"signal_only"}
    assert {row["consumption_series_name"] for row in manifest_rows} == {"weighted_matching_signal_count"}

    assert len(results_rows) == 2
    assert {row["status"] for row in results_rows} == {RESULT_STATUS_PENDING}
    assert len(acquisition_rows) == 4
    assert {row["status"] for row in acquisition_rows} == {RESULT_STATUS_PENDING}
    assert {row["source_family"] for row in acquisition_rows} == {"news", "sns"}
    assert len(link_rows) == 4
    assert len(cache_metadata_rows) == 0
    assert len(unresolved_rows) == 4

    assert metadata == {
        "run_id": "20260324T010203Z_deadbeef",
        "created_at": metadata["created_at"],
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "source_families": ["news", "sns"],
        "shared_state_db_path": str(shared_state_db_path),
        "shared_state_role": "runtime_truth",
        "cache_metadata_snapshot_role": "run_start_audit_repro_snapshot",
        "unresolved_acquisitions_role": "run_start_decision_record_recheck_shared_truth_before_execution",
        "periods_file_name": "periods.csv",
        "grids_file_name": "grids.csv",
        "period_row_count": 2,
        "grid_row_count": 3,
        "eligible_grid_row_count": 1,
        "manifest_case_count": 2,
        "acquisition_manifest_count": 4,
        "cache_metadata_row_count": 0,
        "case_acquisition_link_count": 4,
        "unresolved_acquisition_count": 4,
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
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    exit_code = research_manifest_main(
        [
            "--periods-csv",
            str(periods_path),
            "--grids-csv",
            str(grids_path),
            "--source-family",
            "news",
            "--source-family",
            "sns",
            "--run-root-dir",
            str(run_root_dir),
            "--shared-state-db-path",
            str(shared_state_db_path),
            "--run-id",
            "20260324T010203Z_deadbeef",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    rendered = json.loads(captured.out)
    assert rendered["run_id"] == "20260324T010203Z_deadbeef"
    assert rendered["manifest_case_count"] == 2
    assert rendered["acquisition_manifest_count"] == 4
    assert rendered["unresolved_acquisition_count"] == 4
    assert rendered["shared_state_db_path"] == str(shared_state_db_path)
    assert rendered["shared_state_role"] == "runtime_truth"
    assert rendered["run_dir"] == str(run_root_dir / "20260324T010203Z_deadbeef")


def test_format_research_manifest_run_returns_json() -> None:
    rendered = format_research_manifest_run({"run_id": "run_x", "manifest_case_count": 3})

    assert '"run_id": "run_x"' in rendered
    assert '"manifest_case_count": 3' in rendered


def test_acquisition_manifest_is_generated_with_stable_units(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    period_rows = load_period_rows(periods_path)
    acquisition_rows = build_acquisition_manifest_rows(
        period_rows,
        run_id="run_fixed",
        source_families=["news"],
        created_at="2026-03-24T00:00:00Z",
    )

    assert [row["acquisition_id"] for row in acquisition_rows] == [
        "news__BTCUSD__p_alpha",
        "news__ETHUSD__p_minimal",
    ]
    assert all(row["status"] == RESULT_STATUS_PENDING for row in acquisition_rows)


def test_engine_version_constant_is_stable() -> None:
    assert ENGINE_VERSION == "research_manifest_dry_run_v1"


def test_validate_result_status_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        validate_result_status("queued")


def test_validate_acquisition_status_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        validate_acquisition_status("queued")


def test_validate_acquisition_status_transition_accepts_allowed_paths() -> None:
    assert validate_acquisition_status_transition("pending", "running") == "running"
    assert validate_acquisition_status_transition("running", "completed") == "completed"
    assert validate_acquisition_status_transition("running", "failed") == "failed"


def test_validate_acquisition_status_transition_rejects_disallowed_paths() -> None:
    with pytest.raises(ValueError, match="invalid acquisition status transition: completed -> running"):
        validate_acquisition_status_transition("completed", "running")
    with pytest.raises(ValueError, match="invalid acquisition status transition: failed -> running"):
        validate_acquisition_status_transition("failed", "running")
    with pytest.raises(ValueError, match="invalid acquisition status transition: pending -> completed"):
        validate_acquisition_status_transition("pending", "completed")


def test_validate_error_code_requires_value_for_failed_status() -> None:
    with pytest.raises(ValueError, match="error_code is required when status is failed"):
        validate_error_code(status="failed", error_code="", error_message="boom")


def test_validate_error_code_rejects_non_empty_value_for_pending_status() -> None:
    with pytest.raises(ValueError, match="error_code and error_message must be empty unless status is failed"):
        validate_error_code(status="pending", error_code="runtime_error", error_message="boom")


def test_build_acquisition_manifest_rows_rejects_invalid_source_family(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    with pytest.raises(ValueError, match="source_family must be one of"):
        build_acquisition_manifest_rows(
            load_period_rows(periods_path),
            run_id="run_fixed",
            source_families=["podcast"],
            created_at="2026-03-24T00:00:00Z",
        )


def test_build_acquisition_cache_key_requires_all_inputs() -> None:
    with pytest.raises(ValueError, match="period_signature is required to build cache_key"):
        build_acquisition_cache_key(
            source_family="news",
            symbol="BTCUSD",
            period_signature="",
            input_schema_version=INPUT_SCHEMA_VERSION,
        )


def test_build_initial_cache_metadata_rows_starts_empty() -> None:
    assert build_initial_cache_metadata_rows() == []


def test_shared_cache_metadata_load_validate_upsert_and_search(tmp_path: Path) -> None:
    shared_cache_metadata_path = tmp_path / "shared" / "cache_metadata.csv"
    rows = load_shared_cache_metadata_rows(shared_cache_metadata_path)
    assert rows == []

    rows = upsert_cache_metadata_row(
        rows,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )
    save_shared_cache_metadata_rows(rows, shared_cache_metadata_path)
    loaded_rows = load_shared_cache_metadata_rows(shared_cache_metadata_path)

    assert find_cache_metadata_row(loaded_rows, cache_key="cache_a") == {
        "cache_key": "cache_a",
        "cache_key_version": CACHE_KEY_VERSION,
        "source_family": "news",
        "symbol": "BTCUSD",
        "period_id": "p_alpha",
        "period_signature": "sig_alpha",
        "status": "pending",
        "created_at": "2026-03-24T00:00:00Z",
        "updated_at": "2026-03-24T00:00:00Z",
        "schema_version": CACHE_METADATA_SCHEMA_VERSION,
    }


def test_initialize_shared_state_db_creates_sqlite_and_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    initialized_path = initialize_shared_state_db(db_path)

    assert initialized_path == db_path
    assert db_path.exists()
    assert get_shared_state_schema_version(db_path) == SHARED_STATE_SCHEMA_VERSION


def test_initialize_shared_state_db_migrates_v1_schema_to_v2(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE shared_state_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO shared_state_meta(key, value) VALUES ('schema_version', 'shared_state_v1')")
        connection.execute(
            """
            CREATE TABLE shared_cache_entries (
                cache_key TEXT PRIMARY KEY,
                cache_key_version TEXT NOT NULL,
                source_family TEXT NOT NULL,
                symbol TEXT NOT NULL,
                period_id TEXT NOT NULL,
                period_signature TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO shared_cache_entries (
                cache_key, cache_key_version, source_family, symbol, period_id, period_signature, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("cache_a", CACHE_KEY_VERSION, "news", "BTCUSD", "p_alpha", "sig_alpha", "pending", "t1", "t1"),
        )
        connection.commit()

    initialize_shared_state_db(db_path)
    loaded_row = find_shared_cache_entry(db_path, cache_key="cache_a")

    assert get_shared_state_schema_version(db_path) == SHARED_STATE_SCHEMA_VERSION
    assert loaded_row is not None
    assert loaded_row["claimed_by"] == ""
    assert loaded_row["auto_retry_count"] == "0"
    assert loaded_row["retryable"] == "0"


def test_shared_state_default_path_is_fixed() -> None:
    assert DEFAULT_SHARED_STATE_DB_PATH == Path("var/cache/external_signals/shared_state.sqlite3")


def test_load_shared_cache_entries_returns_empty_list_for_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    initialize_shared_state_db(db_path)

    assert load_shared_cache_entries(db_path) == []


def test_build_cache_metadata_snapshot_rows_renders_csv_schema_from_sqlite_rows() -> None:
    snapshot_rows = build_cache_metadata_snapshot_rows(
        [
            {
                "cache_key": "cache_a",
                "cache_key_version": CACHE_KEY_VERSION,
                "source_family": "news",
                "symbol": "BTCUSD",
                "period_id": "p_alpha",
                "period_signature": "sig_alpha",
                "status": "completed",
                "created_at": "2026-03-24T00:00:00Z",
                "updated_at": "2026-03-24T00:01:00Z",
            }
        ]
    )

    assert snapshot_rows == [
        {
            "cache_key": "cache_a",
            "cache_key_version": CACHE_KEY_VERSION,
            "source_family": "news",
            "symbol": "BTCUSD",
            "period_id": "p_alpha",
            "period_signature": "sig_alpha",
            "status": "completed",
            "created_at": "2026-03-24T00:00:00Z",
            "updated_at": "2026-03-24T00:01:00Z",
            "schema_version": CACHE_METADATA_SCHEMA_VERSION,
        }
    ]


def test_shared_cache_entry_upsert_find_and_list_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    upserted_row = upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    assert upserted_row == {
        "cache_key": "cache_a",
        "cache_key_version": CACHE_KEY_VERSION,
        "source_family": "news",
        "symbol": "BTCUSD",
        "period_id": "p_alpha",
        "period_signature": "sig_alpha",
        "status": "pending",
        "created_at": "2026-03-24T00:00:00Z",
        "updated_at": "2026-03-24T00:00:00Z",
        "claimed_at": "",
        "claimed_by": "",
        "lease_expires_at": "",
        "last_heartbeat_at": "",
        "auto_retry_count": "0",
        "retryable": "0",
        "last_error_code": "",
    }
    assert find_shared_cache_entry(db_path, cache_key="cache_a") == upserted_row
    assert load_shared_cache_entries(db_path) == [upserted_row]


def test_upsert_shared_cache_entry_updates_existing_row_for_same_cache_key(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )
    updated_row = upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="running",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:01:00Z",
        claimed_at="2026-03-24T00:01:00Z",
        claimed_by="worker-a",
        lease_expires_at="2026-03-24T00:06:00Z",
        last_heartbeat_at="2026-03-24T00:01:00Z",
    )

    assert updated_row["status"] == "running"
    assert updated_row["created_at"] == "2026-03-24T00:00:00Z"
    assert updated_row["updated_at"] == "2026-03-24T00:01:00Z"


def test_update_shared_cache_entry_status_applies_valid_non_running_transition(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="running",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:01:00Z",
        claimed_at="2026-03-24T00:01:00Z",
        claimed_by="worker-a",
        lease_expires_at="2026-03-24T00:06:00Z",
        last_heartbeat_at="2026-03-24T00:01:00Z",
    )
    updated_row = update_shared_cache_entry_status(
        db_path,
        cache_key="cache_a",
        next_status="completed",
        updated_at="2026-03-24T00:02:00Z",
    )

    assert updated_row["status"] == "completed"
    assert updated_row["claimed_by"] == ""


def test_update_shared_cache_entry_status_rejects_running_without_lease_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="pending")

    with pytest.raises(ValueError, match="cannot set running without lease fields"):
        update_shared_cache_entry_status(
            db_path,
            cache_key="cache_a",
            next_status="running",
            updated_at="2026-03-24T00:01:00Z",
        )


def test_get_shared_state_schema_version_rejects_invalid_meta_value(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    initialize_shared_state_db(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE shared_state_meta SET value = ? WHERE key = 'schema_version'",
            ("shared_state_v999",),
        )
        connection.commit()

    with pytest.raises(ValueError, match="shared state schema_version must be"):
        get_shared_state_schema_version(db_path)


def test_upsert_shared_cache_entry_rejects_invalid_source_family(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    with pytest.raises(ValueError, match="source_family must be one of"):
        upsert_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            source_family="podcast",
            symbol="BTCUSD",
            period_id="p_alpha",
            period_signature="sig_alpha",
            status="pending",
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )


def test_upsert_shared_cache_entry_rejects_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"

    with pytest.raises(ValueError, match="status must be one of"):
        upsert_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            source_family="news",
            symbol="BTCUSD",
            period_id="p_alpha",
            period_signature="sig_alpha",
            status="queued",
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )


def test_upsert_shared_cache_entry_rejects_inconsistent_duplicate_cache_key(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    upsert_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    with pytest.raises(ValueError, match="shared_cache_entries row mismatch for cache_key cache_a: source_family"):
        upsert_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            source_family="sns",
            symbol="BTCUSD",
            period_id="p_alpha",
            period_signature="sig_alpha",
            status="pending",
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:01:00Z",
        )


def test_delete_legacy_shared_cache_metadata_csv_removes_file_when_present(tmp_path: Path) -> None:
    legacy_csv_path = tmp_path / "shared" / "cache_metadata.csv"
    legacy_csv_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_csv_path.write_text("cache_key\nlegacy\n", encoding="utf-8")

    deleted = delete_legacy_shared_cache_metadata_csv(legacy_csv_path)

    assert deleted is True
    assert not legacy_csv_path.exists()


def test_delete_legacy_shared_cache_metadata_csv_is_safe_when_absent(tmp_path: Path) -> None:
    legacy_csv_path = tmp_path / "shared" / "cache_metadata.csv"

    deleted = delete_legacy_shared_cache_metadata_csv(legacy_csv_path)

    assert deleted is False


def test_claim_shared_cache_entry_claims_pending_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="pending")

    claimed_row = claim_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-a",
        claimed_at="2026-03-24T00:01:00Z",
        lease_duration_seconds=300,
    )

    assert claimed_row["status"] == "running"
    assert claimed_row["claimed_by"] == "worker-a"
    assert claimed_row["last_heartbeat_at"] == "2026-03-24T00:01:00Z"
    assert claimed_row["lease_expires_at"] == "2026-03-24T00:06:00Z"


def test_heartbeat_shared_cache_entry_extends_active_lease(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    heartbeat_row = heartbeat_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-a",
        heartbeat_at="2026-03-24T00:04:00Z",
        lease_duration_seconds=300,
    )

    assert heartbeat_row["last_heartbeat_at"] == "2026-03-24T00:04:00Z"
    assert heartbeat_row["lease_expires_at"] == "2026-03-24T00:09:00Z"


def test_complete_shared_cache_entry_completes_running_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    completed_row = complete_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-a",
        completed_at="2026-03-24T00:05:00Z",
    )

    assert completed_row["status"] == "completed"
    assert completed_row["claimed_at"] == ""


def test_fail_shared_cache_entry_marks_retryable_failed_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    failed_row = fail_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-a",
        failed_at="2026-03-24T00:05:00Z",
        retryable=True,
        last_error_code="runtime_error",
    )

    assert failed_row["status"] == "failed"
    assert failed_row["retryable"] == "1"
    assert failed_row["auto_retry_count"] == "0"
    assert failed_row["last_error_code"] == "runtime_error"


def test_claim_shared_cache_entry_reclaims_stale_running_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    reclaimed_row = claim_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-b",
        claimed_at="2026-03-24T00:10:01Z",
        lease_duration_seconds=300,
    )

    assert reclaimed_row["claimed_by"] == "worker-b"
    assert reclaimed_row["claimed_at"] == "2026-03-24T00:10:01Z"


def test_claim_shared_cache_entry_auto_retries_retryable_failed_entry_once(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="failed", retryable=True, auto_retry_count=0)

    claimed_row = claim_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-b",
        claimed_at="2026-03-24T00:06:00Z",
        lease_duration_seconds=300,
    )

    assert claimed_row["status"] == "running"
    assert claimed_row["auto_retry_count"] == "1"
    assert claimed_row["retryable"] == "0"


def test_claim_shared_cache_entry_rejects_completed_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="completed")

    with pytest.raises(ValueError, match="cache_key is not claimable"):
        claim_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-a",
            claimed_at="2026-03-24T00:01:00Z",
            lease_duration_seconds=300,
        )


def test_claim_shared_cache_entry_rejects_non_stale_running_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    with pytest.raises(ValueError, match="cache_key is not claimable"):
        claim_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-b",
            claimed_at="2026-03-24T00:05:00Z",
            lease_duration_seconds=300,
        )


def test_claim_shared_cache_entry_rejects_non_retryable_failed_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="failed", retryable=False, auto_retry_count=0)

    with pytest.raises(ValueError, match="cache_key is not claimable"):
        claim_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-b",
            claimed_at="2026-03-24T00:06:00Z",
            lease_duration_seconds=300,
        )


def test_claim_shared_cache_entry_rejects_failed_entry_after_auto_retry_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="failed", retryable=True, auto_retry_count=1)

    with pytest.raises(ValueError, match="cache_key is not claimable"):
        claim_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-b",
            claimed_at="2026-03-24T00:06:00Z",
            lease_duration_seconds=300,
        )


def test_heartbeat_shared_cache_entry_rejects_mismatched_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    with pytest.raises(ValueError, match="matching claimed_by"):
        heartbeat_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-b",
            heartbeat_at="2026-03-24T00:02:00Z",
            lease_duration_seconds=300,
        )


def test_is_shared_cache_entry_stale_uses_strict_lease_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    running_row = _seed_shared_cache_entry(db_path, status="running")

    assert is_shared_cache_entry_stale(running_row, now="2026-03-24T00:10:00Z") is False
    assert is_shared_cache_entry_stale(running_row, now="2026-03-24T00:10:01Z") is True


def test_heartbeat_shared_cache_entry_is_not_stale_immediately_after_heartbeat(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _seed_shared_cache_entry(db_path, status="running")

    heartbeat_row = heartbeat_shared_cache_entry(
        db_path,
        cache_key="cache_a",
        claimed_by="worker-a",
        heartbeat_at="2026-03-24T00:03:00Z",
        lease_duration_seconds=300,
    )

    assert is_shared_cache_entry_stale(heartbeat_row, now="2026-03-24T00:03:00Z") is False


def test_claim_shared_cache_entry_rejects_running_entry_with_broken_lease_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "shared_state.sqlite3"
    initialize_shared_state_db(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO shared_cache_entries (
                cache_key, cache_key_version, source_family, symbol, period_id, period_signature, status, created_at, updated_at,
                claimed_at, claimed_by, lease_expires_at, last_heartbeat_at, auto_retry_count, retryable, last_error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cache_a",
                CACHE_KEY_VERSION,
                "news",
                "BTCUSD",
                "p_alpha",
                "sig_alpha",
                "running",
                "2026-03-24T00:00:00Z",
                "2026-03-24T00:00:00Z",
                "",
                "worker-a",
                "",
                "2026-03-24T00:00:00Z",
                0,
                0,
                "",
            ),
        )
        connection.commit()

    with pytest.raises(ValueError, match="running shared_cache_entry must include claimed_at"):
        claim_shared_cache_entry(
            db_path,
            cache_key="cache_a",
            claimed_by="worker-b",
            claimed_at="2026-03-24T00:10:01Z",
            lease_duration_seconds=300,
        )


def test_fetch_acquisition_payload_rejects_unsupported_source_family() -> None:
    with pytest.raises(ValueError, match="unsupported source_family for fetch"):
        fetch_acquisition_payload(
            {
                "acquisition_id": "bad_aq",
                "cache_key": "bad_cache",
                "source_family": "podcast",
            }
        )


def test_update_cache_metadata_status_applies_valid_transitions(tmp_path: Path) -> None:
    rows = upsert_cache_metadata_row(
        [],
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )
    rows = update_cache_metadata_status(
        rows,
        cache_key="cache_a",
        next_status="running",
        updated_at="2026-03-24T00:01:00Z",
    )
    rows = update_cache_metadata_status(
        rows,
        cache_key="cache_a",
        next_status="completed",
        updated_at="2026-03-24T00:02:00Z",
    )

    assert find_cache_metadata_row(rows, cache_key="cache_a")["status"] == "completed"


def test_update_cache_metadata_status_rejects_invalid_transition() -> None:
    rows = upsert_cache_metadata_row(
        [],
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="completed",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    with pytest.raises(ValueError, match="invalid acquisition status transition: completed -> running"):
        update_cache_metadata_status(
            rows,
            cache_key="cache_a",
            next_status="running",
            updated_at="2026-03-24T00:01:00Z",
        )


def test_upsert_cache_metadata_row_rejects_inconsistent_duplicate_cache_key() -> None:
    rows = upsert_cache_metadata_row(
        [],
        cache_key="cache_a",
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature="sig_alpha",
        status="pending",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    with pytest.raises(ValueError, match="cache_metadata row mismatch for cache_key cache_a: source_family"):
        upsert_cache_metadata_row(
            rows,
            cache_key="cache_a",
            source_family="sns",
            symbol="BTCUSD",
            period_id="p_alpha",
            period_signature="sig_alpha",
            status="pending",
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )


def test_case_to_acquisition_links_are_mechanically_derivable(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    period_rows = load_period_rows(periods_path)
    grid_rows = select_eligible_signal_only_grids(load_grid_rows(grids_path))
    manifest_rows = build_manifest_rows(period_rows, grid_rows, run_id="run_fixed")
    acquisition_rows = build_acquisition_manifest_rows(
        period_rows,
        run_id="run_fixed",
        source_families=["news", "sns"],
        created_at="2026-03-24T00:00:00Z",
    )

    link_rows = build_case_acquisition_links(manifest_rows, acquisition_rows)

    assert len(link_rows) == 4
    assert {row["case_id"] for row in link_rows} == {"p_alpha__g_enabled", "p_minimal__g_enabled"}
    assert {row["acquisition_id"] for row in link_rows if row["case_id"] == "p_alpha__g_enabled"} == {
        "news__BTCUSD__p_alpha",
        "sns__BTCUSD__p_alpha",
    }


def test_unresolved_acquisition_rows_are_generated_from_empty_cache_metadata(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    acquisition_rows = build_acquisition_manifest_rows(
        load_period_rows(periods_path),
        run_id="run_fixed",
        source_families=["news"],
        created_at="2026-03-24T00:00:00Z",
    )

    unresolved_rows = build_unresolved_acquisition_rows(acquisition_rows, [])

    assert unresolved_rows == acquisition_rows


def test_load_cache_metadata_rows_rejects_missing_required_column(tmp_path: Path) -> None:
    metadata_path = tmp_path / "cache_metadata.csv"
    _write_csv(metadata_path, ["cache_key"], [["abc"]])

    with pytest.raises(ValueError, match="cache_metadata csv missing required columns"):
        load_cache_metadata_rows(metadata_path)


def test_load_cache_metadata_rows_rejects_invalid_schema_versions(tmp_path: Path) -> None:
    metadata_path = tmp_path / "cache_metadata.csv"
    _write_csv(
        metadata_path,
        [
            "cache_key",
            "cache_key_version",
            "source_family",
            "symbol",
            "period_id",
            "period_signature",
            "status",
            "created_at",
            "updated_at",
            "schema_version",
        ],
        [["abc", "bad_version", "news", "BTCUSD", "p1", "sig1", "pending", "t1", "t1", "bad_schema"]],
    )

    with pytest.raises(ValueError, match="schema_version must be"):
        load_cache_metadata_rows(metadata_path)


def test_load_cache_metadata_rows_rejects_invalid_cache_key_version(tmp_path: Path) -> None:
    metadata_path = tmp_path / "cache_metadata.csv"
    _write_csv(
        metadata_path,
        [
            "cache_key",
            "cache_key_version",
            "source_family",
            "symbol",
            "period_id",
            "period_signature",
            "status",
            "created_at",
            "updated_at",
            "schema_version",
        ],
        [["abc", "bad_version", "news", "BTCUSD", "p1", "sig1", "pending", "t1", "t1", CACHE_METADATA_SCHEMA_VERSION]],
    )

    with pytest.raises(ValueError, match="cache_key_version must be"):
        load_cache_metadata_rows(metadata_path)


def test_load_cache_metadata_rows_rejects_duplicate_cache_key(tmp_path: Path) -> None:
    metadata_path = tmp_path / "cache_metadata.csv"
    _write_csv(
        metadata_path,
        [
            "cache_key",
            "cache_key_version",
            "source_family",
            "symbol",
            "period_id",
            "period_signature",
            "status",
            "created_at",
            "updated_at",
            "schema_version",
        ],
        [
            ["dup_key", CACHE_KEY_VERSION, "news", "BTCUSD", "p1", "sig1", "pending", "t1", "t1", CACHE_METADATA_SCHEMA_VERSION],
            ["dup_key", CACHE_KEY_VERSION, "news", "BTCUSD", "p1", "sig1", "pending", "t2", "t2", CACHE_METADATA_SCHEMA_VERSION],
        ],
    )

    with pytest.raises(ValueError, match="cache_key must be unique in cache_metadata: dup_key"):
        load_cache_metadata_rows(metadata_path)


def test_same_period_id_with_different_period_signature_can_be_distinguished_by_cache_key() -> None:
    cache_key_one = build_acquisition_cache_key(
        source_family="news",
        symbol="BTCUSD",
        period_signature="sig_one",
        input_schema_version=INPUT_SCHEMA_VERSION,
    )
    cache_key_two = build_acquisition_cache_key(
        source_family="news",
        symbol="BTCUSD",
        period_signature="sig_two",
        input_schema_version=INPUT_SCHEMA_VERSION,
    )

    assert cache_key_one != cache_key_two


def test_same_acquisition_id_can_be_distinguished_when_cache_key_differs() -> None:
    cache_key_one = build_acquisition_cache_key(
        source_family="news",
        symbol="BTCUSD",
        period_signature="sig_one",
        input_schema_version=INPUT_SCHEMA_VERSION,
    )
    cache_key_two = build_acquisition_cache_key(
        source_family="news",
        symbol="BTCUSD",
        period_signature="sig_two",
        input_schema_version=INPUT_SCHEMA_VERSION,
    )

    assert cache_key_one != cache_key_two


def test_cache_metadata_loader_accepts_fixed_versions(tmp_path: Path) -> None:
    metadata_path = tmp_path / "cache_metadata.csv"
    _write_csv(
        metadata_path,
        [
            "cache_key",
            "cache_key_version",
            "source_family",
            "symbol",
            "period_id",
            "period_signature",
            "status",
            "created_at",
            "updated_at",
            "schema_version",
        ],
        [["abc", CACHE_KEY_VERSION, "news", "BTCUSD", "p1", "sig1", "completed", "t1", "t1", CACHE_METADATA_SCHEMA_VERSION]],
    )

    rows = load_cache_metadata_rows(metadata_path)

    assert rows == [
        {
            "cache_key": "abc",
            "cache_key_version": CACHE_KEY_VERSION,
            "source_family": "news",
            "symbol": "BTCUSD",
            "period_id": "p1",
            "period_signature": "sig1",
            "status": "completed",
            "created_at": "t1",
            "updated_at": "t1",
            "schema_version": CACHE_METADATA_SCHEMA_VERSION,
        }
    ]


def test_unresolved_acquisition_rows_exclude_completed_cache_entries(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    acquisition_rows = build_acquisition_manifest_rows(
        load_period_rows(periods_path),
        run_id="run_fixed",
        source_families=["news"],
        created_at="2026-03-24T00:00:00Z",
    )
    cache_metadata_rows = [
        {
            "cache_key": acquisition_rows[0]["cache_key"],
            "cache_key_version": CACHE_KEY_VERSION,
            "source_family": "news",
            "symbol": "BTCUSD",
            "period_id": "p_alpha",
            "period_signature": acquisition_rows[0]["period_signature"],
            "status": "completed",
            "created_at": "t1",
            "updated_at": "t1",
            "schema_version": CACHE_METADATA_SCHEMA_VERSION,
        }
    ]

    unresolved_rows = build_unresolved_acquisition_rows(acquisition_rows, cache_metadata_rows)

    assert [row["acquisition_id"] for row in unresolved_rows] == ["news__ETHUSD__p_minimal"]


def test_unresolved_acquisition_rows_exclude_running_cache_entries(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    acquisition_rows = build_acquisition_manifest_rows(
        load_period_rows(periods_path),
        run_id="run_fixed",
        source_families=["news"],
        created_at="2026-03-24T00:00:00Z",
    )
    cache_metadata_rows = [
        {
            "cache_key": acquisition_rows[0]["cache_key"],
            "cache_key_version": CACHE_KEY_VERSION,
            "source_family": "news",
            "symbol": "BTCUSD",
            "period_id": "p_alpha",
            "period_signature": acquisition_rows[0]["period_signature"],
            "status": RESULT_STATUS_RUNNING,
            "created_at": "t1",
            "updated_at": "t1",
            "schema_version": CACHE_METADATA_SCHEMA_VERSION,
        }
    ]

    unresolved_rows = build_unresolved_acquisition_rows(acquisition_rows, cache_metadata_rows)

    assert [row["acquisition_id"] for row in unresolved_rows] == ["news__ETHUSD__p_minimal"]


def test_generate_research_manifest_run_uses_shared_metadata_for_unresolved_and_keeps_snapshot(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    upsert_shared_cache_entry(
        shared_state_db_path,
        cache_key=build_acquisition_cache_key(
            source_family="news",
            symbol="BTCUSD",
            period_signature=load_period_rows(periods_path)[0]["period_signature"],
            input_schema_version=INPUT_SCHEMA_VERSION,
        ),
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature=load_period_rows(periods_path)[0]["period_signature"],
        status="completed",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    snapshot_rows = list(csv.DictReader(result.cache_metadata_path.open("r", encoding="utf-8", newline="")))
    unresolved_rows = list(csv.DictReader(result.unresolved_acquisitions_path.open("r", encoding="utf-8", newline="")))

    assert len(snapshot_rows) == 1
    assert snapshot_rows[0]["status"] == "completed"
    assert [row["acquisition_id"] for row in unresolved_rows] == ["news__ETHUSD__p_minimal"]


def test_orchestrate_research_acquisition_completes_using_shared_truth(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    result = orchestrate_research_acquisition(
        run.run_dir,
        acquisition_id="news__BTCUSD__p_alpha",
        claimed_by="worker-a",
        lease_duration_seconds=300,
    )
    shared_truth = find_shared_cache_entry(shared_state_db_path, cache_key=result["cache_key"])

    assert result["decision_source"] == "shared_truth"
    assert result["outcome"] == "completed"
    assert shared_truth is not None
    assert shared_truth["status"] == "completed"


def test_orchestrate_research_acquisition_marks_failed_when_fetch_raises(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    def failing_fetcher(_: dict[str, str]) -> dict[str, object]:
        raise RuntimeError("boom")

    result = orchestrate_research_acquisition(
        run.run_dir,
        acquisition_id="news__BTCUSD__p_alpha",
        claimed_by="worker-a",
        lease_duration_seconds=300,
        fetcher=failing_fetcher,
    )
    shared_truth = find_shared_cache_entry(shared_state_db_path, cache_key=str(result["cache_key"]))

    assert result["outcome"] == "failed"
    assert shared_truth is not None
    assert shared_truth["status"] == "failed"


def test_orchestrate_research_acquisition_rechecks_shared_truth_after_run_snapshot(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    btc_period = load_period_rows(periods_path)[0]
    completed_row = upsert_shared_cache_entry(
        shared_state_db_path,
        cache_key=build_acquisition_cache_key(
            source_family="news",
            symbol="BTCUSD",
            period_signature=str(btc_period["period_signature"]),
            input_schema_version=INPUT_SCHEMA_VERSION,
        ),
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature=str(btc_period["period_signature"]),
        status="completed",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
    )

    snapshot_rows = list(csv.DictReader(run.cache_metadata_path.open("r", encoding="utf-8", newline="")))
    unresolved_rows = list(csv.DictReader(run.unresolved_acquisitions_path.open("r", encoding="utf-8", newline="")))
    result = orchestrate_research_acquisition(
        run.run_dir,
        acquisition_id="news__BTCUSD__p_alpha",
        claimed_by="worker-a",
        lease_duration_seconds=300,
    )

    assert snapshot_rows == []
    assert any(row["acquisition_id"] == "news__BTCUSD__p_alpha" for row in unresolved_rows)
    assert completed_row["status"] == "completed"
    assert result["outcome"] == "skipped"
    assert result["shared_truth_status_after"] == "completed"


def test_orchestrate_research_acquisition_does_not_reclaim_active_running_from_snapshot(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    btc_period = load_period_rows(periods_path)[0]
    upsert_shared_cache_entry(
        shared_state_db_path,
        cache_key=build_acquisition_cache_key(
            source_family="news",
            symbol="BTCUSD",
            period_signature=str(btc_period["period_signature"]),
            input_schema_version=INPUT_SCHEMA_VERSION,
        ),
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature=str(btc_period["period_signature"]),
        status="running",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:00:00Z",
        claimed_at="2026-03-24T00:00:00Z",
        claimed_by="worker-b",
        lease_expires_at="2099-01-01T00:00:00Z",
        last_heartbeat_at="2026-03-24T00:00:00Z",
    )

    result = orchestrate_research_acquisition(
        run.run_dir,
        acquisition_id="news__BTCUSD__p_alpha",
        claimed_by="worker-a",
        lease_duration_seconds=300,
    )

    assert result["outcome"] == "skipped"
    assert result["shared_truth_status_after"] == "running"


def test_orchestrate_research_acquisition_rejects_snapshot_decision_source(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    with pytest.raises(ValueError, match="decision_source must be shared_truth"):
        orchestrate_research_acquisition(
            run.run_dir,
            acquisition_id="news__BTCUSD__p_alpha",
            claimed_by="worker-a",
            lease_duration_seconds=300,
            decision_source="snapshot",
        )


def test_orchestrate_research_acquisition_rejects_shared_truth_access_failure(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    run = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )
    metadata_path = run.run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    broken_path = tmp_path / "broken_db_dir"
    broken_path.mkdir(parents=True, exist_ok=True)
    metadata["shared_state_db_path"] = str(broken_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed to open shared state db"):
        orchestrate_research_acquisition(
            run.run_dir,
            acquisition_id="news__BTCUSD__p_alpha",
            claimed_by="worker-a",
            lease_duration_seconds=300,
        )


def test_generate_research_manifest_run_excludes_running_and_keeps_pending_failed_from_sqlite(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    period_rows = load_period_rows(periods_path)

    upsert_shared_cache_entry(
        shared_state_db_path,
        cache_key=build_acquisition_cache_key(
            source_family="news",
            symbol="BTCUSD",
            period_signature=period_rows[0]["period_signature"],
            input_schema_version=INPUT_SCHEMA_VERSION,
        ),
        source_family="news",
        symbol="BTCUSD",
        period_id="p_alpha",
        period_signature=period_rows[0]["period_signature"],
        status="running",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:01:00Z",
        claimed_at="2026-03-24T00:01:00Z",
        claimed_by="worker-a",
        lease_expires_at="2026-03-24T00:06:00Z",
        last_heartbeat_at="2026-03-24T00:01:00Z",
    )
    upsert_shared_cache_entry(
        shared_state_db_path,
        cache_key=build_acquisition_cache_key(
            source_family="news",
            symbol="ETHUSD",
            period_signature=period_rows[1]["period_signature"],
            input_schema_version=INPUT_SCHEMA_VERSION,
        ),
        source_family="news",
        symbol="ETHUSD",
        period_id="p_minimal",
        period_signature=period_rows[1]["period_signature"],
        status="failed",
        created_at="2026-03-24T00:00:00Z",
        updated_at="2026-03-24T00:02:00Z",
    )

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    snapshot_rows = list(csv.DictReader(result.cache_metadata_path.open("r", encoding="utf-8", newline="")))
    unresolved_rows = list(csv.DictReader(result.unresolved_acquisitions_path.open("r", encoding="utf-8", newline="")))

    assert {row["status"] for row in snapshot_rows} == {"running", "failed"}
    assert [row["acquisition_id"] for row in unresolved_rows] == ["news__ETHUSD__p_minimal"]


def test_generate_research_manifest_run_generates_headers_when_shared_db_is_empty(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    assert result.cache_metadata_path.read_text(encoding="utf-8").splitlines() == [
        ",".join(
            [
                "cache_key",
                "cache_key_version",
                "source_family",
                "symbol",
                "period_id",
                "period_signature",
                "status",
                "created_at",
                "updated_at",
                "schema_version",
            ]
        )
    ]


def test_generate_research_manifest_run_allows_zero_unresolved_rows(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    run_root_dir = tmp_path / "runs"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    period_rows = load_period_rows(periods_path)

    for period_row in period_rows:
        upsert_shared_cache_entry(
            shared_state_db_path,
            cache_key=build_acquisition_cache_key(
                source_family="news",
                symbol=str(period_row["symbol"]),
                period_signature=str(period_row["period_signature"]),
                input_schema_version=INPUT_SCHEMA_VERSION,
            ),
            source_family="news",
            symbol=str(period_row["symbol"]),
            period_id=str(period_row["period_id"]),
            period_signature=str(period_row["period_signature"]),
            status="completed",
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )

    result = generate_research_manifest_run(
        periods_path,
        grids_path,
        source_families=["news"],
        run_root_dir=run_root_dir,
        shared_state_db_path=shared_state_db_path,
        run_id="20260324T010203Z_deadbeef",
    )

    assert list(csv.DictReader(result.unresolved_acquisitions_path.open("r", encoding="utf-8", newline=""))) == []


def test_generate_research_manifest_run_rejects_invalid_shared_state_schema_version(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    initialize_shared_state_db(shared_state_db_path)

    with sqlite3.connect(shared_state_db_path) as connection:
        connection.execute(
            "UPDATE shared_state_meta SET value = ? WHERE key = 'schema_version'",
            ("shared_state_v999",),
        )
        connection.commit()

    with pytest.raises(ValueError, match="shared state schema_version must be"):
        generate_research_manifest_run(
            periods_path,
            grids_path,
            source_families=["news"],
            run_root_dir=tmp_path / "runs",
            shared_state_db_path=shared_state_db_path,
            run_id="20260324T010203Z_deadbeef",
        )


def test_generate_research_manifest_run_rejects_invalid_status_in_shared_db(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    initialize_shared_state_db(shared_state_db_path)

    with sqlite3.connect(shared_state_db_path) as connection:
        connection.execute("DROP TABLE shared_cache_entries")
        connection.execute(
            """
            CREATE TABLE shared_cache_entries (
                cache_key TEXT PRIMARY KEY,
                cache_key_version TEXT NOT NULL,
                source_family TEXT NOT NULL,
                symbol TEXT NOT NULL,
                period_id TEXT NOT NULL,
                period_signature TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO shared_cache_entries (
                cache_key, cache_key_version, source_family, symbol, period_id, period_signature, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("cache_a", CACHE_KEY_VERSION, "news", "BTCUSD", "p_alpha", "sig_alpha", "queued", "t1", "t1"),
        )
        connection.commit()

    with pytest.raises(ValueError, match="status must be one of"):
        generate_research_manifest_run(
            periods_path,
            grids_path,
            source_families=["news"],
            run_root_dir=tmp_path / "runs",
            shared_state_db_path=shared_state_db_path,
            run_id="20260324T010203Z_deadbeef",
        )


def test_generate_research_manifest_run_rejects_invalid_source_family_in_shared_db(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    shared_state_db_path = tmp_path / "shared" / "shared_state.sqlite3"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    initialize_shared_state_db(shared_state_db_path)

    with sqlite3.connect(shared_state_db_path) as connection:
        connection.execute("DROP TABLE shared_cache_entries")
        connection.execute(
            """
            CREATE TABLE shared_cache_entries (
                cache_key TEXT PRIMARY KEY,
                cache_key_version TEXT NOT NULL,
                source_family TEXT NOT NULL,
                symbol TEXT NOT NULL,
                period_id TEXT NOT NULL,
                period_signature TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO shared_cache_entries (
                cache_key, cache_key_version, source_family, symbol, period_id, period_signature, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("cache_a", CACHE_KEY_VERSION, "podcast", "BTCUSD", "p_alpha", "sig_alpha", "pending", "t1", "t1"),
        )
        connection.commit()

    with pytest.raises(ValueError, match="source_family must be one of"):
        generate_research_manifest_run(
            periods_path,
            grids_path,
            source_families=["news"],
            run_root_dir=tmp_path / "runs",
            shared_state_db_path=shared_state_db_path,
            run_id="20260324T010203Z_deadbeef",
        )


def test_generate_research_manifest_run_rejects_shared_db_open_failure(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    grids_path = tmp_path / "grids.csv"
    shared_state_db_path = tmp_path / "shared_state_dir"
    _write_valid_periods_csv(periods_path)
    _write_valid_grids_csv(grids_path)
    shared_state_db_path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="failed to open shared state db"):
        generate_research_manifest_run(
            periods_path,
            grids_path,
            source_families=["news"],
            run_root_dir=tmp_path / "runs",
            shared_state_db_path=shared_state_db_path,
            run_id="20260324T010203Z_deadbeef",
        )


def test_source_family_versions_are_fixed_for_current_supported_families() -> None:
    assert CACHE_KEY_VERSION == "acquisition_cache_v1"
    assert CACHE_METADATA_SCHEMA_VERSION == "cache_metadata_v1"
    assert DEFAULT_SHARED_CACHE_METADATA_PATH == Path("var/cache/external_signals/cache_metadata.csv")

def test_acquisition_ids_do_not_collide_for_same_symbol_across_periods(tmp_path: Path) -> None:
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
            ["p_one", "2024-01-10", "2024-01-09", "2024-01-11", "A", "etf", "BTCUSD", "x", "g1"],
            ["p_two", "2024-01-12", "2024-01-11", "2024-01-13", "B", "etf", "BTCUSD", "y", "g2"],
        ],
    )

    acquisition_rows = build_acquisition_manifest_rows(
        load_period_rows(periods_path),
        run_id="run_fixed",
        source_families=["news"],
        created_at="2026-03-24T00:00:00Z",
    )

    assert len({row["acquisition_id"] for row in acquisition_rows}) == 2


def test_cache_keys_do_not_collide_for_multiple_source_families_on_same_period(tmp_path: Path) -> None:
    periods_path = tmp_path / "periods.csv"
    _write_valid_periods_csv(periods_path)

    acquisition_rows = build_acquisition_manifest_rows(
        load_period_rows(periods_path)[:1],
        run_id="run_fixed",
        source_families=["news", "sns"],
        created_at="2026-03-24T00:00:00Z",
    )

    assert len({row["cache_key"] for row in acquisition_rows}) == 2


def test_results_status_constants_are_fixed() -> None:
    assert ALLOWED_RESULT_STATUSES == ("pending", "running", "completed", "failed")
