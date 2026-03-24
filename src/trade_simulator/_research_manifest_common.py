from __future__ import annotations

import csv
import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

INPUT_SCHEMA_VERSION = "research_manifest_input_v1"
ENGINE_VERSION = "research_manifest_dry_run_v1"
CACHE_KEY_VERSION = "acquisition_cache_v1"
CACHE_METADATA_SCHEMA_VERSION = "cache_metadata_v1"
SHARED_STATE_SCHEMA_VERSION = "shared_state_v2"
DEFAULT_SHARED_STATE_DB_PATH = Path("var/cache/external_signals/shared_state.sqlite3")

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

SHARED_CACHE_ENTRY_COLUMNS = (
    "cache_key",
    "cache_key_version",
    "source_family",
    "symbol",
    "period_id",
    "period_signature",
    "status",
    "created_at",
    "updated_at",
    "claimed_at",
    "claimed_by",
    "lease_expires_at",
    "last_heartbeat_at",
    "auto_retry_count",
    "retryable",
    "last_error_code",
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
    shared_state_db_path: Path
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


def _parse_iso_datetime_text(value: str, *, field_name: str) -> datetime:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty ISO datetime")
    normalized = stripped.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _render_utc_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect_shared_state_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path)
    except (sqlite3.Error, OSError) as exc:
        raise ValueError(f"failed to open shared state db: {path}") from exc
    connection.row_factory = sqlite3.Row
    return connection


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


def _parse_non_negative_integer_text(row: dict[str, str], field_name: str) -> str:
    raw_value = _parse_required_text(row, field_name)
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return str(parsed)


def _parse_bool_flag_text(row: dict[str, str], field_name: str) -> str:
    raw_value = _parse_required_text(row, field_name).lower()
    if raw_value in ("1", "true"):
        return "1"
    if raw_value in ("0", "false"):
        return "0"
    raise ValueError(f"{field_name} must be 0 or 1")


def _hash_canonical_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_result_status(status: str) -> str:
    if status not in ALLOWED_RESULT_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(ALLOWED_RESULT_STATUSES)}")
    return status


def validate_acquisition_status(status: str) -> str:
    return validate_result_status(status)


def validate_source_family(source_family: str) -> str:
    if source_family not in ALLOWED_SOURCE_FAMILIES:
        raise ValueError(f"source_family must be one of: {', '.join(ALLOWED_SOURCE_FAMILIES)}")
    return source_family


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


def _load_json_object(path: Path, *, entity_name: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{entity_name} must be a JSON object")
    return payload


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
