from __future__ import annotations

import csv
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trade_simulator.data.ohlcv import REQUIRED_OHLCV_COLUMNS, load_ohlcv_csv, normalize_ohlcv_rows
from trade_simulator.data.sources import normalize_symbol
from trade_simulator.live_decision_runner import BINANCE_SPOT_KLINES_URL

from ._evaluation_market_data_shared_state import (
    DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH,
    MARKET_DATA_STATUS_COMPLETED,
    find_market_data_acquisition,
    mark_market_data_acquisition_completed,
    mark_market_data_acquisition_failed,
    mark_market_data_acquisition_running,
)


MARKET_DATA_SCHEMA_VERSION = "market_data_acquisition_v1"
DEFAULT_MARKET_DATA_CACHE_ROOT = Path("var/cache/market_data/ohlcv")
PRIMARY_ARTIFACT_KIND = "ohlcv_csv"
SUPPORTED_MARKET_DATA_SOURCES = ("binance_spot",)


class MarketDataEvaluationError(Exception):
    """Base exception for evaluation market data failures."""


class MarketDataFetchError(MarketDataEvaluationError):
    """Raised when market data fetching fails."""


class MarketDataArtifactValidationError(MarketDataEvaluationError):
    """Raised when a saved market data artifact is invalid."""


def _validate_non_empty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _parse_utc_iso8601(value: str, name: str) -> datetime:
    normalized = _validate_non_empty_text(value, name).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError as error:
        raise ValueError(f"{name} must be ISO 8601") from error


def build_market_data_acquisition_key(
    *,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    schema_version: str = MARKET_DATA_SCHEMA_VERSION,
) -> str:
    canonical_payload = {
        "source": _validate_non_empty_text(source, "source"),
        "symbol": _validate_non_empty_text(symbol, "symbol"),
        "interval": _validate_non_empty_text(interval, "interval"),
        "window_start": _validate_non_empty_text(window_start, "window_start"),
        "window_end": _validate_non_empty_text(window_end, "window_end"),
        "schema_version": _validate_non_empty_text(schema_version, "schema_version"),
    }
    canonical_text = json.dumps(canonical_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def build_market_data_artifact_path(
    *,
    cache_root: str | Path,
    source: str,
    symbol: str,
    acquisition_key: str,
) -> Path:
    return Path(cache_root) / source / normalize_symbol(symbol) / f"{acquisition_key}.csv"


def fetch_binance_spot_klines_range(
    *,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict[str, object]]:
    if urlopen_fn is None:
        urlopen_fn = urllib.request.urlopen
    start_dt = _parse_utc_iso8601(window_start, "window_start")
    end_dt = _parse_utc_iso8601(window_end, "window_end")
    if end_dt <= start_dt:
        raise ValueError("window_end must be later than window_start")

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    rows: list[dict[str, object]] = []

    while start_ms < end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": _validate_non_empty_text(symbol, "symbol"),
                "interval": _validate_non_empty_text(interval, "interval"),
                "limit": 1000,
                "startTime": start_ms,
                "endTime": end_ms,
            }
        )
        request = urllib.request.Request(f"{BINANCE_SPOT_KLINES_URL}?{query}", method="GET")
        try:
            with urlopen_fn(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            message = f"failed to fetch klines: HTTP {error.code}"
            if body:
                message = f"{message}: {body}"
            raise MarketDataFetchError(message) from error
        except urllib.error.URLError as error:
            raise MarketDataFetchError(f"failed to fetch klines: {error.reason}") from error
        except TimeoutError as error:
            raise MarketDataFetchError("failed to fetch klines: timeout") from error
        except json.JSONDecodeError as error:
            raise MarketDataFetchError("failed to decode klines response as JSON") from error

        if not isinstance(payload, list):
            raise MarketDataFetchError("kline response must be a list")
        if not payload:
            break

        for item in payload:
            if not isinstance(item, list) or len(item) < 6:
                raise MarketDataFetchError("kline response item must be a list with at least 6 elements")
            open_time_ms = int(item[0])
            rows.append(
                {
                    "timestamp": datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume": item[5],
                }
            )

        last_open_time_ms = int(payload[-1][0])
        next_start_ms = last_open_time_ms + 1
        if next_start_ms <= start_ms:
            break
        start_ms = next_start_ms
        if len(payload) < 1000:
            break

    return normalize_ohlcv_rows(rows)


def fetch_historical_ohlcv(
    *,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
) -> list[dict[str, object]]:
    if source != "binance_spot":
        raise ValueError(f"source must be one of: {', '.join(SUPPORTED_MARKET_DATA_SOURCES)}")
    return fetch_binance_spot_klines_range(
        symbol=symbol,
        interval=interval,
        window_start=window_start,
        window_end=window_end,
    )


def save_normalized_ohlcv_csv(rows: list[dict[str, object]], csv_path: str | Path) -> Path:
    normalized_rows = normalize_ohlcv_rows(rows)
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(REQUIRED_OHLCV_COLUMNS))
        writer.writeheader()
        for row in normalized_rows:
            writer.writerow({column: row[column] for column in REQUIRED_OHLCV_COLUMNS})
    return path


def validate_saved_ohlcv_artifact(csv_path: str | Path) -> list[dict]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise MarketDataArtifactValidationError("OHLCV csv must include a header")
        missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in reader.fieldnames]
        if missing_columns:
            raise MarketDataArtifactValidationError(
                f"missing required OHLCV columns: {', '.join(missing_columns)}"
            )
        rows = [dict(row) for row in reader]

    if not rows:
        raise MarketDataArtifactValidationError("saved OHLCV csv must not be empty")

    previous_timestamp: datetime | None = None
    for index, row in enumerate(rows):
        raw_timestamp = row.get("timestamp")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            raise MarketDataArtifactValidationError(f"timestamp is required at row {index}")
        try:
            parsed_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as error:
            raise MarketDataArtifactValidationError(f"timestamp must be ISO 8601 at row {index}") from error
        if previous_timestamp is not None and parsed_timestamp <= previous_timestamp:
            raise MarketDataArtifactValidationError("saved OHLCV timestamps must be strictly increasing")
        previous_timestamp = parsed_timestamp

    return load_ohlcv_csv(path)


def resolve_evaluation_market_data(
    *,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    cache_root: str | Path = DEFAULT_MARKET_DATA_CACHE_ROOT,
    shared_state_db_path: str | Path = DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH,
    schema_version: str = MARKET_DATA_SCHEMA_VERSION,
    period_signature: str = "",
    fetcher: Callable[..., list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    source_text = _validate_non_empty_text(source, "source")
    symbol_text = _validate_non_empty_text(symbol, "symbol")
    interval_text = _validate_non_empty_text(interval, "interval")
    window_start_text = _validate_non_empty_text(window_start, "window_start")
    window_end_text = _validate_non_empty_text(window_end, "window_end")
    _parse_utc_iso8601(window_start_text, "window_start")
    _parse_utc_iso8601(window_end_text, "window_end")

    acquisition_key = build_market_data_acquisition_key(
        source=source_text,
        symbol=symbol_text,
        interval=interval_text,
        window_start=window_start_text,
        window_end=window_end_text,
        schema_version=schema_version,
    )
    artifact_path = build_market_data_artifact_path(
        cache_root=cache_root,
        source=source_text,
        symbol=symbol_text,
        acquisition_key=acquisition_key,
    )
    existing = find_market_data_acquisition(shared_state_db_path, acquisition_key=acquisition_key)
    if existing is not None and existing["status"] == MARKET_DATA_STATUS_COMPLETED and existing["artifact_path"]:
        try:
            rows = validate_saved_ohlcv_artifact(existing["artifact_path"])
        except MarketDataArtifactValidationError:
            mark_market_data_acquisition_failed(
                shared_state_db_path,
                acquisition_key=acquisition_key,
                source=source_text,
                symbol=symbol_text,
                interval=interval_text,
                window_start=window_start_text,
                window_end=window_end_text,
                schema_version=schema_version,
                last_error_code="artifact_validation_error",
                period_signature=period_signature,
            )
        else:
            return {
                "acquisition_key": acquisition_key,
                "source": source_text,
                "symbol": symbol_text,
                "interval": interval_text,
                "window_start": window_start_text,
                "window_end": window_end_text,
                "schema_version": schema_version,
                "status": MARKET_DATA_STATUS_COMPLETED,
                "reused_existing_artifact": True,
                "fetched": False,
                "artifact_path": str(Path(existing["artifact_path"])),
                "artifact_kind": PRIMARY_ARTIFACT_KIND,
                "row_count": len(rows),
                "rows": rows,
            }

    mark_market_data_acquisition_running(
        shared_state_db_path,
        acquisition_key=acquisition_key,
        source=source_text,
        symbol=symbol_text,
        interval=interval_text,
        window_start=window_start_text,
        window_end=window_end_text,
        schema_version=schema_version,
        period_signature=period_signature,
    )
    active_fetcher = fetcher or fetch_historical_ohlcv
    try:
        fetched_rows = active_fetcher(
            source=source_text,
            symbol=symbol_text,
            interval=interval_text,
            window_start=window_start_text,
            window_end=window_end_text,
        )
        save_normalized_ohlcv_csv(fetched_rows, artifact_path)
        validated_rows = validate_saved_ohlcv_artifact(artifact_path)
    except Exception as error:
        mark_market_data_acquisition_failed(
            shared_state_db_path,
            acquisition_key=acquisition_key,
            source=source_text,
            symbol=symbol_text,
            interval=interval_text,
            window_start=window_start_text,
            window_end=window_end_text,
            schema_version=schema_version,
            last_error_code=type(error).__name__,
            period_signature=period_signature,
        )
        raise

    mark_market_data_acquisition_completed(
        shared_state_db_path,
        acquisition_key=acquisition_key,
        source=source_text,
        symbol=symbol_text,
        interval=interval_text,
        window_start=window_start_text,
        window_end=window_end_text,
        schema_version=schema_version,
        artifact_path=str(artifact_path),
        artifact_kind=PRIMARY_ARTIFACT_KIND,
        period_signature=period_signature,
    )
    return {
        "acquisition_key": acquisition_key,
        "source": source_text,
        "symbol": symbol_text,
        "interval": interval_text,
        "window_start": window_start_text,
        "window_end": window_end_text,
        "schema_version": schema_version,
        "status": MARKET_DATA_STATUS_COMPLETED,
        "reused_existing_artifact": False,
        "fetched": True,
        "artifact_path": str(artifact_path),
        "artifact_kind": PRIMARY_ARTIFACT_KIND,
        "row_count": len(validated_rows),
        "rows": validated_rows,
    }
