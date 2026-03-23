from pathlib import Path
import pytest

from trade_simulator.config import load_config
from trade_simulator.simulation import simulate


def test_package_imports() -> None:
    import trade_simulator  # noqa: F401


def test_load_config() -> None:
    config_path = Path("config/simulation.example.json")
    config = load_config(config_path)

    assert config["simulation_name"] == "example_simulation"
    assert config["initial_cash"] == 1000000
    assert config["returns"] == [0.01, -0.02, 0.03, 0.01]
    assert config["entry_signals"] == [True, False, True, False]
    assert config["exit_signals"] == [False, True, False, False]


def test_simulate_matches_manually_verified_example() -> None:
    config = {
        "simulation_name": "example_simulation",
        "initial_cash": 1000000.0,
        "returns": [0.01, -0.02, 0.03, 0.01],
        "entry_signals": [True, False, True, False],
        "exit_signals": [False, True, False, False],
    }

    result = simulate(config)

    assert result["position"] == [True, False, True, True]
    assert result["trade_count"] == 2
    assert result["periods_in_position"] == 3
    assert result["equity_curve"] == [1000000.0, 1010000.0, 1010000.0, 1040300.0, 1050703.0]
    assert result["final_value"] == 1050703.0
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_returns_expected_result_fields() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
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
        "position",
        "trade_count",
        "periods_in_position",
        "equity_curve",
        "final_value",
    }
    assert result["simulation_name"] == "test"
    assert result["returns"] == [0.1, -0.05, 0.02]
    assert result["entry_signals"] == [True, False, False]
    assert result["exit_signals"] == [False, True, False]
    assert result["position"] == [True, False, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1100.0]
    assert result["final_value"] == 1100.0


def test_simulate_counts_multiple_entries_as_multiple_trades() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, -0.05, 0.02, 0.03, -0.01],
        "entry_signals": [True, False, False, True, False],
        "exit_signals": [False, True, False, False, False],
    }

    result = simulate(config)

    assert result["position"] == [True, False, False, True, True]
    assert result["trade_count"] == 2
    assert result["periods_in_position"] == 3
    assert result["periods_in_position"] == sum(result["position"])
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1100.0, 1133.0, 1121.67]
    assert result["final_value"] == 1121.67
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_raises_when_returns_and_entry_signals_lengths_differ() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
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
        "returns": [0.1, -0.05],
        "entry_signals": [True],
        "exit_signals": [False, False, True],
    }

    with pytest.raises(ValueError, match="returns, entry_signals, and exit_signals must have the same length"):
        simulate(config)


def test_simulate_returns_initial_cash_only_for_empty_returns() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [],
        "entry_signals": [],
        "exit_signals": [],
    }

    result = simulate(config)

    assert result["position"] == []
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["equity_curve"] == [1000.0]
    assert result["final_value"] == 1000.0
    assert result["final_value"] == result["equity_curve"][-1]


def test_simulate_keeps_equity_flat_when_never_in_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, -0.05, 0.02],
        "entry_signals": [False, False, False],
        "exit_signals": [False, False, False],
    }

    result = simulate(config)

    assert result["position"] == [False, False, False]
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["equity_curve"] == [1000.0, 1000.0, 1000.0, 1000.0]
    assert result["final_value"] == 1000.0


def test_simulate_applies_all_returns_when_always_in_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
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


def test_simulate_exit_wins_when_entry_and_exit_are_both_true() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, 0.05],
        "entry_signals": [True, True],
        "exit_signals": [False, True],
    }

    result = simulate(config)

    assert result["position"] == [True, False]
    assert result["trade_count"] == 1
    assert result["periods_in_position"] == 1
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0]
    assert result["final_value"] == 1100.0


def test_simulate_same_period_entry_and_exit_results_in_no_position() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1],
        "entry_signals": [True],
        "exit_signals": [True],
    }

    result = simulate(config)

    assert result["position"] == [False]
    assert result["trade_count"] == 0
    assert result["periods_in_position"] == 0
    assert result["equity_curve"] == [1000.0, 1000.0]
    assert result["final_value"] == 1000.0
