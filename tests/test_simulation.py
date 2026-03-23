from pathlib import Path
import pytest

from trade_simulator.comparison_cli import format_comparison_results, load_comparison_cases, main as comparison_main
from trade_simulator.config import load_config
from trade_simulator.comparison import run_case, run_comparisons, summarize_case_result
from trade_simulator.signals import (
    generate_consecutive_drop_signals,
    generate_cumulative_drop_signals,
    generate_threshold_signals,
    simulate_consecutive_drop_strategy,
    simulate_cumulative_drop_strategy,
    simulate_threshold_strategy,
)
from trade_simulator.simulation import simulate


def test_package_imports() -> None:
    import trade_simulator  # noqa: F401


def test_load_config() -> None:
    config_path = Path("config/simulation.example.json")
    config = load_config(config_path)

    assert config["simulation_name"] == "example_simulation"
    assert config["initial_cash"] == 100000
    assert config["fee_rate"] == 0.0
    assert config["slippage_rate"] == 0.0
    assert config["returns"] == [0.01, -0.02, 0.03, 0.01]
    assert config["entry_signals"] == [True, False, True, False]
    assert config["exit_signals"] == [False, True, False, False]


def test_load_comparison_config() -> None:
    config_path = Path("config/comparison.example.json")
    cases = load_config(config_path)

    assert len(cases) == 5
    assert cases[0]["name"] == "threshold_baseline"
    assert cases[0]["strategy"] == "threshold"
    assert cases[1]["name"] == "cumulative_drop_fast"
    assert cases[1]["strategy"] == "cumulative_drop"
    assert cases[1]["entry_window"] == 3
    assert cases[2]["name"] == "cumulative_drop_strict"
    assert cases[2]["entry_cumulative_threshold"] == -0.026
    assert cases[3]["name"] == "consecutive_drop_fast"
    assert cases[3]["strategy"] == "consecutive_drop"
    assert cases[4]["name"] == "consecutive_drop_strict"
    assert cases[4]["consecutive_periods"] == 4
    assert all(case["initial_cash"] == 100000 for case in cases)


def test_load_comparison_cases_accepts_root_list_config() -> None:
    cases = load_comparison_cases("config/comparison.example.json")

    assert len(cases) == 5
    assert cases[0]["name"] == "threshold_baseline"
    assert cases[-1]["name"] == "consecutive_drop_strict"


def test_load_comparison_cases_reads_cases_from_dict_config(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text(
        """
        {
          "cases": [
            {
              "name": "single",
              "simulation_name": "single",
              "initial_cash": 1000,
              "strategy": "cumulative_drop",
              "fee_rate": 0.0,
              "slippage_rate": 0.0,
              "returns": [],
              "entry_window": 3,
              "entry_cumulative_threshold": -0.01,
              "exit_threshold": 0.005
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    cases = load_comparison_cases(str(config_path))

    assert cases == [
        {
            "name": "single",
            "simulation_name": "single",
            "initial_cash": 1000,
            "strategy": "cumulative_drop",
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    ]


def test_generate_threshold_signals_creates_entries_and_exits_from_returns() -> None:
    entry_signals, exit_signals = generate_threshold_signals(
        [0.01, 0.02, -0.01, 0.015, -0.02],
        0.01,
        -0.01,
    )

    assert entry_signals == [True, False, False, True, False]
    assert exit_signals == [False, False, True, False, True]


def test_generate_threshold_signals_does_not_reenter_before_exit() -> None:
    entry_signals, exit_signals = generate_threshold_signals(
        [0.02, 0.03, 0.04, -0.02],
        0.01,
        -0.01,
    )

    assert entry_signals == [True, False, False, False]
    assert exit_signals == [False, False, False, True]


def test_generate_threshold_signals_allows_reentry_after_exit() -> None:
    entry_signals, exit_signals = generate_threshold_signals(
        [0.01, -0.01, 0.02, -0.02],
        0.01,
        -0.01,
    )

    assert entry_signals == [True, False, True, False]
    assert exit_signals == [False, True, False, True]


def test_generate_threshold_signals_accepts_empty_returns() -> None:
    entry_signals, exit_signals = generate_threshold_signals([], 0.01, -0.01)

    assert entry_signals == []
    assert exit_signals == []


def test_generate_threshold_signals_handles_exact_threshold_matches() -> None:
    entry_signals, exit_signals = generate_threshold_signals(
        [0.01, -0.01],
        0.01,
        -0.01,
    )

    assert entry_signals == [True, False]
    assert exit_signals == [False, True]


def test_generate_threshold_signals_handles_single_period_without_exit() -> None:
    entry_signals, exit_signals = generate_threshold_signals([0.02], 0.01, -0.01)

    assert entry_signals == [True]
    assert exit_signals == [False]


def test_generate_threshold_signals_returns_all_false_when_thresholds_are_never_met() -> None:
    entry_signals, exit_signals = generate_threshold_signals(
        [0.001, -0.001, 0.0],
        0.01,
        -0.01,
    )

    assert entry_signals == [False, False, False]
    assert exit_signals == [False, False, False]


def test_generate_threshold_signals_raises_for_non_numeric_thresholds() -> None:
    with pytest.raises(TypeError, match="entry_threshold must be a number"):
        generate_threshold_signals([0.01], "0.01", -0.01)

    with pytest.raises(TypeError, match="exit_threshold must be a number"):
        generate_threshold_signals([0.01], 0.01, None)


def test_generate_threshold_signals_raises_for_invalid_returns_input() -> None:
    with pytest.raises(TypeError, match="returns must be a list"):
        generate_threshold_signals(None, 0.01, -0.01)

    with pytest.raises(TypeError, match="returns must be a list"):
        generate_threshold_signals((0.01, -0.01), 0.01, -0.01)

    with pytest.raises(TypeError, match=r"returns\[1\] must be a number"):
        generate_threshold_signals([0.01, "bad"], 0.01, -0.01)


def test_generate_cumulative_drop_signals_creates_entries_and_exits_from_cumulative_drop() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.002, -0.004, -0.005, 0.006, -0.003, -0.004, -0.004, 0.005],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False, False, True, False]
    assert exit_signals == [False, False, False, True, False, False, False, True]


def test_generate_cumulative_drop_signals_does_not_enter_before_window_is_ready() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.02, 0.01],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False]
    assert exit_signals == [False, False]


def test_generate_cumulative_drop_signals_does_not_reenter_before_exit() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.004, -0.004, -0.004, -0.004, 0.006],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False]
    assert exit_signals == [False, False, False, False, True]


def test_generate_cumulative_drop_signals_allows_reentry_after_exit() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.004, -0.004, -0.004, 0.006, -0.005, -0.004, -0.004, 0.005],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False, False, True, False]
    assert exit_signals == [False, False, False, True, False, False, False, True]


def test_generate_cumulative_drop_signals_accepts_empty_returns() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals([], 3, -0.01, 0.005)

    assert entry_signals == []
    assert exit_signals == []


def test_generate_cumulative_drop_signals_supports_window_one() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.01, 0.005],
        1,
        -0.01,
        0.005,
    )

    assert entry_signals == [True, False]
    assert exit_signals == [False, True]


def test_generate_cumulative_drop_signals_handles_exact_threshold_matches() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [-0.003, -0.003, -0.004, 0.005],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False, True, False]
    assert exit_signals == [False, False, False, True]


def test_generate_cumulative_drop_signals_returns_all_false_when_entry_never_occurs() -> None:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        [0.001, -0.001, 0.0, 0.002],
        3,
        -0.01,
        0.005,
    )

    assert entry_signals == [False, False, False, False]
    assert exit_signals == [False, False, False, False]


def test_generate_cumulative_drop_signals_raises_for_invalid_parameters() -> None:
    with pytest.raises(TypeError, match="entry_window must be an int"):
        generate_cumulative_drop_signals([0.01], 3.0, -0.01, 0.005)

    with pytest.raises(ValueError, match="entry_window must be greater than 0"):
        generate_cumulative_drop_signals([0.01], 0, -0.01, 0.005)

    with pytest.raises(TypeError, match="entry_cumulative_threshold must be a number"):
        generate_cumulative_drop_signals([0.01], 3, None, 0.005)

    with pytest.raises(TypeError, match="exit_threshold must be a number"):
        generate_cumulative_drop_signals([0.01], 3, -0.01, "0.005")


def test_generate_cumulative_drop_signals_raises_for_invalid_returns_input() -> None:
    with pytest.raises(TypeError, match="returns must be a list"):
        generate_cumulative_drop_signals(None, 3, -0.01, 0.005)

    with pytest.raises(TypeError, match=r"returns\[1\] must be a number"):
        generate_cumulative_drop_signals([0.01, "bad"], 3, -0.01, 0.005)


def test_generate_consecutive_drop_signals_creates_entries_and_exits_from_consecutive_drops() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.004, -0.003, -0.005, 0.006, -0.004, -0.003, -0.004, 0.005],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False, False, True, False]
    assert exit_signals == [False, False, False, True, False, False, False, True]


def test_generate_consecutive_drop_signals_does_not_enter_before_periods_are_ready() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.01, -0.01],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False]
    assert exit_signals == [False, False]


def test_generate_consecutive_drop_signals_does_not_reenter_before_exit() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.004, -0.003, -0.005, -0.006, 0.006],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False]
    assert exit_signals == [False, False, False, False, True]


def test_generate_consecutive_drop_signals_allows_reentry_after_exit() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.004, -0.003, -0.005, 0.006, -0.003, -0.003, -0.004, 0.005],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False, True, False, False, False, True, False]
    assert exit_signals == [False, False, False, True, False, False, False, True]


def test_generate_consecutive_drop_signals_accepts_empty_returns() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals([], 3, -0.003, 0.005)

    assert entry_signals == []
    assert exit_signals == []


def test_generate_consecutive_drop_signals_supports_periods_one() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.003, 0.005],
        1,
        -0.003,
        0.005,
    )

    assert entry_signals == [True, False]
    assert exit_signals == [False, True]


def test_generate_consecutive_drop_signals_handles_exact_threshold_matches() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.003, -0.003, -0.003, 0.005],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False, True, False]
    assert exit_signals == [False, False, False, True]


def test_generate_consecutive_drop_signals_returns_all_false_when_entry_never_occurs() -> None:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        [-0.002, -0.004, -0.002, 0.006],
        3,
        -0.003,
        0.005,
    )

    assert entry_signals == [False, False, False, False]
    assert exit_signals == [False, False, False, False]


def test_generate_consecutive_drop_signals_raises_for_invalid_parameters() -> None:
    with pytest.raises(TypeError, match="consecutive_periods must be an int"):
        generate_consecutive_drop_signals([0.01], 3.0, -0.003, 0.005)

    with pytest.raises(ValueError, match="consecutive_periods must be greater than 0"):
        generate_consecutive_drop_signals([0.01], 0, -0.003, 0.005)

    with pytest.raises(TypeError, match="drop_threshold must be a number"):
        generate_consecutive_drop_signals([0.01], 3, None, 0.005)

    with pytest.raises(TypeError, match="exit_threshold must be a number"):
        generate_consecutive_drop_signals([0.01], 3, -0.003, "0.005")


def test_generate_consecutive_drop_signals_raises_for_invalid_returns_input() -> None:
    with pytest.raises(TypeError, match="returns must be a list"):
        generate_consecutive_drop_signals(None, 3, -0.003, 0.005)

    with pytest.raises(TypeError, match=r"returns\[1\] must be a number"):
        generate_consecutive_drop_signals([0.01, "bad"], 3, -0.003, 0.005)


def test_simulate_threshold_strategy_connects_generated_signals_to_simulation() -> None:
    result = simulate_threshold_strategy(
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

    assert result["entry_threshold"] == 0.01
    assert result["exit_threshold"] == -0.01
    assert result["entry_signals"] == [True, False, True, False]
    assert result["exit_signals"] == [False, True, False, False]
    assert result["final_value"] == 1050.703
    assert result["trade_count"] == 2
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_threshold_strategy_handles_empty_returns() -> None:
    result = simulate_threshold_strategy(
        {
            "simulation_name": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [],
            "entry_threshold": 0.01,
            "exit_threshold": -0.01,
        }
    )

    assert result["entry_signals"] == []
    assert result["exit_signals"] == []
    assert result["trade_count"] == 0
    assert result["final_value"] == 1000.0


def test_simulate_cumulative_drop_strategy_connects_generated_signals_to_simulation() -> None:
    result = simulate_cumulative_drop_strategy(
        {
            "simulation_name": "cumulative_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.002, -0.004, -0.005, 0.006, -0.003, -0.004, -0.004, 0.005],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    )

    assert result["strategy"] == "cumulative_drop"
    assert result["entry_window"] == 3
    assert result["entry_cumulative_threshold"] == -0.01
    assert result["exit_threshold"] == 0.005
    assert result["entry_signals"] == [False, False, True, False, False, False, True, False]
    assert result["exit_signals"] == [False, False, False, True, False, False, False, True]
    assert result["trade_count"] == 2
    assert result["final_value"] == pytest.approx(991.02)
    assert result["final_value"] == pytest.approx(result["equity_curve"][-1])


def test_simulate_cumulative_drop_strategy_handles_empty_returns() -> None:
    result = simulate_cumulative_drop_strategy(
        {
            "simulation_name": "cumulative_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    )

    assert result["entry_signals"] == []
    assert result["exit_signals"] == []
    assert result["trade_count"] == 0
    assert result["final_value"] == 1000.0


def test_simulate_cumulative_drop_strategy_handles_unclosed_trade() -> None:
    result = simulate_cumulative_drop_strategy(
        {
            "simulation_name": "cumulative_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.004, -0.004, -0.003, 0.001],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    )

    assert result["trade_count"] == 1
    assert result["trade_log"][0]["exited"] is False
    assert result["final_value"] == pytest.approx(997.997)


def test_simulate_consecutive_drop_strategy_connects_generated_signals_to_simulation() -> None:
    result = simulate_consecutive_drop_strategy(
        {
            "simulation_name": "consecutive_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.004, -0.003, -0.005, 0.006, -0.004, -0.003, -0.004, 0.005],
            "consecutive_periods": 3,
            "drop_threshold": -0.003,
            "exit_threshold": 0.005,
        }
    )

    assert result["strategy"] == "consecutive_drop"
    assert result["consecutive_periods"] == 3
    assert result["drop_threshold"] == -0.003
    assert result["exit_threshold"] == 0.005
    assert result["entry_signals"] == [False, False, True, False, False, False, True, False]
    assert result["exit_signals"] == [False, False, False, True, False, False, False, True]
    assert result["trade_count"] == 2
    assert result["final_value"] == pytest.approx(991.02)
    assert result["final_value"] == pytest.approx(result["equity_curve"][-1])


def test_simulate_consecutive_drop_strategy_handles_empty_returns() -> None:
    result = simulate_consecutive_drop_strategy(
        {
            "simulation_name": "consecutive_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [],
            "consecutive_periods": 3,
            "drop_threshold": -0.003,
            "exit_threshold": 0.005,
        }
    )

    assert result["entry_signals"] == []
    assert result["exit_signals"] == []
    assert result["trade_count"] == 0
    assert result["final_value"] == 1000.0


def test_simulate_consecutive_drop_strategy_handles_unclosed_trade() -> None:
    result = simulate_consecutive_drop_strategy(
        {
            "simulation_name": "consecutive_drop",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [-0.003, -0.003, -0.003, 0.001],
            "consecutive_periods": 3,
            "drop_threshold": -0.003,
            "exit_threshold": 0.005,
        }
    )

    assert result["trade_count"] == 1
    assert result["trade_log"][0]["exited"] is False
    assert result["final_value"] == pytest.approx(997.9969999999998)


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


def test_simulate_matches_manually_verified_example_with_zero_costs() -> None:
    config = {
        "simulation_name": "example_simulation",
        "initial_cash": 1000000.0,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.01, -0.02, 0.03, 0.01],
        "entry_signals": [True, False, True, False],
        "exit_signals": [False, True, False, False],
    }

    result = simulate(config)

    assert result["fee_rate"] == 0.0
    assert result["slippage_rate"] == 0.0
    assert result["position"] == [True, False, True, True]
    assert result["trade_count"] == 2
    assert result["periods_in_position"] == 3
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 10000.0
    assert result["average_holding_period"] == 1.0
    assert len(result["trade_log"]) == result["trade_count"]
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 10000.0,
        },
        {
            "entry_index": 2,
            "exit_index": None,
            "holding_periods": 2,
            "entered": True,
            "exited": False,
            "pnl_amount": 40703.0,
        },
    ]
    assert result["equity_curve"] == [1000000.0, 1010000.0, 1010000.0, 1040300.0, 1050703.0]
    assert result["final_value"] == 1050703.0
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_returns_expected_result_fields() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05, 0.02],
        "entry_signals": [True, False, False],
        "exit_signals": [False, True, False],
    }

    result = simulate(config)

    assert set(result) == {
        "simulation_name",
        "initial_cash",
        "returns",
        "entry_signals",
        "exit_signals",
        "fee_rate",
        "slippage_rate",
        "position",
        "trade_count",
        "periods_in_position",
        "trade_log",
        "winning_trades",
        "losing_trades",
        "realized_pnl_total",
        "average_holding_period",
        "equity_curve",
        "final_value",
    }
    assert result["simulation_name"] == "test"
    assert result["returns"] == [0.1, -0.05, 0.02]
    assert result["entry_signals"] == [True, False, False]
    assert result["exit_signals"] == [False, True, False]
    assert result["fee_rate"] == 0.0
    assert result["slippage_rate"] == 0.0
    assert result["position"] == [True, False, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 100.0
    assert result["average_holding_period"] == 1.0
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 100.0,
        }
    ]
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1100.0]
    assert result["final_value"] == 1100.0


def test_simulate_creates_one_trade_log_entry_for_single_completed_trade() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, 0.05],
        "entry_signals": [True, False],
        "exit_signals": [False, True],
    }

    result = simulate(config)

    assert result["trade_count"] == 1
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 100.0
    assert result["average_holding_period"] == 1.0
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 100.0,
        }
    ]


def test_simulate_applies_entry_cost_before_return() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.1,
        "slippage_rate": 0.0,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [False],
    }

    result = simulate(config)

    assert result["position"] == [True]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["equity_curve"] == pytest.approx([1000.0, 990.0])
    assert result["final_value"] == pytest.approx(990.0)
    assert result["final_value"] == pytest.approx(result["equity_curve"][-1])


def test_simulate_applies_exit_cost_when_closing_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.1,
        "slippage_rate": 0.0,
        "returns": [0.1, 0.05],
        "entry_signals": [True, False],
        "exit_signals": [False, True],
    }

    result = simulate(config)

    assert result["position"] == [True, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["equity_curve"] == pytest.approx([1000.0, 990.0, 891.0])
    assert result["final_value"] == pytest.approx(891.0)
    assert result["final_value"] == pytest.approx(result["equity_curve"][-1])


def test_simulate_applies_entry_and_exit_costs_with_slippage() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.01,
        "slippage_rate": 0.02,
        "returns": [0.1, 0.05],
        "entry_signals": [True, False],
        "exit_signals": [False, True],
    }

    result = simulate(config)

    assert result["position"] == [True, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["equity_curve"] == [1000.0, 1067.0, 1034.99]
    assert result["final_value"] == 1034.99
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_counts_multiple_entries_as_multiple_trades() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05, 0.02, 0.03, -0.01],
        "entry_signals": [True, False, False, True, False],
        "exit_signals": [False, True, False, False, False],
    }

    result = simulate(config)

    assert result["position"] == [True, False, False, True, True]
    assert result["trade_count"] == 2
    assert result["periods_in_position"] == 3
    assert result["periods_in_position"] == sum(result["position"])
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 100.0
    assert result["average_holding_period"] == 1.0
    assert len(result["trade_log"]) == result["trade_count"]
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 100.0,
        },
        {
            "entry_index": 3,
            "exit_index": None,
            "holding_periods": 2,
            "entered": True,
            "exited": False,
            "pnl_amount": 21.670000000000073,
        },
    ]
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1100.0, 1133.0, 1121.67]
    assert result["final_value"] == 1121.67
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_summary_counts_wins_losses_and_zero_pnl_exits() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, 0.0, -0.1, 0.0, 0.0, 0.0],
        "entry_signals": [True, True, True, False, True, False],
        "exit_signals": [False, True, False, True, False, True],
    }

    result = simulate(config)

    assert result["trade_count"] == 3
    assert len(result["trade_log"]) == 3
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 1
    assert result["realized_pnl_total"] == -10.0
    assert result["average_holding_period"] == 1.0
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 100.0,
        },
        {
            "entry_index": 2,
            "exit_index": 3,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": -110.0,
        },
        {
            "entry_index": 4,
            "exit_index": 5,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 0.0,
        },
    ]


def test_simulate_raises_when_returns_and_entry_signals_lengths_differ() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05],
        "entry_signals": [True],
        "exit_signals": [False, False],
    }

    with pytest.raises(ValueError, match="returns, entry_signals, and exit_signals must have the same length"):
        simulate(config)


def test_simulate_raises_when_returns_and_exit_signals_lengths_differ() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05],
        "entry_signals": [True, False],
        "exit_signals": [False],
    }

    with pytest.raises(ValueError, match="returns, entry_signals, and exit_signals must have the same length"):
        simulate(config)


def test_simulate_raises_when_entry_and_exit_signals_lengths_differ() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05],
        "entry_signals": [True],
        "exit_signals": [False, False, True],
    }

    with pytest.raises(ValueError, match="returns, entry_signals, and exit_signals must have the same length"):
        simulate(config)


def test_simulate_raises_when_fee_rate_is_negative() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": -0.01,
        "slippage_rate": 0.0,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [False],
    }

    with pytest.raises(ValueError, match="fee_rate must be non-negative"):
        simulate(config)


def test_simulate_raises_when_slippage_rate_is_negative() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": -0.01,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [False],
    }

    with pytest.raises(ValueError, match="slippage_rate must be non-negative"):
        simulate(config)


def test_simulate_returns_initial_cash_only_for_empty_returns() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.1,
        "slippage_rate": 0.2,
        "returns": [],
        "entry_signals": [],
        "exit_signals": [],
    }

    result = simulate(config)

    assert result["position"] == []
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["trade_log"] == []
    assert result["winning_trades"] == 0
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 0
    assert result["average_holding_period"] == 0.0
    assert result["equity_curve"] == [1000.0]
    assert result["final_value"] == 1000.0
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_keeps_equity_flat_when_never_in_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.1,
        "slippage_rate": 0.2,
        "returns": [0.1, -0.05, 0.02],
        "entry_signals": [False, False, False],
        "exit_signals": [False, False, False],
    }

    result = simulate(config)

    assert result["position"] == [False, False, False]
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["trade_log"] == []
    assert result["winning_trades"] == 0
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 0
    assert result["average_holding_period"] == 0.0
    assert result["equity_curve"] == [1000.0, 1000.0, 1000.0, 1000.0]
    assert result["final_value"] == 1000.0


def test_simulate_applies_all_returns_when_always_in_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, -0.05, 0.02],
        "entry_signals": [True, False, False],
        "exit_signals": [False, False, False],
    }

    result = simulate(config)

    assert result["position"] == [True, True, True]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 3
    assert result["equity_curve"] == [1000.0, 1100.0, 1045.0, 1065.9]
    assert result["final_value"] == 1065.9


def test_simulate_applies_only_entry_cost_when_position_never_exits() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.01,
        "slippage_rate": 0.02,
        "returns": [0.1, 0.05],
        "entry_signals": [True, False],
        "exit_signals": [False, False],
    }

    result = simulate(config)

    assert result["position"] == [True, True]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 2
    assert result["winning_trades"] == 0
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 0
    assert result["average_holding_period"] == 0.0
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": None,
            "holding_periods": 2,
            "entered": True,
            "exited": False,
            "pnl_amount": pytest.approx(150.35000000000014),
        }
    ]
    assert result["equity_curve"] == pytest.approx([1000.0, 1067.0, 1120.35])
    assert result["final_value"] == pytest.approx(1120.35)


def test_simulate_supports_zero_fee_with_nonzero_slippage() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.01,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [False],
    }

    result = simulate(config)

    assert result["equity_curve"] == [1000.0, 1089.0]
    assert result["final_value"] == 1089.0


def test_simulate_supports_zero_slippage_with_nonzero_fee() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.01,
        "slippage_rate": 0.0,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [False],
    }

    result = simulate(config)

    assert result["equity_curve"] == [1000.0, 1089.0]
    assert result["final_value"] == 1089.0


def test_simulate_exit_wins_when_entry_and_exit_are_both_true() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "returns": [0.1, 0.05],
        "entry_signals": [True, True],
        "exit_signals": [False, True],
    }

    result = simulate(config)

    assert result["position"] == [True, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["winning_trades"] == 1
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 100.0
    assert result["average_holding_period"] == 1.0
    assert result["trade_log"] == [
        {
            "entry_index": 0,
            "exit_index": 1,
            "holding_periods": 1,
            "entered": True,
            "exited": True,
            "pnl_amount": 100.0,
        }
    ]
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0]
    assert result["final_value"] == 1100.0


def test_simulate_same_period_entry_and_exit_results_in_no_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "fee_rate": 0.1,
        "slippage_rate": 0.2,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [True],
    }

    result = simulate(config)

    assert result["position"] == [False]
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["trade_log"] == []
    assert result["winning_trades"] == 0
    assert result["losing_trades"] == 0
    assert result["realized_pnl_total"] == 0
    assert result["average_holding_period"] == 0.0
    assert result["equity_curve"] == [1000.0, 1000.0]
    assert result["final_value"] == 1000.0


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
        "periods_in_position": 1,
        "winning_trades": 1,
        "losing_trades": 0,
        "win_rate": 1.0,
        "realized_pnl_total": 100.0,
        "average_holding_period": 1.0,
    }


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
            "periods_in_position": 1,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "average_holding_period": 0.0,
        },
        {
            "name": "with_cost",
            "final_value": 1089.0,
            "trade_count": 1,
            "periods_in_position": 1,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "average_holding_period": 0.0,
        },
    ]


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
            "periods_in_position": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "average_holding_period": 0.0,
        }
    ]


def test_run_comparisons_supports_mixed_threshold_cumulative_drop_and_consecutive_drop_cases() -> None:
    cases = load_config(Path("config/comparison.example.json"))
    comparisons = run_comparisons(cases)

    assert [comparison["name"] for comparison in comparisons] == [
        "threshold_baseline",
        "cumulative_drop_fast",
        "cumulative_drop_strict",
        "consecutive_drop_fast",
        "consecutive_drop_strict",
    ]
    assert [comparison["strategy"] for comparison in comparisons] == [
        "threshold",
        "cumulative_drop",
        "cumulative_drop",
        "consecutive_drop",
        "consecutive_drop",
    ]
    assert comparisons[1]["trade_count"] >= comparisons[2]["trade_count"]
    assert comparisons[3]["trade_count"] >= comparisons[4]["trade_count"]
    assert comparisons[0]["final_value"] != comparisons[1]["final_value"]
    assert comparisons[1]["entry_window"] == 3
    assert comparisons[2]["entry_window"] == 5
    assert comparisons[3]["consecutive_periods"] == 3
    assert comparisons[4]["consecutive_periods"] == 4
    assert comparisons[0]["entry_threshold"] == 0.01
    assert comparisons[1]["entry_cumulative_threshold"] == -0.01
    assert comparisons[2]["entry_cumulative_threshold"] == -0.026
    assert comparisons[2]["trade_count"] == 0
    assert comparisons[2]["final_value"] == 100000.0
    assert "drop_threshold" in comparisons[3]
    assert comparisons[3]["trade_count"] > 0
    assert comparisons[4]["trade_count"] == 0


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
            "periods_in_position": 2,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "average_holding_period": 0.0,
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    ]


def test_format_comparison_results_returns_json_with_summary_fields() -> None:
    results = [
        {
            "name": "baseline",
            "final_value": 1000.0,
            "trade_count": 0,
            "periods_in_position": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0,
            "average_holding_period": 0.0,
            "strategy": "threshold",
            "entry_threshold": 0.01,
            "exit_threshold": -0.01,
        }
    ]

    formatted = format_comparison_results(results)

    assert '"name": "baseline"' in formatted
    assert '"final_value": 1000.0' in formatted
    assert '"strategy": "threshold"' in formatted
    assert '"entry_threshold": 0.01' in formatted
    assert '"win_rate": 0.0' in formatted
    assert '"average_holding_period": 0.0' in formatted


def test_comparison_main_prints_same_results_as_run_comparisons(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = comparison_main(["--config", "config/comparison.example.json"])

    captured = capsys.readouterr()
    results = load_config(Path("config/comparison.example.json"))

    assert exit_code == 0
    assert captured.out == format_comparison_results(run_comparisons(results)) + "\n"


def test_load_comparison_cases_raises_when_cases_key_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"name": "missing_cases"}', encoding="utf-8")

    with pytest.raises(ValueError, match="comparison config must be a list or include a cases list"):
        load_comparison_cases(str(config_path))


def test_load_comparison_cases_raises_when_cases_is_not_a_list(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"cases": {"name": "invalid"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="comparison config cases must be a list"):
        load_comparison_cases(str(config_path))


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


def test_comparison_main_handles_empty_cases_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"cases": []}', encoding="utf-8")

    exit_code = comparison_main(["--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "[]\n"
