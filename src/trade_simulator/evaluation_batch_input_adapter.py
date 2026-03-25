from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable, Iterator

from trade_simulator.evaluation_batch_runner import DEFAULT_CASE_CHUNK_SIZE


PERIODS_CSV_REQUIRED_COLUMNS = (
    "period_id",
    "source",
    "symbol",
    "interval",
    "start",
    "end",
)

GRIDS_CSV_REQUIRED_COLUMNS = (
    "grid_id",
    "template_name",
    "overrides_json",
)


def _read_csv_rows(csv_path: str | Path, *, required_columns: tuple[str, ...], entity_name: str) -> list[dict[str, str]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{entity_name} csv must include a header")
        missing_columns = [column for column in required_columns if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"{entity_name} csv missing required columns: {', '.join(missing_columns)}")
        return [{str(key): "" if value is None else str(value) for key, value in row.items()} for row in reader]


def _iter_csv_rows(csv_path: str | Path, *, required_columns: tuple[str, ...], entity_name: str) -> Iterator[dict[str, str]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{entity_name} csv must include a header")
        missing_columns = [column for column in required_columns if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"{entity_name} csv missing required columns: {', '.join(missing_columns)}")
        for row in reader:
            yield {str(key): "" if value is None else str(value) for key, value in row.items()}


def _parse_required_text(row: dict[str, str], field_name: str, *, entity_name: str) -> str:
    value = row.get(field_name, "").strip()
    if not value:
        raise ValueError(f"{entity_name} {field_name} must be a non-empty string")
    return value


def _parse_optional_text(row: dict[str, str], field_name: str) -> str:
    return row.get(field_name, "").strip()


def _parse_optional_bool(row: dict[str, str], field_name: str, *, default: bool) -> bool:
    raw_value = row.get(field_name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes"}:
        return True
    if raw_value in {"0", "false", "no"}:
        return False
    raise ValueError(f"{field_name} must be a boolean-like string")


def _validate_non_negative_int(value: object, name: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int")
    return value


def load_batch_input_adapter_config(config: object) -> dict[str, object]:
    if not isinstance(config, dict):
        raise ValueError("batch input adapter config must be a dict")
    input_config = config.get("input")
    if not isinstance(input_config, dict):
        raise ValueError("batch input adapter config must include input")
    execution_config = config.get("execution")
    if not isinstance(execution_config, dict):
        raise ValueError("batch input adapter config must include execution")

    periods_csv_path = _parse_required_text(input_config, "periods_csv_path", entity_name="input")
    case_templates_json_path = _parse_required_text(input_config, "case_templates_json_path", entity_name="input")
    grids_csv_path = _parse_required_text(input_config, "grids_csv_path", entity_name="input")
    output_csv_path = _parse_required_text(execution_config, "output_csv_path", entity_name="execution")

    return {
        "periods_csv_path": periods_csv_path,
        "case_templates_json_path": case_templates_json_path,
        "grids_csv_path": grids_csv_path,
        "period_limit": _validate_non_negative_int(input_config.get("period_limit"), "period_limit"),
        "case_limit": _validate_non_negative_int(input_config.get("case_limit"), "case_limit"),
        "output_csv_path": output_csv_path,
        "results_db_path": execution_config.get("results_db_path"),
        "cache_root": str(execution_config.get("cache_root", "var/cache/market_data/ohlcv")),
        "shared_state_db_path": str(execution_config.get("shared_state_db_path", "var/cache/market_data/shared_state.sqlite3")),
        "case_chunk_size": _validate_positive_int(
            execution_config.get("case_chunk_size", DEFAULT_CASE_CHUNK_SIZE),
            "case_chunk_size",
        ),
        "dry_run": bool(execution_config.get("dry_run", False)),
    }


def load_periods_from_csv(csv_path: str | Path, *, period_limit: int | None = None) -> list[dict[str, str]]:
    rows = _read_csv_rows(csv_path, required_columns=PERIODS_CSV_REQUIRED_COLUMNS, entity_name="periods")
    normalized_rows: list[dict[str, str]] = []
    seen_period_ids: set[str] = set()
    for index, row in enumerate(rows):
        if period_limit is not None and len(normalized_rows) >= period_limit:
            break
        normalized_row = {
            "period_id": _parse_required_text(row, "period_id", entity_name=f"periods[{index}]"),
            "source": _parse_required_text(row, "source", entity_name=f"periods[{index}]"),
            "symbol": _parse_required_text(row, "symbol", entity_name=f"periods[{index}]"),
            "interval": _parse_required_text(row, "interval", entity_name=f"periods[{index}]"),
            "start": _parse_required_text(row, "start", entity_name=f"periods[{index}]"),
            "end": _parse_required_text(row, "end", entity_name=f"periods[{index}]"),
            "period_signature": _parse_optional_text(row, "period_signature"),
        }
        if normalized_row["period_id"] in seen_period_ids:
            raise ValueError(f"period_id must be unique: {normalized_row['period_id']}")
        seen_period_ids.add(normalized_row["period_id"])
        normalized_rows.append(normalized_row)
    if not normalized_rows:
        raise ValueError("periods csv must produce at least one row")
    return normalized_rows


def load_case_templates_json(json_path: str | Path) -> dict[str, dict]:
    path = Path(json_path)
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("case templates json must be a list")
    templates: dict[str, dict] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"case_templates[{index}] must be a dict")
        template_name = str(item.get("template_name", "")).strip()
        if not template_name:
            raise ValueError(f"case_templates[{index}].template_name must be a non-empty string")
        if template_name in templates:
            raise ValueError(f"template_name must be unique: {template_name}")
        case_payload = item.get("case")
        if not isinstance(case_payload, dict):
            raise ValueError(f"case_templates[{index}].case must be a dict")
        templates[template_name] = dict(case_payload)
    if not templates:
        raise ValueError("case templates json must not be empty")
    return templates


def _iter_grid_rows(csv_path: str | Path) -> Iterator[dict[str, str]]:
    yield from _iter_csv_rows(csv_path, required_columns=GRIDS_CSV_REQUIRED_COLUMNS, entity_name="grids")


def _build_case_name(*, template_name: str, grid_id: str) -> str:
    return f"{template_name}__{grid_id}"


def _build_case_from_template_and_grid(
    *,
    case_templates: dict[str, dict],
    grid_row: dict[str, str],
) -> dict[str, object] | None:
    if not _parse_optional_bool(grid_row, "enabled", default=True):
        return None
    template_name = _parse_required_text(grid_row, "template_name", entity_name="grid")
    if template_name not in case_templates:
        raise ValueError(f"grid template_name not found: {template_name}")
    grid_id = _parse_required_text(grid_row, "grid_id", entity_name="grid")
    overrides_text = _parse_required_text(grid_row, "overrides_json", entity_name="grid")
    try:
        overrides = json.loads(overrides_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"grid overrides_json must be valid JSON: {grid_id}") from exc
    if not isinstance(overrides, dict):
        raise ValueError(f"grid overrides_json must decode to an object: {grid_id}")
    if "name" in overrides or "simulation_name" in overrides:
        raise ValueError(f"grid overrides_json must not override name/simulation_name: {grid_id}")

    generated_case = dict(case_templates[template_name])
    generated_case.update(overrides)
    generated_name = _build_case_name(template_name=template_name, grid_id=grid_id)
    generated_case["name"] = generated_name
    if "simulation_name" not in generated_case:
        generated_case["simulation_name"] = generated_name
    generated_case["_template_name"] = template_name
    generated_case["_grid_id"] = grid_id
    return generated_case


def count_generated_cases(
    *,
    case_templates: dict[str, dict],
    grids_csv_path: str | Path,
    case_limit: int | None = None,
) -> int:
    count = 0
    seen_case_names: set[str] = set()
    for grid_row in _iter_grid_rows(grids_csv_path):
        generated_case = _build_case_from_template_and_grid(case_templates=case_templates, grid_row=grid_row)
        if generated_case is None:
            continue
        case_name = str(generated_case["name"])
        if case_name in seen_case_names:
            raise ValueError(f"generated case_name must be unique: {case_name}")
        seen_case_names.add(case_name)
        count += 1
        if case_limit is not None and count >= case_limit:
            break
    if count == 0:
        raise ValueError("grids input must produce at least one enabled case")
    return count


def build_generated_case_iterator_factory(
    *,
    case_templates: dict[str, dict],
    grids_csv_path: str | Path,
    case_limit: int | None = None,
) -> Callable[[], Iterator[dict[str, object]]]:
    def iterator() -> Iterator[dict[str, object]]:
        yielded = 0
        seen_case_names: set[str] = set()
        for grid_row in _iter_grid_rows(grids_csv_path):
            generated_case = _build_case_from_template_and_grid(case_templates=case_templates, grid_row=grid_row)
            if generated_case is None:
                continue
            case_name = str(generated_case["name"])
            if case_name in seen_case_names:
                raise ValueError(f"generated case_name must be unique: {case_name}")
            seen_case_names.add(case_name)
            yield generated_case
            yielded += 1
            if case_limit is not None and yielded >= case_limit:
                return

    return iterator


def resolve_batch_execution_inputs(config: dict[str, object]) -> dict[str, object]:
    periods = load_periods_from_csv(
        config["periods_csv_path"],
        period_limit=config["period_limit"],
    )
    case_templates = load_case_templates_json(config["case_templates_json_path"])
    total_cases = count_generated_cases(
        case_templates=case_templates,
        grids_csv_path=config["grids_csv_path"],
        case_limit=config["case_limit"],
    )
    case_iterator_factory = build_generated_case_iterator_factory(
        case_templates=case_templates,
        grids_csv_path=config["grids_csv_path"],
        case_limit=config["case_limit"],
    )
    return {
        "periods": periods,
        "total_cases": total_cases,
        "case_iterator_factory": case_iterator_factory,
        "output_csv_path": config["output_csv_path"],
        "results_db_path": config["results_db_path"],
        "cache_root": config["cache_root"],
        "shared_state_db_path": config["shared_state_db_path"],
        "case_chunk_size": config["case_chunk_size"],
        "dry_run": config["dry_run"],
        "config_fingerprint_payload": {
            "input": {
                "periods_csv_path": config["periods_csv_path"],
                "case_templates_json_path": config["case_templates_json_path"],
                "grids_csv_path": config["grids_csv_path"],
                "period_limit": config["period_limit"],
                "case_limit": config["case_limit"],
            },
            "execution": {
                "output_csv_path": config["output_csv_path"],
                "results_db_path": config["results_db_path"],
                "cache_root": config["cache_root"],
                "shared_state_db_path": config["shared_state_db_path"],
                "case_chunk_size": config["case_chunk_size"],
                "dry_run": config["dry_run"],
            },
        },
    }
