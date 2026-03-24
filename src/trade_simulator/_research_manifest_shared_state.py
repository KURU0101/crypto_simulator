from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from ._research_manifest_common import (
    CACHE_KEY_VERSION,
    DEFAULT_SHARED_STATE_DB_PATH,
    RESULT_STATUS_COMPLETED,
    RESULT_STATUS_FAILED,
    RESULT_STATUS_PENDING,
    RESULT_STATUS_RUNNING,
    SHARED_CACHE_ENTRY_COLUMNS,
    SHARED_STATE_SCHEMA_VERSION,
    _connect_shared_state_db,
    _parse_bool_flag_text,
    _parse_iso_datetime_text,
    _parse_non_negative_integer_text,
    _parse_required_text,
    _render_utc_datetime,
    _strip_and_validate_null_string,
    validate_acquisition_status,
    validate_source_family,
)


def _shared_cache_entries_table_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'shared_cache_entries'"
    ).fetchone()
    return row is not None


def _shared_cache_entry_column_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("PRAGMA table_info(shared_cache_entries)").fetchall()
    return {str(row["name"]) for row in rows}


def _migrate_shared_state_db_v1_to_v2(connection: sqlite3.Connection) -> None:
    existing_columns = _shared_cache_entry_column_names(connection)
    required_column_statements = {
        "claimed_at": "ALTER TABLE shared_cache_entries ADD COLUMN claimed_at TEXT NOT NULL DEFAULT ''",
        "claimed_by": "ALTER TABLE shared_cache_entries ADD COLUMN claimed_by TEXT NOT NULL DEFAULT ''",
        "lease_expires_at": "ALTER TABLE shared_cache_entries ADD COLUMN lease_expires_at TEXT NOT NULL DEFAULT ''",
        "last_heartbeat_at": "ALTER TABLE shared_cache_entries ADD COLUMN last_heartbeat_at TEXT NOT NULL DEFAULT ''",
        "auto_retry_count": "ALTER TABLE shared_cache_entries ADD COLUMN auto_retry_count INTEGER NOT NULL DEFAULT 0",
        "retryable": "ALTER TABLE shared_cache_entries ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0",
        "last_error_code": "ALTER TABLE shared_cache_entries ADD COLUMN last_error_code TEXT NOT NULL DEFAULT ''",
    }
    for column_name, statement in required_column_statements.items():
        if column_name in existing_columns:
            continue
        connection.execute(statement)
    connection.execute(
        """
        INSERT INTO shared_state_meta(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (SHARED_STATE_SCHEMA_VERSION,),
    )


def _ensure_shared_state_db_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_state_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    if not _shared_cache_entries_table_exists(connection):
        connection.execute(
            """
            CREATE TABLE shared_cache_entries (
                cache_key TEXT PRIMARY KEY,
                cache_key_version TEXT NOT NULL,
                source_family TEXT NOT NULL CHECK (source_family IN ('news', 'sns')),
                symbol TEXT NOT NULL,
                period_id TEXT NOT NULL,
                period_signature TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                claimed_at TEXT NOT NULL DEFAULT '',
                claimed_by TEXT NOT NULL DEFAULT '',
                lease_expires_at TEXT NOT NULL DEFAULT '',
                last_heartbeat_at TEXT NOT NULL DEFAULT '',
                auto_retry_count INTEGER NOT NULL DEFAULT 0 CHECK (auto_retry_count >= 0),
                retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
                last_error_code TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            INSERT INTO shared_state_meta(key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (SHARED_STATE_SCHEMA_VERSION,),
        )
        return

    schema_row = connection.execute(
        "SELECT value FROM shared_state_meta WHERE key = 'schema_version'"
    ).fetchone()
    if schema_row is None:
        existing_columns = _shared_cache_entry_column_names(connection)
        expected_columns = set(SHARED_CACHE_ENTRY_COLUMNS)
        if not expected_columns.issubset(existing_columns):
            _migrate_shared_state_db_v1_to_v2(connection)
            return
        connection.execute(
            """
            INSERT INTO shared_state_meta(key, value)
            VALUES ('schema_version', ?)
            """,
            (SHARED_STATE_SCHEMA_VERSION,),
        )
        return

    schema_version = str(schema_row["value"])
    if schema_version == "shared_state_v1":
        _migrate_shared_state_db_v1_to_v2(connection)
        return
    existing_columns = _shared_cache_entry_column_names(connection)
    expected_columns = set(SHARED_CACHE_ENTRY_COLUMNS)
    if not expected_columns.issubset(existing_columns):
        _migrate_shared_state_db_v1_to_v2(connection)
        return
    if schema_version != SHARED_STATE_SCHEMA_VERSION:
        return


def initialize_shared_state_db(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
) -> Path:
    path = Path(db_path)
    with _connect_shared_state_db(path) as connection:
        _ensure_shared_state_db_schema(connection)
        connection.commit()
    return path


def get_shared_state_schema_version(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
) -> str:
    path = initialize_shared_state_db(db_path)
    with _connect_shared_state_db(path) as connection:
        row = connection.execute(
            "SELECT value FROM shared_state_meta WHERE key = 'schema_version'"
        ).fetchone()
    if row is None:
        raise ValueError("shared_state_meta must include schema_version")
    schema_version = str(row["value"])
    if schema_version != SHARED_STATE_SCHEMA_VERSION:
        raise ValueError(f"shared state schema_version must be {SHARED_STATE_SCHEMA_VERSION}")
    return schema_version


def _normalize_shared_cache_entry(row: dict[str, str]) -> dict[str, str]:
    normalized_row = {
        "cache_key": _parse_required_text(row, "cache_key"),
        "cache_key_version": _parse_required_text(row, "cache_key_version"),
        "source_family": validate_source_family(_parse_required_text(row, "source_family")),
        "symbol": _parse_required_text(row, "symbol"),
        "period_id": _parse_required_text(row, "period_id"),
        "period_signature": _parse_required_text(row, "period_signature"),
        "status": validate_acquisition_status(_parse_required_text(row, "status")),
        "created_at": _parse_required_text(row, "created_at"),
        "updated_at": _parse_required_text(row, "updated_at"),
        "claimed_at": _strip_and_validate_null_string(row.get("claimed_at", ""), field_name="claimed_at"),
        "claimed_by": _strip_and_validate_null_string(row.get("claimed_by", ""), field_name="claimed_by"),
        "lease_expires_at": _strip_and_validate_null_string(row.get("lease_expires_at", ""), field_name="lease_expires_at"),
        "last_heartbeat_at": _strip_and_validate_null_string(
            row.get("last_heartbeat_at", ""),
            field_name="last_heartbeat_at",
        ),
        "auto_retry_count": _parse_non_negative_integer_text(row, "auto_retry_count"),
        "retryable": _parse_bool_flag_text(row, "retryable"),
        "last_error_code": _strip_and_validate_null_string(row.get("last_error_code", ""), field_name="last_error_code"),
    }
    if normalized_row["cache_key_version"] != CACHE_KEY_VERSION:
        raise ValueError(f"cache_key_version must be {CACHE_KEY_VERSION}")
    if normalized_row["claimed_at"]:
        _parse_iso_datetime_text(normalized_row["claimed_at"], field_name="claimed_at")
    if normalized_row["lease_expires_at"]:
        _parse_iso_datetime_text(normalized_row["lease_expires_at"], field_name="lease_expires_at")
    if normalized_row["last_heartbeat_at"]:
        _parse_iso_datetime_text(normalized_row["last_heartbeat_at"], field_name="last_heartbeat_at")
    if normalized_row["status"] == RESULT_STATUS_RUNNING:
        required_running_columns = ("claimed_at", "claimed_by", "lease_expires_at", "last_heartbeat_at")
        for column in required_running_columns:
            if not normalized_row[column]:
                raise ValueError(f"running shared_cache_entry must include {column}")
    else:
        forbidden_non_running_columns = ("claimed_at", "claimed_by", "lease_expires_at", "last_heartbeat_at")
        for column in forbidden_non_running_columns:
            if normalized_row[column]:
                raise ValueError(f"non-running shared_cache_entry must not include {column}")
    return normalized_row


def _find_shared_cache_entry_in_connection(
    connection: sqlite3.Connection,
    *,
    cache_key: str,
) -> dict[str, str] | None:
    row = connection.execute(
        f"""
        SELECT {', '.join(SHARED_CACHE_ENTRY_COLUMNS)}
        FROM shared_cache_entries
        WHERE cache_key = ?
        """,
        (cache_key,),
    ).fetchone()
    if row is None:
        return None
    return _normalize_shared_cache_entry(
        {column: "" if row[column] is None else str(row[column]) for column in SHARED_CACHE_ENTRY_COLUMNS}
    )


def _build_shared_cache_entry_row(
    *,
    cache_key: str,
    source_family: str,
    symbol: str,
    period_id: str,
    period_signature: str,
    status: str,
    created_at: str,
    updated_at: str,
    claimed_at: str = "",
    claimed_by: str = "",
    lease_expires_at: str = "",
    last_heartbeat_at: str = "",
    auto_retry_count: int | str = 0,
    retryable: bool | int | str = False,
    last_error_code: str = "",
) -> dict[str, str]:
    if isinstance(retryable, bool):
        retryable_value = "1" if retryable else "0"
    else:
        retryable_value = str(retryable)
    return _normalize_shared_cache_entry(
        {
            "cache_key": cache_key,
            "cache_key_version": CACHE_KEY_VERSION,
            "source_family": source_family,
            "symbol": symbol,
            "period_id": period_id,
            "period_signature": period_signature,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
            "claimed_at": claimed_at,
            "claimed_by": claimed_by,
            "lease_expires_at": lease_expires_at,
            "last_heartbeat_at": last_heartbeat_at,
            "auto_retry_count": str(auto_retry_count),
            "retryable": retryable_value,
            "last_error_code": last_error_code,
        }
    )


def _build_shared_cache_entry_state_row(
    existing_row: dict[str, str],
    *,
    next_status: str,
    state_changed_at: str,
    claimed_at: str = "",
    claimed_by: str = "",
    lease_expires_at: str = "",
    last_heartbeat_at: str = "",
    auto_retry_count: int | str | None = None,
    retryable: bool | int | str | None = None,
    last_error_code: str | None = None,
) -> dict[str, str]:
    # updated_at tracks the last time this shared-truth row changed. Liveness is derived from
    # lease_expires_at / last_heartbeat_at, so callers must not treat updated_at as a heartbeat.
    return _build_shared_cache_entry_row(
        cache_key=existing_row["cache_key"],
        source_family=existing_row["source_family"],
        symbol=existing_row["symbol"],
        period_id=existing_row["period_id"],
        period_signature=existing_row["period_signature"],
        status=next_status,
        created_at=existing_row["created_at"],
        updated_at=state_changed_at,
        claimed_at=claimed_at,
        claimed_by=claimed_by,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=last_heartbeat_at,
        auto_retry_count=existing_row["auto_retry_count"] if auto_retry_count is None else auto_retry_count,
        retryable=existing_row["retryable"] if retryable is None else retryable,
        last_error_code=existing_row["last_error_code"] if last_error_code is None else last_error_code,
    )


def _save_shared_cache_entry_in_connection(
    connection: sqlite3.Connection,
    row: dict[str, str],
) -> None:
    connection.execute(
        f"""
        INSERT INTO shared_cache_entries (
            {', '.join(SHARED_CACHE_ENTRY_COLUMNS)}
        )
        VALUES ({', '.join('?' for _ in SHARED_CACHE_ENTRY_COLUMNS)})
        ON CONFLICT(cache_key) DO UPDATE SET
            cache_key_version=excluded.cache_key_version,
            source_family=excluded.source_family,
            symbol=excluded.symbol,
            period_id=excluded.period_id,
            period_signature=excluded.period_signature,
            status=excluded.status,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            claimed_at=excluded.claimed_at,
            claimed_by=excluded.claimed_by,
            lease_expires_at=excluded.lease_expires_at,
            last_heartbeat_at=excluded.last_heartbeat_at,
            auto_retry_count=excluded.auto_retry_count,
            retryable=excluded.retryable,
            last_error_code=excluded.last_error_code
        """,
        tuple(row[column] for column in SHARED_CACHE_ENTRY_COLUMNS),
    )


def _compute_lease_expires_at(claimed_at: str, *, lease_duration_seconds: int) -> str:
    if lease_duration_seconds <= 0:
        raise ValueError("lease_duration_seconds must be greater than 0")
    claimed_at_dt = _parse_iso_datetime_text(claimed_at, field_name="claimed_at")
    return _render_utc_datetime(claimed_at_dt + timedelta(seconds=lease_duration_seconds))


def is_shared_cache_entry_stale(
    shared_cache_entry: dict[str, str],
    *,
    now: str | datetime,
) -> bool:
    # Staleness is lease-based. updated_at is only the last row-mutation timestamp and does not
    # decide whether a running worker still owns the entry.
    if shared_cache_entry["status"] != RESULT_STATUS_RUNNING:
        return False
    lease_expires_at = shared_cache_entry["lease_expires_at"]
    if not lease_expires_at:
        raise ValueError("running shared_cache_entry must include lease_expires_at")
    now_dt = now if isinstance(now, datetime) else _parse_iso_datetime_text(now, field_name="now")
    lease_expires_at_dt = _parse_iso_datetime_text(lease_expires_at, field_name="lease_expires_at")
    return lease_expires_at_dt < now_dt.astimezone(timezone.utc)


def _can_auto_retry_failed_entry(shared_cache_entry: dict[str, str]) -> bool:
    return (
        shared_cache_entry["status"] == RESULT_STATUS_FAILED
        and shared_cache_entry["retryable"] == "1"
        and shared_cache_entry["auto_retry_count"] == "0"
    )


def load_shared_cache_entries(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
) -> list[dict[str, str]]:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    with _connect_shared_state_db(path) as connection:
        rows = connection.execute(
            f"""
            SELECT {', '.join(SHARED_CACHE_ENTRY_COLUMNS)}
            FROM shared_cache_entries
            ORDER BY cache_key
            """
        ).fetchall()
    return [
        _normalize_shared_cache_entry({column: "" if row[column] is None else str(row[column]) for column in SHARED_CACHE_ENTRY_COLUMNS})
        for row in rows
    ]


def find_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
) -> dict[str, str] | None:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    with _connect_shared_state_db(path) as connection:
        return _find_shared_cache_entry_in_connection(connection, cache_key=cache_key)


def upsert_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
    source_family: str,
    symbol: str,
    period_id: str,
    period_signature: str,
    status: str,
    created_at: str,
    updated_at: str,
    claimed_at: str = "",
    claimed_by: str = "",
    lease_expires_at: str = "",
    last_heartbeat_at: str = "",
    auto_retry_count: int | str = 0,
    retryable: bool | int | str = False,
    last_error_code: str = "",
) -> dict[str, str]:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    new_row = _build_shared_cache_entry_row(
        cache_key=cache_key,
        source_family=source_family,
        symbol=symbol,
        period_id=period_id,
        period_signature=period_signature,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        claimed_at=claimed_at,
        claimed_by=claimed_by,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=last_heartbeat_at,
        auto_retry_count=auto_retry_count,
        retryable=retryable,
        last_error_code=last_error_code,
    )
    existing_row = find_shared_cache_entry(path, cache_key=cache_key)
    if existing_row is not None:
        immutable_columns = (
            "cache_key",
            "cache_key_version",
            "source_family",
            "symbol",
            "period_id",
            "period_signature",
            "created_at",
        )
        for column in immutable_columns:
            if existing_row[column] != new_row[column]:
                raise ValueError(f"shared_cache_entries row mismatch for cache_key {cache_key}: {column}")

    with _connect_shared_state_db(path) as connection:
        _save_shared_cache_entry_in_connection(connection, new_row)
        connection.commit()
    return find_shared_cache_entry(path, cache_key=cache_key)  # type: ignore[return-value]


def claim_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
    claimed_by: str,
    claimed_at: str,
    lease_duration_seconds: int,
) -> dict[str, str]:
    if not claimed_by.strip():
        raise ValueError("claimed_by must be a non-empty string")
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    claim_time = _parse_iso_datetime_text(claimed_at, field_name="claimed_at")
    lease_expires_at = _compute_lease_expires_at(claimed_at, lease_duration_seconds=lease_duration_seconds)
    with _connect_shared_state_db(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_row = _find_shared_cache_entry_in_connection(connection, cache_key=cache_key)
        if existing_row is None:
            raise ValueError(f"cache_key not found in shared_cache_entries: {cache_key}")
        can_claim = False
        auto_retry_count = int(existing_row["auto_retry_count"])
        if existing_row["status"] == RESULT_STATUS_PENDING:
            can_claim = True
        elif existing_row["status"] == RESULT_STATUS_RUNNING:
            can_claim = is_shared_cache_entry_stale(existing_row, now=claim_time)
        elif _can_auto_retry_failed_entry(existing_row):
            can_claim = True
            auto_retry_count = 1

        if not can_claim:
            raise ValueError(f"cache_key is not claimable: {cache_key}")

        claimed_row = _build_shared_cache_entry_state_row(
            existing_row,
            next_status=RESULT_STATUS_RUNNING,
            state_changed_at=claimed_at,
            claimed_at=claimed_at,
            claimed_by=claimed_by.strip(),
            lease_expires_at=lease_expires_at,
            last_heartbeat_at=claimed_at,
            auto_retry_count=auto_retry_count,
            retryable=False,
            last_error_code="",
        )
        _save_shared_cache_entry_in_connection(connection, claimed_row)
        connection.commit()
    return find_shared_cache_entry(path, cache_key=cache_key)  # type: ignore[return-value]


def heartbeat_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
    claimed_by: str,
    heartbeat_at: str,
    lease_duration_seconds: int,
) -> dict[str, str]:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    heartbeat_time = _parse_iso_datetime_text(heartbeat_at, field_name="heartbeat_at")
    lease_expires_at = _compute_lease_expires_at(heartbeat_at, lease_duration_seconds=lease_duration_seconds)
    with _connect_shared_state_db(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_row = _find_shared_cache_entry_in_connection(connection, cache_key=cache_key)
        if existing_row is None:
            raise ValueError(f"cache_key not found in shared_cache_entries: {cache_key}")
        if existing_row["status"] != RESULT_STATUS_RUNNING:
            raise ValueError(f"heartbeat requires running status: {cache_key}")
        if existing_row["claimed_by"] != claimed_by:
            raise ValueError(f"heartbeat requires matching claimed_by for cache_key {cache_key}")
        if is_shared_cache_entry_stale(existing_row, now=heartbeat_time):
            raise ValueError(f"heartbeat requires an active lease for cache_key {cache_key}")
        heartbeat_row = _build_shared_cache_entry_state_row(
            existing_row,
            next_status=RESULT_STATUS_RUNNING,
            state_changed_at=heartbeat_at,
            claimed_at=existing_row["claimed_at"],
            claimed_by=existing_row["claimed_by"],
            lease_expires_at=lease_expires_at,
            last_heartbeat_at=heartbeat_at,
        )
        _save_shared_cache_entry_in_connection(connection, heartbeat_row)
        connection.commit()
    return find_shared_cache_entry(path, cache_key=cache_key)  # type: ignore[return-value]


def complete_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
    claimed_by: str,
    completed_at: str,
) -> dict[str, str]:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    completed_time = _parse_iso_datetime_text(completed_at, field_name="completed_at")
    with _connect_shared_state_db(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_row = _find_shared_cache_entry_in_connection(connection, cache_key=cache_key)
        if existing_row is None:
            raise ValueError(f"cache_key not found in shared_cache_entries: {cache_key}")
        if existing_row["status"] != RESULT_STATUS_RUNNING:
            raise ValueError(f"complete requires running status: {cache_key}")
        if existing_row["claimed_by"] != claimed_by:
            raise ValueError(f"complete requires matching claimed_by for cache_key {cache_key}")
        if is_shared_cache_entry_stale(existing_row, now=completed_time):
            raise ValueError(f"complete requires an active lease for cache_key {cache_key}")
        completed_row = _build_shared_cache_entry_state_row(
            existing_row,
            next_status=RESULT_STATUS_COMPLETED,
            state_changed_at=completed_at,
            retryable=False,
            last_error_code="",
        )
        _save_shared_cache_entry_in_connection(connection, completed_row)
        connection.commit()
    return find_shared_cache_entry(path, cache_key=cache_key)  # type: ignore[return-value]


def fail_shared_cache_entry(
    db_path: str | Path = DEFAULT_SHARED_STATE_DB_PATH,
    *,
    cache_key: str,
    claimed_by: str,
    failed_at: str,
    retryable: bool,
    last_error_code: str = "",
) -> dict[str, str]:
    path = initialize_shared_state_db(db_path)
    get_shared_state_schema_version(path)
    failed_time = _parse_iso_datetime_text(failed_at, field_name="failed_at")
    error_code = last_error_code.strip()
    with _connect_shared_state_db(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_row = _find_shared_cache_entry_in_connection(connection, cache_key=cache_key)
        if existing_row is None:
            raise ValueError(f"cache_key not found in shared_cache_entries: {cache_key}")
        if existing_row["status"] != RESULT_STATUS_RUNNING:
            raise ValueError(f"fail requires running status: {cache_key}")
        if existing_row["claimed_by"] != claimed_by:
            raise ValueError(f"fail requires matching claimed_by for cache_key {cache_key}")
        if is_shared_cache_entry_stale(existing_row, now=failed_time):
            raise ValueError(f"fail requires an active lease for cache_key {cache_key}")
        failed_row = _build_shared_cache_entry_state_row(
            existing_row,
            next_status=RESULT_STATUS_FAILED,
            state_changed_at=failed_at,
            retryable=retryable,
            last_error_code=error_code,
        )
        _save_shared_cache_entry_in_connection(connection, failed_row)
        connection.commit()
    return find_shared_cache_entry(path, cache_key=cache_key)  # type: ignore[return-value]


def ensure_shared_cache_entry_for_acquisition(
    db_path: str | Path,
    *,
    acquisition_row: dict[str, str],
    created_at: str,
) -> dict[str, str]:
    existing_row = find_shared_cache_entry(db_path, cache_key=acquisition_row["cache_key"])
    if existing_row is not None:
        return existing_row
    return upsert_shared_cache_entry(
        db_path,
        cache_key=acquisition_row["cache_key"],
        source_family=acquisition_row["source_family"],
        symbol=acquisition_row["symbol"],
        period_id=acquisition_row["period_id"],
        period_signature=acquisition_row["period_signature"],
        status=RESULT_STATUS_PENDING,
        created_at=created_at,
        updated_at=created_at,
    )
