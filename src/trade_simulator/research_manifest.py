from __future__ import annotations

import csv
import hashlib
import json
import secrets
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

INPUT_SCHEMA_VERSION = "research_manifest_input_v1"
ENGINE_VERSION = "research_manifest_dry_run_v1"
CACHE_KEY_VERSION = "acquisition_cache_v1"
CACHE_METADATA_SCHEMA_VERSION = "cache_metadata_v1"
DEFAULT_SHARED_CACHE_METADATA_PATH = Path("var/cache/external_signals/cache_metadata.csv")

RESULT_STATUS_PENDING = "pending"
RESULT_STATUS_RUNNING = "running"
RESULT_STATUS_COMPLETED = "completed"
RESULT_STATUS_FAILED = "failed"
ALLOWED_RESULT_STATUSES = (
    RESULT_STATUS_PENDING,
    RESULT_STATUS_RUNNING,
    RESULT_STATUS_COMPLETED,
    RESULT_STATUS_FAILED,
)

ERROR_CODE_VALIDATION = "validation_error"
ERROR_CODE_RUNTIME = "runtime_error"
ERROR_CODE_INTERNAL = "internal_error"
ALLOWED_ERROR_CODES = (
    "",
    ERROR_CODE_VALIDATION,
    ERROR_CODE_RUNTIME,
    ERROR_CODE_INTERNAL,
)

SOURCE_FAMILY_NEWS = "news"
SOURCE_FAMILY_SNS = "sns"
ALLOWED_SOURCE_FAMILIES = (
    SOURCE_FAMILY_NEWS,
    SOURCE_FAMILY_SNS,
)
# Source-family extension rule:
# - Add only to ALLOWED_SOURCE_FAMILIES when the new family can reuse the same acquisition identity shape.
# - Bump CACHE_KEY_VERSION when cache-key inputs or semantics change.
# - Bump CACHE_METADATA_SCHEMA_VERSION when persisted cache metadata columns or meanings change.

PERIOD_REQUIRED_COLUMNS = (
    "period_id",
    "event_date",
    "window_start",
    "window_end",
    "short_name",
    "event_type",
    "symbol",
    "note",
    "overlap_group",
)

GRID_REQUIRED_COLUMNS = (
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
)

PERIOD_SIGNATURE_COLUMNS = (
    "period_id",
    "event_date",
    "window_start",
    "window_end",
    "short_name",
    "event_type",
    "symbol",
    "overlap_group",
)

GRID_SIGNATURE_COLUMNS = (
    "grid_id",
    "consumption_series_name",
    "entry_count_threshold",
    "exit_after_inactive_periods",
    "take_profit",
    "stop_loss",
    "max_hold_minutes",
    "price_spike_limit",
    "volume_multiplier",
)

MANIFEST_COLUMNS = (
    "run_id",
    "case_id",
    "case_signature",
    "period_id",
    "period_signature",
    "grid_id",
    "grid_signature",
    "short_name",
    "event_type",
    "symbol",
    "window_start",
    "window_end",
    "grid_family",
    "consumption_series_name",
    "entry_count_threshold",
    "exit_after_inactive_periods",
    "input_schema_version",
    "engine_version",
)

RESULTS_INDEX_COLUMNS = (
    "run_id",
    "case_id",
    "case_signature",
    "status",
    "error_code",
    "error_message",
    "created_at",
    "updated_at",
)

ACQUISITION_MANIFEST_COLUMNS = (
    "run_id",
    "acquisition_id",
    "source_family",
    "symbol",
    "period_id",
    "period_signature",
    "window_start",
    "window_end",
    "status",
    "cache_key",
    "created_at",
    "updated_at",
)

CACHE_METADATA_COLUMNS = (
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
)

CASE_ACQUISITION_LINK_COLUMNS = (
    "run_id",
    "case_id",
    "case_signature",
    "acquisition_id",
    "cache_key",
)


@dataclass(frozen=True)
class ResearchManifestRun:
    run_id: str
    run_dir: Path
    periods_copy_path: Path
    grids_copy_path: Path
    manifest_path: Path
    results_index_path: Path
    acquisition_manifest_path: Path
    case_acquisition_links_path: Path
    cache_metadata_path: Path
    shared_cache_metadata_path: Path
    unresolved_acquisitions_path: Path
    metadata_path: Path
    period_row_count: int
    grid_row_count: int
    eligible_grid_row_count: int
    manifest_case_count: int
    acquisition_manifest_count: int
    unresolved_acquisition_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_run_id(now: datetime | None = None) -> str:
    resolved_now = now or _utc_now()
    return f"{resolved_now.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"


def _read_csv_rows(csv_path: str | Path, *, required_columns: tuple[str, ...], entity_name: str) -> list[dict[str, str]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{entity_name} csv must include a header")

        missing_columns = [column for column in required_columns if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"{entity_name} csv missing required columns: {', '.join(missing_columns)}")

        return [
            {str(key): "" if value is None else str(value) for key, value in row.items()}
            for row in reader
        ]


def _strip_and_validate_null_string(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if stripped.lower() == "null":
        raise ValueError(f'{field_name} must not use the string "null"; use an empty field for null')
    return stripped


def _parse_required_text(row: dict[str, str], field_name: str) -> str:
    value = _strip_and_validate_null_string(row.get(field_name, ""), field_name=field_name)
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _parse_optional_text(row: dict[str, str], field_name: str) -> str | None:
    value = _strip_and_validate_null_string(row.get(field_name, ""), field_name=field_name)
    if not value:
        return None
    return value


def _parse_iso_date(row: dict[str, str], field_name: str) -> str:
    value = _parse_required_text(row, field_name)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _parse_decimal_string(
    row: dict[str, str],
    field_name: str,
    *,
    required: bool,
    positive_only: bool = False,
    integer_only: bool = False,
) -> str | None:
    raw_value = _strip_and_validate_null_string(row.get(field_name, ""), field_name=field_name)
    if not raw_value:
        if required:
            raise ValueError(f"{field_name} must be provided")
        return None

    try:
        parsed = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a valid number") from exc

    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite number")
    if integer_only and parsed != parsed.to_integral_value():
        raise ValueError(f"{field_name} must be an integer")
    if positive_only and parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")

    normalized = parsed.normalize()
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        rendered = "0"
    return rendered or "0"


def _parse_bool(row: dict[str, str], field_name: str) -> bool:
    value = _parse_required_text(row, field_name).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{field_name} must be true or false")


def _hash_canonical_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_result_status(status: str) -> str:
    if status not in ALLOWED_RESULT_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(ALLOWED_RESULT_STATUSES)}")
    return status


def validate_acquisition_status(status: str) -> str:
    return validate_result_status(status)


def validate_acquisition_status_transition(current_status: str, next_status: str) -> str:
    resolved_current = validate_acquisition_status(current_status)
    resolved_next = validate_acquisition_status(next_status)
    allowed_transitions = {
        RESULT_STATUS_PENDING: {RESULT_STATUS_RUNNING},
        RESULT_STATUS_RUNNING: {RESULT_STATUS_COMPLETED, RESULT_STATUS_FAILED},
        RESULT_STATUS_COMPLETED: set(),
        RESULT_STATUS_FAILED: set(),
    }
    if resolved_next not in allowed_transitions[resolved_current]:
        raise ValueError(f"invalid acquisition status transition: {resolved_current} -> {resolved_next}")
    return resolved_next


def validate_error_code(*, status: str, error_code: str, error_message: str) -> str:
    if error_code not in ALLOWED_ERROR_CODES:
        raise ValueError(f"error_code must be one of: {', '.join(code or '<empty>' for code in ALLOWED_ERROR_CODES)}")
    if status == RESULT_STATUS_FAILED:
        if not error_code:
            raise ValueError("error_code is required when status is failed")
        if not error_message.strip():
            raise ValueError("error_message is required when status is failed")
    elif error_code or error_message.strip():
        raise ValueError("error_code and error_message must be empty unless status is failed")
    return error_code


def _validate_required_columns(rows: list[dict[str, str]], required_columns: tuple[str, ...], *, entity_name: str) -> None:
    if not rows:
        return

    missing_columns = [column for column in required_columns if column not in rows[0]]
    if missing_columns:
        raise ValueError(f"{entity_name} missing required columns: {', '.join(missing_columns)}")


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
        status = validate_result_status(RESULT_STATUS_PENDING)
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


def build_initial_cache_metadata_rows() -> list[dict[str, object]]:
    return []


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


def load_shared_cache_metadata_rows(
    shared_cache_metadata_path: str | Path = DEFAULT_SHARED_CACHE_METADATA_PATH,
) -> list[dict[str, str]]:
    path = Path(shared_cache_metadata_path)
    if not path.exists():
        return []
    return load_cache_metadata_rows(path)


def find_cache_metadata_row(
    cache_metadata_rows: list[dict[str, str]],
    *,
    cache_key: str,
) -> dict[str, str] | None:
    matches = [row for row in cache_metadata_rows if row["cache_key"] == cache_key]
    if len(matches) > 1:
        raise ValueError(f"cache_key must be unique in cache_metadata: {cache_key}")
    if not matches:
        return None
    return matches[0]


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


def upsert_cache_metadata_row(
    cache_metadata_rows: list[dict[str, str]],
    *,
    cache_key: str,
    source_family: str,
    symbol: str,
    period_id: str,
    period_signature: str,
    status: str,
    created_at: str,
    updated_at: str,
) -> list[dict[str, str]]:
    new_row = _build_cache_metadata_row(
        cache_key=cache_key,
        source_family=source_family,
        symbol=symbol,
        period_id=period_id,
        period_signature=period_signature,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
    )
    existing_row = find_cache_metadata_row(cache_metadata_rows, cache_key=cache_key)
    if existing_row is None:
        return [*cache_metadata_rows, new_row]

    immutable_columns = ("cache_key", "cache_key_version", "source_family", "symbol", "period_id", "period_signature", "schema_version")
    for column in immutable_columns:
        if existing_row[column] != new_row[column]:
            raise ValueError(f"cache_metadata row mismatch for cache_key {cache_key}: {column}")

    updated_rows: list[dict[str, str]] = []
    for row in cache_metadata_rows:
        if row["cache_key"] == cache_key:
            updated_rows.append(
                {
                    **row,
                    "status": new_row["status"],
                    "updated_at": updated_at,
                }
            )
        else:
            updated_rows.append(row)
    return updated_rows


def update_cache_metadata_status(
    cache_metadata_rows: list[dict[str, str]],
    *,
    cache_key: str,
    next_status: str,
    updated_at: str,
) -> list[dict[str, str]]:
    existing_row = find_cache_metadata_row(cache_metadata_rows, cache_key=cache_key)
    if existing_row is None:
        raise ValueError(f"cache_key not found in cache_metadata: {cache_key}")
    validate_acquisition_status_transition(existing_row["status"], next_status)
    updated_rows: list[dict[str, str]] = []
    for row in cache_metadata_rows:
        if row["cache_key"] == cache_key:
            updated_rows.append(
                {
                    **row,
                    "status": next_status,
                    "updated_at": updated_at,
                }
            )
        else:
            updated_rows.append(row)
    return updated_rows


def save_shared_cache_metadata_rows(
    cache_metadata_rows: list[dict[str, str]],
    shared_cache_metadata_path: str | Path = DEFAULT_SHARED_CACHE_METADATA_PATH,
) -> Path:
    path = Path(shared_cache_metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(path, CACHE_METADATA_COLUMNS, cache_metadata_rows)
    return path


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


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def generate_research_manifest_run(
    periods_csv_path: str | Path,
    grids_csv_path: str | Path,
    *,
    source_families: list[str] | tuple[str, ...],
    run_root_dir: str | Path = "var/research_runs",
    shared_cache_metadata_path: str | Path = DEFAULT_SHARED_CACHE_METADATA_PATH,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> ResearchManifestRun:
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
    shared_cache_metadata_rows = load_shared_cache_metadata_rows(shared_cache_metadata_path)
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
        "shared_cache_metadata_path": str(Path(shared_cache_metadata_path)),
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
        shared_cache_metadata_path=Path(shared_cache_metadata_path),
        unresolved_acquisitions_path=unresolved_acquisitions_path,
        metadata_path=metadata_path,
        period_row_count=len(period_rows),
        grid_row_count=len(grid_rows),
        eligible_grid_row_count=len(eligible_grid_rows),
        manifest_case_count=len(manifest_rows),
        acquisition_manifest_count=len(acquisition_manifest_rows),
        unresolved_acquisition_count=len(unresolved_acquisition_rows),
    )
