from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.evaluation_runner import EmptyReturnsError, run_single_case_evaluation
from trade_simulator.evaluation_runner_cli import main as evaluation_runner_main


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
            "high": "103",
            "low": "99",
            "close": "102",
            "volume": "11",
        },
        {
            "timestamp": "2024-01-01T02:00:00Z",
            "open": "102",
            "high": "104",
            "low": "101",
            "close": "101",
            "volume": "12",
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


def _threshold_case() -> dict[str, object]:
    return {
        "name": "threshold_case",
        "strategy": "threshold",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "entry_threshold": 0.01,
        "exit_threshold": -0.005,
    }


def test_run_single_case_evaluation_runs_end_to_end_from_saved_market_data(tmp_path: Path) -> None:
    fetch_count = 0

    def fetcher(**kwargs):
        nonlocal fetch_count
        fetch_count += 1
        return _sample_rows()

    result = run_single_case_evaluation(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T03:00:00Z",
        case_config=_threshold_case(),
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_count == 1
    assert result["case_name"] == "threshold_case"
    assert result["fetched"] is True
    assert result["reused_existing_artifact"] is False
    assert result["returns_count"] == 2
    assert result["summary"]["name"] == "threshold_case"
    assert "final_value" in result["summary"]


def test_run_single_case_evaluation_reuses_market_data_before_simulation(tmp_path: Path) -> None:
    fetch_count = 0

    def fetcher(**kwargs):
        nonlocal fetch_count
        fetch_count += 1
        return _sample_rows()

    run_single_case_evaluation(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T03:00:00Z",
        case_config=_threshold_case(),
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )
    reused = run_single_case_evaluation(
        source="binance_spot",
        symbol="BTCUSDT",
        interval="1h",
        window_start="2024-01-01T00:00:00Z",
        window_end="2024-01-01T03:00:00Z",
        case_config=_threshold_case(),
        cache_root=tmp_path / "cache",
        shared_state_db_path=tmp_path / "shared_state.sqlite3",
        fetcher=fetcher,
    )

    assert fetch_count == 1
    assert reused["fetched"] is False
    assert reused["reused_existing_artifact"] is True
    assert reused["summary"]["name"] == "threshold_case"


def test_run_single_case_evaluation_rejects_invalid_case(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="threshold strategy requires entry_threshold and exit_threshold"):
        run_single_case_evaluation(
            source="binance_spot",
            symbol="BTCUSDT",
            interval="1h",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T03:00:00Z",
            case_config={
                "name": "broken_case",
                "strategy": "threshold",
                "initial_cash": 1000,
            },
            cache_root=tmp_path / "cache",
            shared_state_db_path=tmp_path / "shared_state.sqlite3",
            fetcher=lambda **kwargs: _sample_rows(),
        )


def test_run_single_case_evaluation_fails_when_returns_are_empty(tmp_path: Path) -> None:
    with pytest.raises(EmptyReturnsError, match="returns must not be empty for evaluation"):
        run_single_case_evaluation(
            source="binance_spot",
            symbol="BTCUSDT",
            interval="1h",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T01:00:00Z",
            case_config=_threshold_case(),
            cache_root=tmp_path / "cache",
            shared_state_db_path=tmp_path / "shared_state.sqlite3",
            fetcher=lambda **kwargs: _single_row_sample(),
        )


def test_run_single_case_evaluation_surfaces_invalid_ohlcv_for_returns(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="close must be greater than 0 at row 1"):
        run_single_case_evaluation(
            source="binance_spot",
            symbol="BTCUSDT",
            interval="1h",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T03:00:00Z",
            case_config=_threshold_case(),
            cache_root=tmp_path / "cache",
            shared_state_db_path=tmp_path / "shared_state.sqlite3",
            fetcher=lambda **kwargs: [
                _sample_rows()[0],
                {
                    "timestamp": "2024-01-01T01:00:00Z",
                    "open": "100",
                    "high": "103",
                    "low": "99",
                    "close": "0",
                    "volume": "11",
                },
            ],
        )


def test_evaluation_runner_cli_prints_tracking_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(_threshold_case()), encoding="utf-8")
    monkeypatch.setattr(
        "trade_simulator.evaluation_runner_cli.run_single_case_evaluation",
        lambda **kwargs: {
            "acquisition_key": "aq_key",
            "artifact_path": str(tmp_path / "cache" / "artifact.csv"),
            "artifact_kind": "ohlcv_csv",
            "source": kwargs["source"],
            "symbol": kwargs["symbol"],
            "interval": kwargs["interval"],
            "window_start": kwargs["window_start"],
            "window_end": kwargs["window_end"],
            "fetched": False,
            "reused_existing_artifact": True,
            "case_name": "threshold_case",
            "returns_count": 2,
            "price_basis": "close_to_close",
            "summary": {"name": "threshold_case", "final_value": 1000.0},
        },
    )

    exit_code = evaluation_runner_main(
        [
            "--source",
            "binance_spot",
            "--symbol",
            "BTCUSDT",
            "--start",
            "2024-01-01T00:00:00Z",
            "--end",
            "2024-01-01T03:00:00Z",
            "--interval",
            "1h",
            "--case-config",
            str(case_path),
            "--cache-root",
            str(tmp_path / "cache"),
            "--shared-state-db-path",
            str(tmp_path / "shared_state.sqlite3"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["acquisition_key"]
    assert payload["artifact_path"]
    assert payload["case_name"] == "threshold_case"
    assert "summary" in payload
