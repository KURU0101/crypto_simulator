from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path


def _require_dict(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")
    return dict(value)


def _require_non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def _require_optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_string(value, name)


def _require_finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{name} must be finite")
    return numeric_value


def _require_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def normalize_symbol_for_external_signal(symbol: str) -> str:
    normalized = "".join(character for character in symbol.upper() if character.isalnum())
    if not normalized:
        raise ValueError("symbol must contain at least one alphanumeric character")
    return normalized


def normalize_topic(topic: str) -> str:
    parts = topic.strip().split()
    if not parts:
        raise ValueError("topic must be a non-empty string")
    return " ".join(parts).lower()


def normalize_timestamp_to_utc_z(value: object, name: str) -> str:
    timestamp = _require_non_empty_string(value, name)
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_or_ndjson(path: str | Path) -> list[dict]:
    input_path = Path(path)
    content = input_path.read_text(encoding="utf-8")
    stripped = content.strip()
    if not stripped:
        raise ValueError("input file must not be empty")

    if input_path.suffix.lower() == ".ndjson":
        records: list[dict] = []
        for index, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {index}") from error
            records.append(_require_dict(record, f"record[{index - 1}]"))
        if not records:
            raise ValueError("input file must include at least one record")
        return records

    payload = json.loads(content)
    if not isinstance(payload, list):
        raise ValueError("input file must contain a JSON array")
    return [_require_dict(record, f"record[{index}]") for index, record in enumerate(payload)]


__all__ = [
    "load_json_or_ndjson",
    "normalize_symbol_for_external_signal",
    "normalize_timestamp_to_utc_z",
    "normalize_topic",
    "_require_finite_number",
    "_require_non_empty_string",
    "_require_non_negative_int",
    "_require_optional_string",
]
