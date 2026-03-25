from __future__ import annotations

from pathlib import Path

import pytest

from trade_simulator._evaluation_market_data_shared_state import (
    MARKET_DATA_STATUS_COMPLETED,
    MARKET_DATA_STATUS_FAILED,
    find_market_data_acquisition,
)
from trade_simulator.evaluation_market_data import (
    build_market_data_acquisition_key,
    resolve_evaluation_market_data,
    validate_saved_ohlcv_artifact,
)


def _sample_rows() -> list[dict[str, object]]:
    return [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "10",
        },
        {
            "timestamp": "2024-01-01T01:00:00Z",
            "open": "100",
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": "11",
        },
    ]


def _single_row_sample() -> list[dict[str, object]]:
    return [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "10",
        }
    ]


def test_resolve_evaluation_market_data_fetches_and_saves_on_first_run(tmp_path: Path) -> None:
    fetch_calls: list[dict[str, str]] = []

    def fetcher(**kwargs):
        fetch_calls.append(kwargs)
        return _sample_rows()

    result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert result["fetched"] is True
    assert result["reused_existing_artifact"] is False
    assert len(fetch_calls) == 1
    assert Path(str(result["artifact_path"])).exists()
    saved_rows = validate_saved_ohlcv_artifact(result["artifact_path"])
    assert len(saved_rows) == 2

    shared_row = find_market_data_acquisition(
        tmp_path / "shared_state.sqlite3",
        acquisition_key=str(result["acquisition_key"]),
    )
    assert shared_row is not None
    assert shared_row["status"] == MARKET_DATA_STATUS_COMPLETED


def test_resolve_evaluation_market_data_reuses_existing_completed_artifact(tmp_path: Path) -> None:
    fetch_count = 0

    def fetcher(**kwargs):
        nonlocal fetch_count
        fetch_count += 1
        return _sample_rows()

    first_result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )
    second_result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_count == 1
    assert first_result["acquisition_key"] == second_result["acquisition_key"]
    assert second_result["fetched"] is False
    assert second_result["reused_existing_artifact"] is True


def test_resolve_evaluation_market_data_marks_failed_when_fetch_fails(tmp_path: Path) -> None:
    def fetcher(**kwargs):
        raise RuntimeError("boom")

    acquisition_key = build_market_data_acquisition_key(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
    )

    with pytest.raises(RuntimeError, match="boom"):
        resolve_evaluation_market_data(
            source="binance_spot",
            symbol="BTCUSDT",
            interval="1h",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T02:00:00Z",
            cache_root=tmp_path / "cache",
            shared_state_db_path=tmp_path / "shared_state.sqlite3",
            fetcher=fetcher,
        )

    shared_row = find_market_data_acquisition(
        tmp_path / "shared_state.sqlite3",
        acquisition_key=acquisition_key,
    )
    assert shared_row is not None
    assert shared_row["status"] == MARKET_DATA_STATUS_FAILED


def test_resolve_evaluation_market_data_supports_single_row_period(tmp_path: Path) -> None:
    result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T01:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _single_row_sample(),
    )

    assert result["row_count"] == 1
    assert Path(str(result["artifact_path"])).exists()


def test_resolve_evaluation_market_data_refetches_when_completed_artifact_is_broken(tmp_path: Path) -> None:
    fetch_count = 0

    def fetcher(**kwargs):
        nonlocal fetch_count
        fetch_count += 1
        return _sample_rows()

    first_result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )
    Path(str(first_result["artifact_path"])).write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

    second_result = resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_count == 2
    assert second_result["fetched"] is True
    shared_row = find_market_data_acquisition(
        tmp_path / "shared_state.sqlite3",
        acquisition_key=str(second_result["acquisition_key"]),
    )
    assert shared_row is not None
    assert shared_row["status"] == MARKET_DATA_STATUS_COMPLETED


def test_resolve_evaluation_market_data_does_not_leave_completed_after_broken_artifact_and_refetch_failure(
    tmp_path: Path,
) -> None:
    resolve_evaluation_market_data(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=lambda **kwargs: _sample_rows(),
    )
    acquisition_key = build_market_data_acquisition_key(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T02:00:00Z",
    )
    shared_row = find_market_data_acquisition(tmp_path / "shared_state.sqlite3", acquisition_key=acquisition_key)
    assert shared_row is not None
    Path(shared_row["artifact_path"]).write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refetch failed"):
        resolve_evaluation_market_data(
            source="binance_spot",
            symbol="BTCUSDT",
            interval="1h",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T02:00:00Z",
            cache_root=tmp_path / "cache",
            shared_state_db_path=tmp_path / "shared_state.sqlite3",
            fetcher=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("refetch failed")),
        )

    failed_row = find_market_data_acquisition(tmp_path / "shared_state.sqlite3", acquisition_key=acquisition_key)
    assert failed_row is not None
    assert failed_row["status"] == MARKET_DATA_STATUS_FAILED
