from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH = Path("var/cache/market_data/shared_state.sqlite3")
MARKET_DATA_SHARED_STATE_SCHEMA_VERSION = "market_data_shared_state_v1"
MARKET_DATA_STATUS_RUNNING = "running"
MARKET_DATA_STATUS_COMPLETED = "completed"
MARKET_DATA_STATUS_FAILED = "failed"
MARKET_DATA_STATUS_VALUES = (
    MARKET_DATA_STATUS_RUNNING,
    MARKET_DATA_STATUS_COMPLETED,
    MARKET_DATA_STATUS_FAILED,
)
MARKET_DATA_SHARED_STATE_COLUMNS = (
    "acquisition_key",
    "source",
    "symbol",
    "interval",
    "window_start",
    "window_end",
    "schema_version",
    "status",
    "created_at",
    "updated_at",
    "artifact_path",
    "artifact_kind",
    "last_error_code",
    "period_signature",
)


def _connect_market_data_shared_state_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_status(status: str) -> str:
    if status not in MARKET_DATA_STATUS_VALUES:
        raise ValueError(f"status must be one of: {', '.join(MARKET_DATA_STATUS_VALUES)}")
    return status


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    normalized = {
        "acquisition_key": str(row["acquisition_key"]),
        "source": str(row["source"]),
        "symbol": str(row["symbol"]),
        "interval": str(row["interval"]),
        "window_start": str(row["window_start"]),
        "window_end": str(row["window_end"]),
        "schema_version": str(row["schema_version"]),
        "status": _validate_status(str(row["status"])),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "artifact_path": str(row.get("artifact_path", "")),
        "artifact_kind": str(row.get("artifact_kind", "")),
        "last_error_code": str(row.get("last_error_code", "")),
        "period_signature": str(row.get("period_signature", "")),
    }
    for key in ("acquisition_key", "source", "symbol", "interval", "window_start", "window_end", "schema_version"):
        if not normalized[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    return normalized


def initialize_market_data_shared_state_db(
    db_path: str | Path = DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH,
) -> Path:
    path = Path(db_path)
    with _connect_market_data_shared_state_db(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_data_shared_state_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_data_acquisitions (
                acquisition_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                artifact_path TEXT NOT NULL DEFAULT '',
                artifact_kind TEXT NOT NULL DEFAULT '',
                last_error_code TEXT NOT NULL DEFAULT '',
                period_signature TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            INSERT INTO market_data_shared_state_meta(key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (MARKET_DATA_SHARED_STATE_SCHEMA_VERSION,),
        )
        connection.commit()
    return path


def get_market_data_shared_state_schema_version(
    db_path: str | Path = DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH,
) -> str:
    path = initialize_market_data_shared_state_db(db_path)
    with _connect_market_data_shared_state_db(path) as connection:
        row = connection.execute(
            "SELECT value FROM market_data_shared_state_meta WHERE key = 'schema_version'"
        ).fetchone()
    if row is None:
        raise ValueError("market_data_shared_state_meta must include schema_version")
    schema_version = str(row["value"])
    if schema_version != MARKET_DATA_SHARED_STATE_SCHEMA_VERSION:
        raise ValueError(f"market data shared state schema_version must be {MARKET_DATA_SHARED_STATE_SCHEMA_VERSION}")
    return schema_version


def find_market_data_acquisition(
    db_path: str | Path = DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH,
    *,
    acquisition_key: str,
) -> dict[str, str] | None:
    path = initialize_market_data_shared_state_db(db_path)
    get_market_data_shared_state_schema_version(path)
    with _connect_market_data_shared_state_db(path) as connection:
        row = connection.execute(
            f"""
            SELECT {', '.join(MARKET_DATA_SHARED_STATE_COLUMNS)}
            FROM market_data_acquisitions
            WHERE acquisition_key = ?
            """,
            (acquisition_key,),
        ).fetchone()
    if row is None:
        return None
    return _normalize_row({column: row[column] for column in MARKET_DATA_SHARED_STATE_COLUMNS})


def _upsert_market_data_acquisition(
    db_path: str | Path,
    *,
    acquisition_key: str,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    schema_version: str,
    status: str,
    artifact_path: str,
    artifact_kind: str,
    last_error_code: str,
    period_signature: str,
) -> dict[str, str]:
    path = initialize_market_data_shared_state_db(db_path)
    get_market_data_shared_state_schema_version(path)
    existing = find_market_data_acquisition(path, acquisition_key=acquisition_key)
    timestamp = _utc_now_text()
    created_at = timestamp if existing is None else existing["created_at"]
    row = _normalize_row(
        {
            "acquisition_key": acquisition_key,
            "source": source,
            "symbol": symbol,
            "interval": interval,
            "window_start": window_start,
            "window_end": window_end,
            "schema_version": schema_version,
            "status": status,
            "created_at": created_at,
            "updated_at": timestamp,
            "artifact_path": artifact_path,
            "artifact_kind": artifact_kind,
            "last_error_code": last_error_code,
            "period_signature": period_signature,
        }
    )
    with _connect_market_data_shared_state_db(path) as connection:
        connection.execute(
            f"""
            INSERT INTO market_data_acquisitions (
                {', '.join(MARKET_DATA_SHARED_STATE_COLUMNS)}
            )
            VALUES ({', '.join('?' for _ in MARKET_DATA_SHARED_STATE_COLUMNS)})
            ON CONFLICT(acquisition_key) DO UPDATE SET
                source=excluded.source,
                symbol=excluded.symbol,
                interval=excluded.interval,
                window_start=excluded.window_start,
                window_end=excluded.window_end,
                schema_version=excluded.schema_version,
                status=excluded.status,
                updated_at=excluded.updated_at,
                artifact_path=excluded.artifact_path,
                artifact_kind=excluded.artifact_kind,
                last_error_code=excluded.last_error_code,
                period_signature=excluded.period_signature
            """,
            tuple(row[column] for column in MARKET_DATA_SHARED_STATE_COLUMNS),
        )
        connection.commit()
    return find_market_data_acquisition(path, acquisition_key=acquisition_key)  # type: ignore[return-value]


def mark_market_data_acquisition_running(
    db_path: str | Path,
    *,
    acquisition_key: str,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    schema_version: str,
    period_signature: str = "",
) -> dict[str, str]:
    return _upsert_market_data_acquisition(
        db_path,
        acquisition_key=acquisition_key,
        source=source,
        symbol=symbol,
        interval=interval,
        window_start=window_start,
        window_end=window_end,
        schema_version=schema_version,
        status=MARKET_DATA_STATUS_RUNNING,
        artifact_path="",
        artifact_kind="",
        last_error_code="",
        period_signature=period_signature,
    )


def mark_market_data_acquisition_completed(
    db_path: str | Path,
    *,
    acquisition_key: str,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    schema_version: str,
    artifact_path: str,
    artifact_kind: str,
    period_signature: str = "",
) -> dict[str, str]:
    return _upsert_market_data_acquisition(
        db_path,
        acquisition_key=acquisition_key,
        source=source,
        symbol=symbol,
        interval=interval,
        window_start=window_start,
        window_end=window_end,
        schema_version=schema_version,
        status=MARKET_DATA_STATUS_COMPLETED,
        artifact_path=artifact_path,
        artifact_kind=artifact_kind,
        last_error_code="",
        period_signature=period_signature,
    )


def mark_market_data_acquisition_failed(
    db_path: str | Path,
    *,
    acquisition_key: str,
    source: str,
    symbol: str,
    interval: str,
    window_start: str,
    window_end: str,
    schema_version: str,
    last_error_code: str,
    period_signature: str = "",
) -> dict[str, str]:
    return _upsert_market_data_acquisition(
        db_path,
        acquisition_key=acquisition_key,
        source=source,
        symbol=symbol,
        interval=interval,
        window_start=window_start,
        window_end=window_end,
        schema_version=schema_version,
        status=MARKET_DATA_STATUS_FAILED,
        artifact_path="",
        artifact_kind="",
        last_error_code=last_error_code,
        period_signature=period_signature,
    )
