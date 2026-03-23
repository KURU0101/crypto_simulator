import pytest

from trade_simulator.signals import (
    generate_consecutive_drop_signals,
    generate_cumulative_drop_signals,
    generate_threshold_signals,
    simulate_consecutive_drop_strategy,
    simulate_cumulative_drop_strategy,
    simulate_threshold_strategy,
)


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
