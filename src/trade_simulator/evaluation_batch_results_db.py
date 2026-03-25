from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_EVALUATION_RESULTS_DB_PATH = Path("var/evaluation_batch/results.sqlite3")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _render_utc_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect_results_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_evaluation_results_db(db_path: str | Path) -> Path:
    path = Path(db_path)
    with _connect_results_db(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL,
                config_path TEXT,
                config_fingerprint TEXT NOT NULL,
                total_periods INTEGER NOT NULL,
                total_cases INTEGER NOT NULL,
                planned_rows INTEGER NOT NULL,
                succeeded_rows INTEGER NOT NULL,
                failed_rows INTEGER NOT NULL,
                output_csv_path TEXT,
                results_db_path TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_results (
                run_id TEXT NOT NULL,
                period_id TEXT NOT NULL,
                case_name TEXT NOT NULL,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                acquisition_key TEXT NOT NULL,
                artifact_path TEXT,
                fetched INTEGER,
                reused_existing_artifact INTEGER,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                returns_count INTEGER,
                price_basis TEXT,
                final_value REAL,
                trade_count INTEGER,
                completed_trade_count INTEGER,
                open_trade_count INTEGER,
                win_rate REAL,
                realized_pnl_total REAL,
                average_holding_period REAL,
                total_cost_amount REAL,
                PRIMARY KEY (run_id, period_id, case_name),
                FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
            )
            """
        )
        connection.commit()
    return path


def generate_evaluation_run_id(now: datetime | None = None) -> str:
    resolved_now = now or _utc_now()
    return f"{resolved_now.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"


def build_evaluation_run_config_fingerprint(payload: dict[str, object]) -> str:
    canonical_text = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def create_evaluation_run(db_path: str | Path, run_record: dict[str, object]) -> None:
    with _connect_results_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO evaluation_runs (
                run_id,
                started_at,
                ended_at,
                status,
                config_path,
                config_fingerprint,
                total_periods,
                total_cases,
                planned_rows,
                succeeded_rows,
                failed_rows,
                output_csv_path,
                results_db_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(run_record["run_id"]),
                str(run_record["started_at"]),
                run_record.get("ended_at"),
                str(run_record["status"]),
                run_record.get("config_path"),
                str(run_record["config_fingerprint"]),
                int(run_record["total_periods"]),
                int(run_record["total_cases"]),
                int(run_record["planned_rows"]),
                int(run_record["succeeded_rows"]),
                int(run_record["failed_rows"]),
                run_record.get("output_csv_path"),
                str(run_record["results_db_path"]),
            ),
        )
        connection.commit()


def update_evaluation_run(
    db_path: str | Path,
    *,
    run_id: str,
    succeeded_rows: int,
    failed_rows: int,
    status: str,
    ended_at: str | None = None,
) -> None:
    with _connect_results_db(db_path) as connection:
        connection.execute(
            """
            UPDATE evaluation_runs
            SET succeeded_rows = ?,
                failed_rows = ?,
                status = ?,
                ended_at = COALESCE(?, ended_at)
            WHERE run_id = ?
            """,
            (
                int(succeeded_rows),
                int(failed_rows),
                status,
                ended_at,
                run_id,
            ),
        )
        connection.commit()


def _normalize_optional_text(value: object) -> str | None:
    if value in ("", None):
        return None
    return str(value)


def _normalize_optional_int(value: object) -> int | None:
    if value in ("", None):
        return None
    return int(value)


def _normalize_optional_float(value: object) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def _normalize_optional_bool(value: object) -> int | None:
    if value in ("", None):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if str(value).strip().lower() in {"1", "true"}:
        return 1
    if str(value).strip().lower() in {"0", "false"}:
        return 0
    raise ValueError(f"unsupported boolean-like value: {value}")


def insert_evaluation_result_rows(
    db_path: str | Path,
    *,
    run_id: str,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    with _connect_results_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO evaluation_results (
                run_id,
                period_id,
                case_name,
                source,
                symbol,
                interval,
                window_start,
                window_end,
                acquisition_key,
                artifact_path,
                fetched,
                reused_existing_artifact,
                status,
                error_code,
                error_message,
                returns_count,
                price_basis,
                final_value,
                trade_count,
                completed_trade_count,
                open_trade_count,
                win_rate,
                realized_pnl_total,
                average_holding_period,
                total_cost_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    str(row["period_id"]),
                    str(row["case_name"]),
                    str(row["source"]),
                    str(row["symbol"]),
                    str(row["interval"]),
                    str(row["window_start"]),
                    str(row["window_end"]),
                    str(row["acquisition_key"]),
                    _normalize_optional_text(row.get("artifact_path")),
                    _normalize_optional_bool(row.get("fetched")),
                    _normalize_optional_bool(row.get("reused_existing_artifact")),
                    str(row["status"]),
                    _normalize_optional_text(row.get("error_code")),
                    _normalize_optional_text(row.get("error_message")),
                    _normalize_optional_int(row.get("returns_count")),
                    _normalize_optional_text(row.get("price_basis")),
                    _normalize_optional_float(row.get("final_value")),
                    _normalize_optional_int(row.get("trade_count")),
                    _normalize_optional_int(row.get("completed_trade_count")),
                    _normalize_optional_int(row.get("open_trade_count")),
                    _normalize_optional_float(row.get("win_rate")),
                    _normalize_optional_float(row.get("realized_pnl_total")),
                    _normalize_optional_float(row.get("average_holding_period")),
                    _normalize_optional_float(row.get("total_cost_amount")),
                )
                for row in rows
            ],
        )
        connection.commit()


def build_evaluation_run_record(
    *,
    run_id: str,
    config_path: str | None,
    config_fingerprint: str,
    total_periods: int,
    total_cases: int,
    planned_rows: int,
    output_csv_path: str,
    results_db_path: str,
    started_at: datetime | None = None,
) -> dict[str, object]:
    resolved_started_at = started_at or _utc_now()
    return {
        "run_id": run_id,
        "started_at": _render_utc_datetime(resolved_started_at),
        "ended_at": None,
        "status": "running",
        "config_path": config_path,
        "config_fingerprint": config_fingerprint,
        "total_periods": total_periods,
        "total_cases": total_cases,
        "planned_rows": planned_rows,
        "succeeded_rows": 0,
        "failed_rows": 0,
        "output_csv_path": output_csv_path,
        "results_db_path": results_db_path,
    }


def render_utc_now() -> str:
    return _render_utc_datetime(_utc_now())
