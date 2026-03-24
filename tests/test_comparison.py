from pathlib import Path

import pytest

from trade_simulator.comparison import run_case, run_comparisons, summarize_case_result
from trade_simulator.config import load_config
from trade_simulator.simulation import simulate


def test_run_case_supports_manual_strategy_configs() -> None:
    result = run_case(
        {
            "strategy": "manual",
            "simulation_name": "manual",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        }
    )

    assert result["entry_signals"] == [True]
    assert result["exit_signals"] == [False]


def test_run_case_supports_threshold_based_strategy_configs() -> None:
    result = run_case(
        {
            "simulation_name": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.01, -0.02, 0.03, 0.01],
            "entry_threshold": 0.01,
            "exit_threshold": -0.01,
        }
    )

    assert result["entry_signals"] == [True, False, True, False]
    assert result["exit_signals"] == [False, True, False, False]


def test_run_case_supports_cumulative_drop_strategy_configs() -> None:
    result = run_case(
        {
            "strategy": "cumulative_drop",
            "simulation_name": "cumulative_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.002, -0.004, -0.005, 0.006],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    )

    assert result["entry_signals"] == [False, False, True, False]
    assert result["exit_signals"] == [False, False, False, True]


def test_run_case_supports_consecutive_drop_strategy_configs() -> None:
    result = run_case(
        {
            "strategy": "consecutive_drop",
            "simulation_name": "consecutive_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.004, -0.003, -0.005, 0.006],
            "consecutive_periods": 3,
            "drop_threshold": -0.003,
            "exit_threshold": 0.005,
        }
    )

    assert result["entry_signals"] == [False, False, True, False]
    assert result["exit_signals"] == [False, False, False, True]


def test_run_case_raises_when_strategy_inputs_are_missing() -> None:
    with pytest.raises(
        ValueError,
        match="each comparison case must include manual signals, threshold parameters, cumulative_drop parameters, or consecutive_drop parameters",
    ):
        run_case(
            {
                "simulation_name": "invalid",
                "initial_cash": 1000,
                "returns": [0.01],
            }
        )


def test_run_case_raises_for_invalid_strategy_name() -> None:
    with pytest.raises(ValueError, match="strategy must be one of manual, threshold, cumulative_drop, or consecutive_drop"):
        run_case(
            {
                "strategy": "unknown",
                "simulation_name": "invalid",
                "initial_cash": 1000,
                "returns": [0.01],
            }
        )


def test_summarize_case_result_matches_simulation_summary_fields() -> None:
    result = simulate(
        {
            "simulation_name": "test",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.1, -0.05, 0.02],
            "entry_signals": [True, False, False],
            "exit_signals": [False, True, False],
        }
    )

    summary = summarize_case_result("baseline", result)

    assert summary == {
        "name": "baseline",
        "final_value": 1100.0,
        "trade_count": 1,
        "completed_trade_count": 1,
        "open_trade_count": 0,
        "periods_in_position": 1,
        "winning_trades": 1,
        "losing_trades": 0,
        "win_rate": 1.0,
        "realized_pnl_total": 100.0,
        "total_realized_pnl": 100.0,
        "average_pnl_per_completed_trade": 100.0,
        "average_holding_period": 1.0,
        "total_cost_amount": 0.0,
    }


def test_summarize_case_result_handles_open_trade_and_zero_completed_trade_count() -> None:
    result = simulate(
        {
            "simulation_name": "open_only",
            "initial_cash": 1000,
            "fee_rate": 0.01,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        }
    )

    summary = summarize_case_result("open_only", result)

    assert summary["trade_count"] == 1
    assert summary["completed_trade_count"] == 0
    assert summary["open_trade_count"] == 1
    assert summary["win_rate"] == 0.0
    assert summary["average_pnl_per_completed_trade"] == 0.0
    assert summary["total_realized_pnl"] == 0.0
    assert summary["total_cost_amount"] == pytest.approx(10.0)


def test_run_comparisons_returns_one_summary_per_case() -> None:
    cases = [
        {
            "name": "zero_cost",
            "simulation_name": "zero_cost",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        },
        {
            "name": "with_cost",
            "simulation_name": "with_cost",
            "initial_cash": 1000,
            "fee_rate": 0.01,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        },
    ]

    comparisons = run_comparisons(cases)

    assert len(comparisons) == 2
    assert comparisons == [
        {
            "name": "zero_cost",
            "final_value": 1100.0,
            "trade_count": 1,
            "completed_trade_count": 0,
            "open_trade_count": 1,
            "periods_in_position": 1,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "total_realized_pnl": 0,
            "average_pnl_per_completed_trade": 0.0,
            "average_holding_period": 0.0,
            "total_cost_amount": 0.0,
        },
        {
            "name": "with_cost",
            "final_value": 1089.0,
            "trade_count": 1,
            "completed_trade_count": 0,
            "open_trade_count": 1,
            "periods_in_position": 1,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "total_realized_pnl": 0,
            "average_pnl_per_completed_trade": 0.0,
            "average_holding_period": 0.0,
            "total_cost_amount": 10.0,
        },
    ]


def test_run_comparisons_includes_external_signal_metadata_for_manual_cases() -> None:
    comparisons = run_comparisons(
        [
            {
                "name": "external_signal_case",
                "simulation_name": "external_signal_case",
                "strategy": "manual",
                "initial_cash": 1000,
                "fee_rate": 0.0,
                "slippage_rate": 0.0,
                "returns": [0.1, -0.05, 0.02],
                "entry_signals": [False, True, False],
                "exit_signals": [False, False, True],
                "external_signal": {
                    "consumption_series_name": "blended_weighted_signal_count",
                    "blended_weights": {
                        "symbol": 0.5,
                        "topic": 0.5,
                    },
                },
                "external_signal_consumption_features": {
                    "return_timestamps": [
                        "2024-01-01T01:00:00Z",
                        "2024-01-01T02:00:00Z",
                        "2024-01-01T03:00:00Z",
                    ],
                    "summary": {
                        "blended_definition": {
                            "base_series": [
                                "weighted_symbol_signal_count",
                                "weighted_topic_signal_count",
                            ],
                            "weights": {
                                "symbol_weight": 0.5,
                                "topic_weight": 0.5,
                            },
                        }
                    },
                },
            }
        ]
    )

    assert comparisons[0]["external_signal"] == {
        "consumption_series_name": "blended_weighted_signal_count",
        "blended_weights": {
            "symbol": 0.5,
            "topic": 0.5,
        },
        "blended_definition": {
            "base_series": [
                "weighted_symbol_signal_count",
                "weighted_topic_signal_count",
            ],
            "weights": {
                "symbol_weight": 0.5,
                "topic_weight": 0.5,
            },
        },
    }
    assert comparisons[0]["signal_summary"] == {
        "entry_signal_count": 1,
        "exit_signal_count": 1,
        "entry_signal_indexes": [1],
        "exit_signal_indexes": [2],
        "entry_signal_timestamps": ["2024-01-01T02:00:00Z"],
        "exit_signal_timestamps": ["2024-01-01T03:00:00Z"],
    }


def test_run_comparisons_matches_single_simulation_summary() -> None:
    case = {
        "name": "baseline",
        "simulation_name": "baseline",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05, 0.02],
        "entry_signals": [True, False, False],
        "exit_signals": [False, True, False],
    }

    comparison = run_comparisons([case])[0]
    single_result = simulate({key: value for key, value in case.items() if key != "name"})

    assert comparison == summarize_case_result("baseline", single_result)


def test_run_comparisons_raises_when_name_is_missing() -> None:
    cases = [
        {
            "simulation_name": "missing_name",
            "initial_cash": 1000,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        }
    ]

    with pytest.raises(ValueError, match="each comparison case must include a name"):
        run_comparisons(cases)


def test_run_comparisons_allows_duplicate_names() -> None:
    cases = [
        {
            "name": "duplicate",
            "simulation_name": "first",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        },
        {
            "name": "duplicate",
            "simulation_name": "second",
            "initial_cash": 1000,
            "fee_rate": 0.01,
            "slippage_rate": 0.0,
            "returns": [0.1],
            "entry_signals": [True],
            "exit_signals": [False],
        },
    ]

    comparisons = run_comparisons(cases)

    assert [comparison["name"] for comparison in comparisons] == ["duplicate", "duplicate"]
    assert comparisons[0]["final_value"] != comparisons[1]["final_value"]


def test_run_comparisons_returns_empty_list_for_empty_cases() -> None:
    assert run_comparisons([]) == []


def test_run_comparisons_handles_single_zero_summary_case() -> None:
    comparisons = run_comparisons(
        [
            {
                "name": "flat",
                "simulation_name": "flat",
                "initial_cash": 1000,
                "fee_rate": 0.0,
                "slippage_rate": 0.0,
                "returns": [],
                "entry_signals": [],
                "exit_signals": [],
            }
        ]
    )

    assert comparisons == [
        {
            "name": "flat",
            "final_value": 1000.0,
            "trade_count": 0,
            "completed_trade_count": 0,
            "open_trade_count": 0,
            "periods_in_position": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "total_realized_pnl": 0,
            "average_pnl_per_completed_trade": 0.0,
            "average_holding_period": 0.0,
            "total_cost_amount": 0.0,
        }
    ]


def test_run_comparisons_supports_mixed_threshold_cumulative_drop_and_consecutive_drop_cases() -> None:
    cases = load_config(Path("config/comparison.example.json"))
    comparisons = run_comparisons(cases)

    assert [comparison["name"] for comparison in comparisons] == [
        "threshold_baseline",
        "threshold_with_cost",
        "cumulative_drop_fast",
        "cumulative_drop_strict",
        "consecutive_drop_fast",
        "consecutive_drop_strict",
    ]
    assert [comparison["strategy"] for comparison in comparisons] == [
        "threshold",
        "threshold",
        "cumulative_drop",
        "cumulative_drop",
        "consecutive_drop",
        "consecutive_drop",
    ]
    assert comparisons[0]["entry_threshold"] == 0.01
    assert comparisons[1]["total_cost_amount"] > 0
    assert comparisons[1]["final_value"] < comparisons[0]["final_value"]
    assert comparisons[2]["trade_count"] >= comparisons[3]["trade_count"]
    assert comparisons[4]["trade_count"] >= comparisons[5]["trade_count"]
    assert comparisons[2]["entry_window"] == 3
    assert comparisons[3]["entry_window"] == 5
    assert comparisons[4]["consecutive_periods"] == 3
    assert comparisons[5]["consecutive_periods"] == 4
    assert comparisons[3]["trade_count"] == 0
    assert comparisons[3]["completed_trade_count"] == 0
    assert comparisons[3]["open_trade_count"] == 0
    assert comparisons[3]["final_value"] == 100000.0
    assert "drop_threshold" in comparisons[4]
    assert comparisons[4]["trade_count"] > 0
    assert comparisons[5]["trade_count"] == 0


def test_run_comparisons_allows_cumulative_drop_case_with_unclosed_trade() -> None:
    comparisons = run_comparisons(
        [
            {
                "name": "open_trade_cumulative_drop",
                "strategy": "cumulative_drop",
                "simulation_name": "open_trade_cumulative_drop",
                "initial_cash": 1000,
                "fee_rate": 0.0,
                "slippage_rate": 0.0,
                "returns": [-0.004, -0.004, -0.003, 0.001],
                "entry_window": 3,
                "entry_cumulative_threshold": -0.01,
                "exit_threshold": 0.005,
            }
        ]
    )

    assert comparisons == [
        {
            "name": "open_trade_cumulative_drop",
            "strategy": "cumulative_drop",
            "final_value": pytest.approx(997.9969999999998),
            "trade_count": 1,
            "completed_trade_count": 0,
            "open_trade_count": 1,
            "periods_in_position": 2,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "total_realized_pnl": 0,
            "average_pnl_per_completed_trade": 0.0,
            "average_holding_period": 0.0,
            "total_cost_amount": 0.0,
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    ]


def test_run_comparisons_raises_for_missing_threshold_pair() -> None:
    with pytest.raises(
        ValueError,
        match="each comparison case must include manual signals, threshold parameters, cumulative_drop parameters, or consecutive_drop parameters",
    ):
        run_comparisons(
            [
                {
                    "name": "invalid_threshold_case",
                    "simulation_name": "invalid_threshold_case",
                    "initial_cash": 1000,
                    "returns": [0.01],
                    "entry_threshold": 0.01,
                }
            ]
        )


def test_run_comparisons_raises_for_invalid_threshold_type_case() -> None:
    with pytest.raises(TypeError, match="entry_threshold must be a number"):
        run_comparisons(
            [
                {
                    "name": "invalid_threshold_type",
                    "simulation_name": "invalid_threshold_type",
                    "initial_cash": 1000,
                    "returns": [0.01],
                    "entry_threshold": "0.01",
                    "exit_threshold": -0.01,
                }
            ]
        )


def test_run_comparisons_raises_for_missing_cumulative_drop_parameters() -> None:
    with pytest.raises(
        ValueError,
        match="cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold",
    ):
        run_comparisons(
            [
                {
                    "name": "invalid_cumulative_drop_case",
                    "strategy": "cumulative_drop",
                    "simulation_name": "invalid_cumulative_drop_case",
                    "initial_cash": 1000,
                    "returns": [-0.01, -0.01],
                    "entry_window": 3,
                    "exit_threshold": 0.005,
                }
            ]
        )


def test_run_comparisons_raises_for_invalid_strategy_value() -> None:
    with pytest.raises(ValueError, match="strategy must be one of manual, threshold, cumulative_drop, or consecutive_drop"):
        run_comparisons(
            [
                {
                    "name": "invalid_strategy_case",
                    "strategy": "invalid",
                    "simulation_name": "invalid_strategy_case",
                    "initial_cash": 1000,
                    "returns": [0.01],
                }
            ]
        )


def test_run_comparisons_raises_for_missing_consecutive_drop_parameters() -> None:
    with pytest.raises(
        ValueError,
        match="consecutive_drop strategy requires consecutive_periods, drop_threshold, and exit_threshold",
    ):
        run_comparisons(
            [
                {
                    "name": "invalid_consecutive_drop_case",
                    "strategy": "consecutive_drop",
                    "simulation_name": "invalid_consecutive_drop_case",
                    "initial_cash": 1000,
                    "returns": [-0.01, -0.01, -0.01],
                    "consecutive_periods": 3,
                    "exit_threshold": 0.005,
                }
            ]
        )
