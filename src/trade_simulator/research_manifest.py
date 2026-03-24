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


@dataclass(frozen=True)
class ResearchManifestRun:
    run_id: str
    run_dir: Path
    periods_copy_path: Path
    grids_copy_path: Path
    manifest_path: Path
    results_index_path: Path
    metadata_path: Path
    period_row_count: int
    grid_row_count: int
    eligible_grid_row_count: int
    manifest_case_count: int


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
    return [
        {
            "run_id": row["run_id"],
            "case_id": row["case_id"],
            "case_signature": row["case_signature"],
            "status": "pending",
            "error_code": "",
            "error_message": "",
            "created_at": created_at,
            "updated_at": created_at,
        }
        for row in manifest_rows
    ]


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
    run_root_dir: str | Path = "var/research_runs",
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

    run_dir = Path(run_root_dir) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    periods_copy_path = run_dir / "periods.csv"
    grids_copy_path = run_dir / "grids.csv"
    manifest_path = run_dir / "manifest.csv"
    results_index_path = run_dir / "results_index.csv"
    metadata_path = run_dir / "metadata.json"

    shutil.copyfile(Path(periods_csv_path), periods_copy_path)
    shutil.copyfile(Path(grids_csv_path), grids_copy_path)
    _write_csv(manifest_path, MANIFEST_COLUMNS, manifest_rows)
    _write_csv(results_index_path, RESULTS_INDEX_COLUMNS, results_index_rows)

    metadata = {
        "run_id": resolved_run_id,
        "created_at": created_at_text,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "periods_file_name": periods_copy_path.name,
        "grids_file_name": grids_copy_path.name,
        "period_row_count": len(period_rows),
        "grid_row_count": len(grid_rows),
        "eligible_grid_row_count": len(eligible_grid_rows),
        "manifest_case_count": len(manifest_rows),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return ResearchManifestRun(
        run_id=resolved_run_id,
        run_dir=run_dir,
        periods_copy_path=periods_copy_path,
        grids_copy_path=grids_copy_path,
        manifest_path=manifest_path,
        results_index_path=results_index_path,
        metadata_path=metadata_path,
        period_row_count=len(period_rows),
        grid_row_count=len(grid_rows),
        eligible_grid_row_count=len(eligible_grid_rows),
        manifest_case_count=len(manifest_rows),
    )
