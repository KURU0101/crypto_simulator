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


def test_simulate_result_structure() -> None:
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
        "equity_curve",
        "final_value",
    }
    assert result["simulation_name"] == "test"
    assert result["returns"] == [0.1, -0.05, 0.02]
    assert result["entry_signals"] == [True, False, False]
    assert result["exit_signals"] == [False, True, False]
    assert result["position"] == [True, False, False]
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1100.0]
    assert result["final_value"] == 1100.0


def test_simulate_raises_on_length_mismatch() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, -0.05],
        "entry_signals": [True],
        "exit_signals": [False, False],
    }

    with pytest.raises(ValueError, match="returns, entry_signals, and exit_signals must have the same length"):
        simulate(config)


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
    assert result["equity_curve"] == [1000.0, 1000.0]
    assert result["final_value"] == 1000.0
