from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ._research_manifest_builders import (
    build_acquisition_manifest_rows,
    build_cache_metadata_snapshot_rows,
    build_case_acquisition_links,
    build_manifest_rows,
    build_results_index_rows,
    build_unresolved_acquisition_rows,
    load_grid_rows,
    load_period_rows,
    normalize_source_families,
    select_eligible_signal_only_grids,
)
from ._research_manifest_common import (
    ACQUISITION_MANIFEST_COLUMNS,
    ALLOWED_SOURCE_FAMILIES,
    CACHE_METADATA_COLUMNS,
    CASE_ACQUISITION_LINK_COLUMNS,
    DEFAULT_SHARED_STATE_DB_PATH,
    ENGINE_VERSION,
    INPUT_SCHEMA_VERSION,
    MANIFEST_COLUMNS,
    RESULTS_INDEX_COLUMNS,
    ResearchManifestRun,
    _load_json_object,
    _read_csv_rows,
    _render_utc_datetime,
    _utc_now,
    _write_csv,
    generate_run_id,
)
from ._research_manifest_shared_state import (
    claim_shared_cache_entry,
    complete_shared_cache_entry,
    ensure_shared_cache_entry_for_acquisition,
    fail_shared_cache_entry,
    find_shared_cache_entry,
    load_shared_cache_entries,
)


def load_research_run_metadata(run_dir: str | Path) -> dict[str, object]:
    return _load_json_object(Path(run_dir) / "metadata.json", entity_name="research run metadata")


def load_run_acquisition_manifest_row(
    run_dir: str | Path,
    *,
    acquisition_id: str,
) -> dict[str, str]:
    rows = _read_csv_rows(
        Path(run_dir) / "acquisition_manifest.csv",
        required_columns=ACQUISITION_MANIFEST_COLUMNS,
        entity_name="acquisition_manifest",
    )
    matches = [row for row in rows if row["acquisition_id"] == acquisition_id]
    if len(matches) > 1:
        raise ValueError(f"acquisition_id must be unique in acquisition_manifest: {acquisition_id}")
    if not matches:
        raise ValueError(f"acquisition_id not found in acquisition_manifest: {acquisition_id}")
    return matches[0]


def fetch_acquisition_payload(acquisition_row: dict[str, str]) -> dict[str, object]:
    source_family = acquisition_row["source_family"]
    if source_family not in ALLOWED_SOURCE_FAMILIES:
        raise ValueError(f"unsupported source_family for fetch: {source_family}")
    return {
        "source_family": source_family,
        "fetch_mode": "stub",
        "cache_key": acquisition_row["cache_key"],
        "acquisition_id": acquisition_row["acquisition_id"],
    }


def orchestrate_research_acquisition(
    run_dir: str | Path,
    *,
    acquisition_id: str,
    claimed_by: str,
    lease_duration_seconds: int,
    fetcher: Optional[Callable[[dict[str, str]], dict[str, object]]] = None,
    decision_source: str = "shared_truth",
) -> dict[str, object]:
    if decision_source != "shared_truth":
        raise ValueError("decision_source must be shared_truth")
    resolved_run_dir = Path(run_dir)
    run_metadata = load_research_run_metadata(resolved_run_dir)
    shared_state_db_path = str(run_metadata.get("shared_state_db_path", "")).strip()
    if not shared_state_db_path:
        raise ValueError("research run metadata must include shared_state_db_path")

    acquisition_row = load_run_acquisition_manifest_row(resolved_run_dir, acquisition_id=acquisition_id)
    execution_started_at = _render_utc_datetime(_utc_now())
    ensure_shared_cache_entry_for_acquisition(
        shared_state_db_path,
        acquisition_row=acquisition_row,
        created_at=execution_started_at,
    )
    shared_truth_before = find_shared_cache_entry(shared_state_db_path, cache_key=acquisition_row["cache_key"])

    try:
        claim_shared_cache_entry(
            shared_state_db_path,
            cache_key=acquisition_row["cache_key"],
            claimed_by=claimed_by,
            claimed_at=execution_started_at,
            lease_duration_seconds=lease_duration_seconds,
        )
    except ValueError as exc:
        latest_shared_truth = find_shared_cache_entry(shared_state_db_path, cache_key=acquisition_row["cache_key"])
        return {
            "run_dir": str(resolved_run_dir),
            "acquisition_id": acquisition_id,
            "cache_key": acquisition_row["cache_key"],
            "decision_source": decision_source,
            "outcome": "skipped",
            "skip_reason": "shared_truth_not_claimable",
            "shared_truth_status_before": None if shared_truth_before is None else shared_truth_before["status"],
            "shared_truth_status_after": None if latest_shared_truth is None else latest_shared_truth["status"],
            "message": str(exc),
        }

    active_fetcher = fetcher or fetch_acquisition_payload
    try:
        fetch_result = active_fetcher(acquisition_row)
    except Exception as exc:
        failed_at = _render_utc_datetime(_utc_now())
        failed_row = fail_shared_cache_entry(
            shared_state_db_path,
            cache_key=acquisition_row["cache_key"],
            claimed_by=claimed_by,
            failed_at=failed_at,
            retryable=False,
            last_error_code="runtime_error",
        )
        return {
            "run_dir": str(resolved_run_dir),
            "acquisition_id": acquisition_id,
            "cache_key": acquisition_row["cache_key"],
            "decision_source": decision_source,
            "outcome": "failed",
            "shared_truth_status_before": None if shared_truth_before is None else shared_truth_before["status"],
            "shared_truth_status_after": failed_row["status"],
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

    completed_at = _render_utc_datetime(_utc_now())
    completed_row = complete_shared_cache_entry(
        shared_state_db_path,
        cache_key=acquisition_row["cache_key"],
        claimed_by=claimed_by,
        completed_at=completed_at,
    )
    return {
        "run_dir": str(resolved_run_dir),
        "acquisition_id": acquisition_id,
        "cache_key": acquisition_row["cache_key"],
        "decision_source": decision_source,
        "outcome": "completed",
        "shared_truth_status_before": None if shared_truth_before is None else shared_truth_before["status"],
        "shared_truth_status_after": completed_row["status"],
        "fetch_result": fetch_result,
    }


def generate_research_manifest_run(
    periods_csv_path: str | Path,
    grids_csv_path: str | Path,
    *,
    source_families: list[str] | tuple[str, ...],
    run_root_dir: str | Path = "var/research_runs",
    shared_state_db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> ResearchManifestRun:
    # Run artifacts capture the run-start view for audit/repro. Later claim/skip decisions must
    # re-check shared_state_db_path instead of trusting these CSV snapshots.
    resolved_created_at = created_at or _utc_now()
    resolved_run_id = run_id or generate_run_id(resolved_created_at)
    created_at_text = resolved_created_at.isoformat().replace("+00:00", "Z")

    period_rows = load_period_rows(periods_csv_path)
    grid_rows = load_grid_rows(grids_csv_path)
    eligible_grid_rows = select_eligible_signal_only_grids(grid_rows)
    manifest_rows = build_manifest_rows(period_rows, eligible_grid_rows, run_id=resolved_run_id)
    results_index_rows = build_results_index_rows(manifest_rows, created_at=created_at_text)
    acquisition_manifest_rows = build_acquisition_manifest_rows(
        period_rows,
        run_id=resolved_run_id,
        source_families=source_families,
        created_at=created_at_text,
    )
    case_acquisition_link_rows = build_case_acquisition_links(manifest_rows, acquisition_manifest_rows)
    shared_cache_entries = load_shared_cache_entries(shared_state_db_path)
    shared_cache_metadata_rows = build_cache_metadata_snapshot_rows(shared_cache_entries)
    unresolved_acquisition_rows = build_unresolved_acquisition_rows(acquisition_manifest_rows, shared_cache_metadata_rows)

    run_dir = Path(run_root_dir) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    periods_copy_path = run_dir / "periods.csv"
    grids_copy_path = run_dir / "grids.csv"
    manifest_path = run_dir / "manifest.csv"
    results_index_path = run_dir / "results_index.csv"
    acquisition_manifest_path = run_dir / "acquisition_manifest.csv"
    case_acquisition_links_path = run_dir / "case_acquisition_links.csv"
    cache_metadata_path = run_dir / "cache_metadata.csv"
    unresolved_acquisitions_path = run_dir / "unresolved_acquisitions.csv"
    metadata_path = run_dir / "metadata.json"

    shutil.copyfile(Path(periods_csv_path), periods_copy_path)
    shutil.copyfile(Path(grids_csv_path), grids_copy_path)
    _write_csv(manifest_path, MANIFEST_COLUMNS, manifest_rows)
    _write_csv(results_index_path, RESULTS_INDEX_COLUMNS, results_index_rows)
    _write_csv(acquisition_manifest_path, ACQUISITION_MANIFEST_COLUMNS, acquisition_manifest_rows)
    _write_csv(case_acquisition_links_path, CASE_ACQUISITION_LINK_COLUMNS, case_acquisition_link_rows)
    _write_csv(cache_metadata_path, CACHE_METADATA_COLUMNS, shared_cache_metadata_rows)
    _write_csv(unresolved_acquisitions_path, ACQUISITION_MANIFEST_COLUMNS, unresolved_acquisition_rows)

    metadata = {
        "run_id": resolved_run_id,
        "created_at": created_at_text,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "source_families": normalize_source_families(source_families),
        "shared_state_db_path": str(Path(shared_state_db_path)),
        "shared_state_role": "runtime_truth",
        "cache_metadata_snapshot_role": "run_start_audit_repro_snapshot",
        "unresolved_acquisitions_role": "run_start_decision_record_recheck_shared_truth_before_execution",
        "periods_file_name": periods_copy_path.name,
        "grids_file_name": grids_copy_path.name,
        "period_row_count": len(period_rows),
        "grid_row_count": len(grid_rows),
        "eligible_grid_row_count": len(eligible_grid_rows),
        "manifest_case_count": len(manifest_rows),
        "acquisition_manifest_count": len(acquisition_manifest_rows),
        "cache_metadata_row_count": len(shared_cache_metadata_rows),
        "case_acquisition_link_count": len(case_acquisition_link_rows),
        "unresolved_acquisition_count": len(unresolved_acquisition_rows),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return ResearchManifestRun(
        run_id=resolved_run_id,
        run_dir=run_dir,
        periods_copy_path=periods_copy_path,
        grids_copy_path=grids_copy_path,
        manifest_path=manifest_path,
        results_index_path=results_index_path,
        acquisition_manifest_path=acquisition_manifest_path,
        case_acquisition_links_path=case_acquisition_links_path,
        cache_metadata_path=cache_metadata_path,
        shared_state_db_path=Path(shared_state_db_path),
        unresolved_acquisitions_path=unresolved_acquisitions_path,
        metadata_path=metadata_path,
        period_row_count=len(period_rows),
        grid_row_count=len(grid_rows),
        eligible_grid_row_count=len(eligible_grid_rows),
        manifest_case_count=len(manifest_rows),
        acquisition_manifest_count=len(acquisition_manifest_rows),
        unresolved_acquisition_count=len(unresolved_acquisition_rows),
    )
