from __future__ import annotations

import csv
import math
from datetime import datetime
from numbers import Real
from pathlib import Path


REQUIRED_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def _parse_timestamp(value: object, row_index: int) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"timestamp is required at row {row_index}")

    timestamp = value.strip()
    normalized = timestamp.replace("Z", "+00:00")

    try:
        parsed_timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"timestamp must be ISO 8601 at row {row_index}") from error

    return timestamp, parsed_timestamp


def _parse_numeric(value: object, name: str, row_index: int) -> float:
    if isinstance(value, bool) or isinstance(value, Real):
        numeric_value = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            numeric_value = float(value)
        except ValueError as error:
            raise TypeError(f"{name} must be numeric at row {row_index}") from error
    else:
        raise TypeError(f"{name} must be numeric at row {row_index}")

    if not math.isfinite(numeric_value):
        raise ValueError(f"{name} must be finite at row {row_index}")

    return numeric_value


def _normalize_ohlcv_row(row: object, row_index: int) -> dict:
    if not isinstance(row, dict):
        raise TypeError(f"ohlcv_rows[{row_index}] must be a dict")

    missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in row]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"missing required OHLCV columns: {missing}")

    timestamp, parsed_timestamp = _parse_timestamp(row["timestamp"], row_index)
    normalized_row = {
        "timestamp": timestamp,
        "timestamp_sort_key": parsed_timestamp,
    }

    for column in REQUIRED_OHLCV_COLUMNS[1:]:
        normalized_row[column] = _parse_numeric(row[column], column, row_index)

    if normalized_row["close"] <= 0:
        raise ValueError(f"close must be greater than 0 at row {row_index}")

    return normalized_row


def normalize_ohlcv_rows(ohlcv_rows: object) -> list[dict]:
    if not isinstance(ohlcv_rows, list):
        raise TypeError("ohlcv_rows must be a list")
    if not ohlcv_rows:
        raise ValueError("ohlcv_rows must not be empty")

    normalized_rows = [_normalize_ohlcv_row(row, index) for index, row in enumerate(ohlcv_rows)]
    normalized_rows.sort(key=lambda row: row["timestamp_sort_key"])

    for index in range(1, len(normalized_rows)):
        if normalized_rows[index]["timestamp"] == normalized_rows[index - 1]["timestamp"]:
            raise ValueError("timestamp must be unique")

    return normalized_rows


def load_ohlcv_csv(csv_path: str | Path) -> list[dict]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("OHLCV csv must include a header")

        missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in reader.fieldnames]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"missing required OHLCV columns: {missing}")

        rows = [dict(row) for row in reader]

    return normalize_ohlcv_rows(rows)


def build_close_to_close_returns(ohlcv_rows: object) -> dict:
    normalized_rows = normalize_ohlcv_rows(ohlcv_rows)

    returns = []
    return_timestamps = []

    for previous_row, current_row in zip(normalized_rows, normalized_rows[1:]):
        period_return = (current_row["close"] / previous_row["close"]) - 1.0
        returns.append(period_return)
        return_timestamps.append(current_row["timestamp"])

    return {
        "price_basis": "close_to_close",
        "timestamps": [row["timestamp"] for row in normalized_rows],
        "return_timestamps": return_timestamps,
        "returns": returns,
    }


def load_returns_from_ohlcv_csv(csv_path: str | Path) -> dict:
    ohlcv_rows = load_ohlcv_csv(csv_path)
    return build_close_to_close_returns(ohlcv_rows)
