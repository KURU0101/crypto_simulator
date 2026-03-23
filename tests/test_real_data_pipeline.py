from pathlib import Path

import pytest

from trade_simulator.data.ohlcv import (
    build_close_to_close_returns,
    load_ohlcv_csv,
    load_returns_from_ohlcv_csv,
)
from trade_simulator.data.sources import (
    build_symbol_work_csv_path,
    load_data_sources_config,
    summarize_data_sources,
)
from trade_simulator.market_data_cli import main as market_data_main
from trade_simulator.real_data_comparison_cli import (
    format_real_data_comparison_results,
    load_real_data_comparison_config,
    prepare_cases_with_real_data_returns,
)


def test_load_ohlcv_csv_reads_sample_data() -> None:
    rows = load_ohlcv_csv("data/btcusdt_1h_sample.csv")

    assert len(rows) == 6
    assert rows[0]["timestamp"] == "2024-01-01T00:00:00Z"
    assert rows[-1]["close"] == 42300.0


def test_build_close_to_close_returns_generates_expected_values() -> None:
    payload = build_close_to_close_returns(
        [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            },
            {
                "timestamp": "2024-01-01T01:00:00Z",
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "volume": 11,
            },
            {
                "timestamp": "2024-01-01T02:00:00Z",
                "open": 102,
                "high": 103,
                "low": 101,
                "close": 101,
                "volume": 12,
            },
        ]
    )

    assert payload["price_basis"] == "close_to_close"
    assert payload["timestamps"] == [
        "2024-01-01T00:00:00Z",
        "2024-01-01T01:00:00Z",
        "2024-01-01T02:00:00Z",
    ]
    assert payload["return_timestamps"] == [
        "2024-01-01T01:00:00Z",
        "2024-01-01T02:00:00Z",
    ]
    assert payload["returns"] == pytest.approx([0.02, -0.009803921568627416])


def test_build_close_to_close_returns_sorts_unsorted_input() -> None:
    payload = build_close_to_close_returns(
        [
            {
                "timestamp": "2024-01-01T02:00:00Z",
                "open": 102,
                "high": 103,
                "low": 101,
                "close": 101,
                "volume": 12,
            },
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            },
            {
                "timestamp": "2024-01-01T01:00:00Z",
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "volume": 11,
            },
        ]
    )

    assert payload["timestamps"] == [
        "2024-01-01T00:00:00Z",
        "2024-01-01T01:00:00Z",
        "2024-01-01T02:00:00Z",
    ]
    assert payload["returns"] == pytest.approx([0.02, -0.009803921568627416])


def test_build_close_to_close_returns_handles_single_row() -> None:
    payload = build_close_to_close_returns(
        [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            }
        ]
    )

    assert payload["returns"] == []
    assert payload["return_timestamps"] == []


def test_build_close_to_close_returns_handles_two_row_minimum_case() -> None:
    payload = build_close_to_close_returns(
        [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            },
            {
                "timestamp": "2024-01-01T01:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 11,
            },
        ]
    )

    assert payload["returns"] == [0.0]
    assert payload["return_timestamps"] == ["2024-01-01T01:00:00Z"]


def test_build_close_to_close_returns_handles_flat_close_series() -> None:
    payload = build_close_to_close_returns(
        [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            },
            {
                "timestamp": "2024-01-01T01:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 11,
            },
            {
                "timestamp": "2024-01-01T02:00:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 12,
            },
        ]
    )

    assert payload["returns"] == [0.0, 0.0]


def test_load_returns_from_ohlcv_csv_raises_for_missing_required_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_close.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,volume",
                "2024-01-01T00:00:00Z,100,101,99,10",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required OHLCV columns: close"):
        load_returns_from_ohlcv_csv(csv_path)


def test_load_returns_from_ohlcv_csv_raises_for_empty_data(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ohlcv_rows must not be empty"):
        load_returns_from_ohlcv_csv(csv_path)


def test_load_returns_from_ohlcv_csv_raises_for_non_numeric_value(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_close.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                "2024-01-01T01:00:00Z,100,101,99,bad,11",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(TypeError, match="close must be numeric at row 1"):
        load_returns_from_ohlcv_csv(csv_path)


def test_load_returns_from_ohlcv_csv_raises_for_missing_timestamp(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_timestamp.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                ",100,101,99,101,11",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="timestamp is required at row 1"):
        load_returns_from_ohlcv_csv(csv_path)


def test_load_returns_from_ohlcv_csv_raises_for_duplicate_timestamp(tmp_path: Path) -> None:
    csv_path = tmp_path / "duplicate_timestamp.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                "2024-01-01T00:00:00Z,100,101,99,101,11",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="timestamp must be unique"):
        load_returns_from_ohlcv_csv(csv_path)


def test_load_returns_from_ohlcv_csv_rejects_nan_close(tmp_path: Path) -> None:
    csv_path = tmp_path / "nan_close.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                "2024-01-01T01:00:00Z,100,101,99,nan,11",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="close must be finite at row 1"):
        load_returns_from_ohlcv_csv(csv_path)


def test_prepare_cases_with_real_data_returns_connects_returns_to_comparison() -> None:
    data_source = {
        "data_source": {
            "symbol": "BTC/USDT",
            "ohlcv_csv_path": "data/btcusdt_1h_sample.csv",
        }
    }
    cases = [
        {
            "name": "threshold_real_data",
            "strategy": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "entry_threshold": 0.01,
            "exit_threshold": -0.004,
        },
        {
            "name": "consecutive_drop_real_data",
            "strategy": "consecutive_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "consecutive_periods": 2,
            "drop_threshold": -0.003,
            "exit_threshold": 0.01,
        },
    ]

    data_summary, prepared_cases = prepare_cases_with_real_data_returns(data_source, cases)

    assert data_summary["symbol"] == "BTC/USDT"
    assert data_summary["price_basis"] == "close_to_close"
    assert data_summary["returns_count"] == 5
    assert prepared_cases[0]["simulation_name"] == "threshold_real_data"
    assert len(prepared_cases[0]["returns"]) == 5
    assert prepared_cases[1]["returns"] == prepared_cases[0]["returns"]


def test_real_data_comparison_config_loading_reads_data_source_and_cases(tmp_path: Path) -> None:
    config_path = tmp_path / "real_data_comparison.json"
    config_path.write_text(
        """
        {
          "data_source": {
            "symbol": "BTC/USDT",
            "ohlcv_csv_path": "data/btcusdt_1h_sample.csv"
          },
          "cases": [
            {
              "name": "threshold_real_data",
              "strategy": "threshold",
              "initial_cash": 1000,
              "fee_rate": 0.0,
              "slippage_rate": 0.0,
              "entry_threshold": 0.01,
              "exit_threshold": -0.004
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    data_source, cases = load_real_data_comparison_config(str(config_path))

    assert data_source["data_source"]["symbol"] == "BTC/USDT"
    assert len(cases) == 1
    assert cases[0]["name"] == "threshold_real_data"


def test_real_data_pipeline_runs_multiple_strategies_on_same_returns() -> None:
    data_source, cases = load_real_data_comparison_config("config/real_data_comparison.example.json")
    data_summary, prepared_cases = prepare_cases_with_real_data_returns(data_source, cases)

    assert data_summary["returns_count"] == 5

    from trade_simulator.comparison import run_comparisons

    results = run_comparisons(prepared_cases)

    assert len(results) == 3
    assert [result["name"] for result in results] == [
        "threshold_real_data",
        "cumulative_drop_real_data",
        "consecutive_drop_real_data",
    ]
    assert all("final_value" in result for result in results)


def test_load_data_sources_config_supports_multiple_symbols() -> None:
    data_sources = load_data_sources_config(
        {
            "data_sources": {
                "default_symbol": "ETH/USDT",
                "symbols": [
                    {
                        "symbol": "BTC/USDT",
                        "ohlcv_csv_path": "data/market/btcusdt/1h_sample.csv",
                    },
                    {
                        "symbol": "ETH/USDT",
                        "ohlcv_csv_path": "data/market/ethusdt/1h_sample.csv",
                    },
                ],
            }
        }
    )

    assert data_sources["default_symbol"] == "ETH/USDT"
    assert data_sources["symbols"] == ["BTC/USDT", "ETH/USDT"]


def test_prepare_cases_with_real_data_returns_selects_symbol_from_multi_source_config() -> None:
    data_source = {
        "data_sources": {
            "default_symbol": "BTC/USDT",
            "symbols": [
                {
                    "symbol": "BTC/USDT",
                    "ohlcv_csv_path": "data/market/btcusdt/1h_sample.csv",
                },
                {
                    "symbol": "ETH/USDT",
                    "ohlcv_csv_path": "data/market/ethusdt/1h_sample.csv",
                },
            ],
        }
    }
    cases = [
        {
            "name": "threshold_real_data",
            "strategy": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "entry_threshold": 0.01,
            "exit_threshold": -0.004,
        }
    ]

    data_summary, prepared_cases = prepare_cases_with_real_data_returns(data_source, cases, symbol="ETH/USDT")

    assert data_summary["symbol"] == "ETH/USDT"
    assert data_summary["available_symbols"] == ["BTC/USDT", "ETH/USDT"]
    assert data_summary["ohlcv_csv_path"] == "data/market/ethusdt/1h_sample.csv"
    assert len(prepared_cases[0]["returns"]) == 5


def test_summarize_data_sources_returns_counts_per_symbol() -> None:
    summary = summarize_data_sources(
        {
            "data_sources": {
                "default_symbol": "BTC/USDT",
                "symbols": [
                    {
                        "symbol": "BTC/USDT",
                        "ohlcv_csv_path": "data/market/btcusdt/1h_sample.csv",
                    },
                    {
                        "symbol": "ETH/USDT",
                        "ohlcv_csv_path": "data/market/ethusdt/1h_sample.csv",
                    },
                ],
            }
        }
    )

    assert summary["default_symbol"] == "BTC/USDT"
    assert summary["symbols"][0]["symbol_slug"] == "btcusdt"
    assert summary["symbols"][1]["returns_count"] == 5


def test_build_symbol_work_csv_path_uses_symbol_slug() -> None:
    assert build_symbol_work_csv_path("var/replay", "ETH/USDT") == "var/replay/ethusdt_replay_work.csv"


def test_format_real_data_comparison_results_includes_data_summary() -> None:
    rendered = format_real_data_comparison_results(
        {
            "symbol": "BTC/USDT",
            "ohlcv_csv_path": "data/btcusdt_1h_sample.csv",
            "price_basis": "close_to_close",
            "ohlcv_points": 6,
            "returns_count": 5,
            "return_timestamps": ["2024-01-01T01:00:00Z"],
        },
        [{"name": "threshold_real_data", "final_value": 1010.0}],
    )

    assert '"symbol": "BTC/USDT"' in rendered
    assert '"results"' in rendered


def test_market_data_cli_main_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = market_data_main(["--config", "config/real_data_comparison.example.json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"default_symbol": "BTC/USDT"' in captured.out
    assert '"symbol": "ETH/USDT"' in captured.out
