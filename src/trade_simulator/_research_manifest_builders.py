from __future__ import annotations

from pathlib import Path

from ._research_manifest_common import (
    ACQUISITION_MANIFEST_COLUMNS,
    CACHE_KEY_VERSION,
    CACHE_METADATA_COLUMNS,
    CACHE_METADATA_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRID_REQUIRED_COLUMNS,
    GRID_SIGNATURE_COLUMNS,
    INPUT_SCHEMA_VERSION,
    PERIOD_REQUIRED_COLUMNS,
    PERIOD_SIGNATURE_COLUMNS,
    RESULT_STATUS_COMPLETED,
    RESULT_STATUS_PENDING,
    RESULT_STATUS_RUNNING,
    _hash_canonical_payload,
    _parse_bool,
    _parse_decimal_string,
    _parse_iso_date,
    _parse_optional_text,
    _parse_required_text,
    _read_csv_rows,
    _strip_and_validate_null_string,
    validate_acquisition_status,
    validate_error_code,
)


def _canonical_payload(row: dict[str, object], columns: tuple[str, ...]) -> dict[str, object]:
    # Signatures intentionally operate on a fixed column order with normalized scalar values.
    # Dates are stored as ISO strings, numbers as canonical decimal strings, and missing optional
    # values as explicit null so hash generation is stable across CSV formatting differences.
    return {column: row.get(column) for column in columns}


def load_period_rows(csv_path: str | Path) -> list[dict[str, object]]:
    rows = _read_csv_rows(csv_path, required_columns=PERIOD_REQUIRED_COLUMNS, entity_name="periods")

    normalized_rows: list[dict[str, object]] = []
    seen_period_ids: set[str] = set()
    for row in rows:
        period_id = _parse_required_text(row, "period_id")
        if period_id in seen_period_ids:
            raise ValueError(f"period_id must be unique: {period_id}")
        seen_period_ids.add(period_id)

        event_date = _parse_iso_date(row, "event_date")
        window_start = _parse_iso_date(row, "window_start")
        window_end = _parse_iso_date(row, "window_end")
        if window_start > event_date or event_date > window_end:
            raise ValueError("window_start <= event_date <= window_end must hold")

        normalized_row: dict[str, object] = {
            "period_id": period_id,
            "event_date": event_date,
            "window_start": window_start,
            "window_end": window_end,
            "short_name": _parse_required_text(row, "short_name"),
            "event_type": _parse_required_text(row, "event_type"),
            "symbol": _parse_required_text(row, "symbol"),
            "note": _parse_required_text(row, "note"),
            "overlap_group": _parse_required_text(row, "overlap_group"),
        }
        normalized_row["period_signature"] = _hash_canonical_payload(
            _canonical_payload(normalized_row, PERIOD_SIGNATURE_COLUMNS)
        )
        normalized_rows.append(normalized_row)

    return normalized_rows


def load_grid_rows(csv_path: str | Path) -> list[dict[str, object]]:
    rows = _read_csv_rows(csv_path, required_columns=GRID_REQUIRED_COLUMNS, entity_name="grids")

    normalized_rows: list[dict[str, object]] = []
    seen_grid_ids: set[str] = set()
    for row in rows:
        grid_id = _parse_required_text(row, "grid_id")
        if grid_id in seen_grid_ids:
            raise ValueError(f"grid_id must be unique: {grid_id}")
        seen_grid_ids.add(grid_id)

        normalized_row: dict[str, object] = {
            "grid_id": grid_id,
            "grid_family": _parse_required_text(row, "grid_family"),
            "consumption_series_name": _parse_required_text(row, "consumption_series_name"),
            "entry_count_threshold": _parse_decimal_string(
                row, "entry_count_threshold", required=True, positive_only=True
            ),
            "exit_after_inactive_periods": _parse_decimal_string(
                row, "exit_after_inactive_periods", required=True, positive_only=True, integer_only=True
            ),
            "take_profit": _parse_decimal_string(row, "take_profit", required=False),
            "stop_loss": _parse_decimal_string(row, "stop_loss", required=False),
            "max_hold_minutes": _parse_decimal_string(row, "max_hold_minutes", required=False, integer_only=True),
            "price_spike_limit": _parse_decimal_string(row, "price_spike_limit", required=False),
            "volume_multiplier": _parse_decimal_string(row, "volume_multiplier", required=False),
            "enabled": _parse_bool(row, "enabled"),
            "note": _parse_optional_text(row, "note"),
        }
        normalized_row["grid_signature"] = _hash_canonical_payload(
            _canonical_payload(normalized_row, GRID_SIGNATURE_COLUMNS)
        )
        normalized_rows.append(normalized_row)

    return normalized_rows


def normalize_source_families(source_families: list[str] | tuple[str, ...]) -> list[str]:
    from ._research_manifest_common import ALLOWED_SOURCE_FAMILIES

    normalized_source_families: list[str] = []
    seen_source_families: set[str] = set()

    for raw_value in source_families:
        normalized_value = _strip_and_validate_null_string(str(raw_value), field_name="source_family").lower()
        if not normalized_value:
            raise ValueError("source_family must be a non-empty string")
        if normalized_value not in ALLOWED_SOURCE_FAMILIES:
            raise ValueError(f"source_family must be one of: {', '.join(ALLOWED_SOURCE_FAMILIES)}")
        if normalized_value in seen_source_families:
            continue
        seen_source_families.add(normalized_value)
        normalized_source_families.append(normalized_value)

    if not normalized_source_families:
        raise ValueError("at least one source_family must be provided")

    return normalized_source_families


def select_eligible_signal_only_grids(grid_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row for row in grid_rows if row["enabled"] is True and row["grid_family"] == "signal_only"
    ]


def build_manifest_rows(
    period_rows: list[dict[str, object]],
    grid_rows: list[dict[str, object]],
    *,
    run_id: str,
    input_schema_version: str = INPUT_SCHEMA_VERSION,
    engine_version: str = ENGINE_VERSION,
) -> list[dict[str, object]]:
    manifest_rows: list[dict[str, object]] = []

    for period_row in period_rows:
        for grid_row in grid_rows:
            case_id = f'{period_row["period_id"]}__{grid_row["grid_id"]}'
            case_signature = _hash_canonical_payload(
                {
                    "period_signature": period_row["period_signature"],
                    "grid_signature": grid_row["grid_signature"],
                    "input_schema_version": input_schema_version,
                    "engine_version": engine_version,
                }
            )
            manifest_rows.append(
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "case_signature": case_signature,
                    "period_id": period_row["period_id"],
                    "period_signature": period_row["period_signature"],
                    "grid_id": grid_row["grid_id"],
                    "grid_signature": grid_row["grid_signature"],
                    "short_name": period_row["short_name"],
                    "event_type": period_row["event_type"],
                    "symbol": period_row["symbol"],
                    "window_start": period_row["window_start"],
                    "window_end": period_row["window_end"],
                    "grid_family": grid_row["grid_family"],
                    "consumption_series_name": grid_row["consumption_series_name"],
                    "entry_count_threshold": grid_row["entry_count_threshold"],
                    "exit_after_inactive_periods": grid_row["exit_after_inactive_periods"],
                    "input_schema_version": input_schema_version,
                    "engine_version": engine_version,
                }
            )

    return manifest_rows


def build_results_index_rows(
    manifest_rows: list[dict[str, object]],
    *,
    created_at: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in manifest_rows:
        status = validate_acquisition_status(RESULT_STATUS_PENDING)
        error_code = validate_error_code(status=status, error_code="", error_message="")
        rows.append(
            {
                "run_id": row["run_id"],
                "case_id": row["case_id"],
                "case_signature": row["case_signature"],
                "status": status,
                "error_code": error_code,
                "error_message": "",
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
    return rows


def build_acquisition_cache_key(
    *,
    source_family: str,
    symbol: str,
    period_signature: str,
    input_schema_version: str,
    cache_key_version: str = CACHE_KEY_VERSION,
) -> str:
    if not source_family:
        raise ValueError("source_family is required to build cache_key")
    if not symbol:
        raise ValueError("symbol is required to build cache_key")
    if not period_signature:
        raise ValueError("period_signature is required to build cache_key")
    if not input_schema_version:
        raise ValueError("input_schema_version is required to build cache_key")

    return _hash_canonical_payload(
        {
            "cache_key_version": cache_key_version,
            "source_family": source_family,
            "symbol": symbol,
            "period_signature": period_signature,
            "input_schema_version": input_schema_version,
        }
    )


def load_cache_metadata_rows(csv_path: str | Path) -> list[dict[str, str]]:
    rows = _read_csv_rows(csv_path, required_columns=CACHE_METADATA_COLUMNS, entity_name="cache_metadata")
    normalized_rows: list[dict[str, str]] = []
    seen_cache_keys: dict[str, dict[str, str]] = {}

    for row in rows:
        status = validate_acquisition_status(_parse_required_text(row, "status"))
        schema_version = _parse_required_text(row, "schema_version")
        cache_key_version = _parse_required_text(row, "cache_key_version")
        if schema_version != CACHE_METADATA_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {CACHE_METADATA_SCHEMA_VERSION}")
        if cache_key_version != CACHE_KEY_VERSION:
            raise ValueError(f"cache_key_version must be {CACHE_KEY_VERSION}")

        normalized_row = {
            "cache_key": _parse_required_text(row, "cache_key"),
            "cache_key_version": cache_key_version,
            "source_family": _parse_required_text(row, "source_family"),
            "symbol": _parse_required_text(row, "symbol"),
            "period_id": _parse_required_text(row, "period_id"),
            "period_signature": _parse_required_text(row, "period_signature"),
            "status": status,
            "created_at": _parse_required_text(row, "created_at"),
            "updated_at": _parse_required_text(row, "updated_at"),
            "schema_version": schema_version,
        }
        existing_row = seen_cache_keys.get(normalized_row["cache_key"])
        if existing_row is not None:
            raise ValueError(f'cache_key must be unique in cache_metadata: {normalized_row["cache_key"]}')
        seen_cache_keys[normalized_row["cache_key"]] = normalized_row
        normalized_rows.append(normalized_row)

    return normalized_rows


def _build_cache_metadata_row(
    *,
    cache_key: str,
    source_family: str,
    symbol: str,
    period_id: str,
    period_signature: str,
    status: str,
    created_at: str,
    updated_at: str,
) -> dict[str, str]:
    return {
        "cache_key": cache_key,
        "cache_key_version": CACHE_KEY_VERSION,
        "source_family": source_family,
        "symbol": symbol,
        "period_id": period_id,
        "period_signature": period_signature,
        "status": validate_acquisition_status(status),
        "created_at": created_at,
        "updated_at": updated_at,
        "schema_version": CACHE_METADATA_SCHEMA_VERSION,
    }


def build_cache_metadata_snapshot_rows(
    shared_cache_entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    # Run snapshots keep only the audit/repro fields needed to describe the run-start shared truth.
    # Lease and heartbeat columns stay in SQLite runtime truth and are intentionally omitted here.
    return [
        _build_cache_metadata_row(
            cache_key=row["cache_key"],
            source_family=row["source_family"],
            symbol=row["symbol"],
            period_id=row["period_id"],
            period_signature=row["period_signature"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in shared_cache_entries
    ]


def build_acquisition_manifest_rows(
    period_rows: list[dict[str, object]],
    *,
    run_id: str,
    source_families: list[str] | tuple[str, ...],
    created_at: str,
    input_schema_version: str = INPUT_SCHEMA_VERSION,
) -> list[dict[str, object]]:
    normalized_source_families = normalize_source_families(source_families)
    acquisition_rows: list[dict[str, object]] = []

    for source_family in normalized_source_families:
        for period_row in period_rows:
            status = validate_acquisition_status(RESULT_STATUS_PENDING)
            cache_key = build_acquisition_cache_key(
                source_family=source_family,
                symbol=str(period_row["symbol"]),
                period_signature=str(period_row["period_signature"]),
                input_schema_version=input_schema_version,
            )
            acquisition_rows.append(
                {
                    "run_id": run_id,
                    "acquisition_id": f'{source_family}__{period_row["symbol"]}__{period_row["period_id"]}',
                    "source_family": source_family,
                    "symbol": period_row["symbol"],
                    "period_id": period_row["period_id"],
                    "period_signature": period_row["period_signature"],
                    "window_start": period_row["window_start"],
                    "window_end": period_row["window_end"],
                    "status": status,
                    "cache_key": cache_key,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )

    return acquisition_rows


def build_case_acquisition_links(
    manifest_rows: list[dict[str, object]],
    acquisition_manifest_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    acquisition_by_period_signature: dict[str, list[dict[str, object]]] = {}
    for acquisition_row in acquisition_manifest_rows:
        period_signature = str(acquisition_row["period_signature"])
        acquisition_by_period_signature.setdefault(period_signature, []).append(acquisition_row)

    link_rows: list[dict[str, object]] = []
    for manifest_row in manifest_rows:
        period_signature = str(manifest_row["period_signature"])
        linked_acquisitions = acquisition_by_period_signature.get(period_signature, [])
        for acquisition_row in linked_acquisitions:
            link_rows.append(
                {
                    "run_id": manifest_row["run_id"],
                    "case_id": manifest_row["case_id"],
                    "case_signature": manifest_row["case_signature"],
                    "acquisition_id": acquisition_row["acquisition_id"],
                    "cache_key": acquisition_row["cache_key"],
                }
            )

    return link_rows


def build_unresolved_acquisition_rows(
    acquisition_manifest_rows: list[dict[str, object]],
    cache_metadata_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    resolved_by_cache_key = {row["cache_key"]: row["status"] for row in cache_metadata_rows}
    unresolved_rows: list[dict[str, object]] = []
    for row in acquisition_manifest_rows:
        cache_status = resolved_by_cache_key.get(str(row["cache_key"]))
        # Running acquisitions are excluded from unresolved output so later runs do not try to
        # claim work that another run has already marked in progress. Pending, failed, and missing
        # cache metadata rows stay unresolved because they still require acquisition work.
        if cache_status in (RESULT_STATUS_COMPLETED, RESULT_STATUS_RUNNING):
            continue
        unresolved_rows.append(row)
    return unresolved_rows
