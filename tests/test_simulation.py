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
    assert config["position"] == [True, False, True, True]


def test_simulate_result_structure() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, -0.05, 0.02],
        "position": [True, False, True],
    }

    result = simulate(config)

    assert set(result) == {
        "simulation_name",
        "initial_cash",
        "returns",
        "position",
        "equity_curve",
        "final_value",
    }
    assert result["simulation_name"] == "test"
    assert result["returns"] == [0.1, -0.05, 0.02]
    assert result["position"] == [True, False, True]
    assert result["equity_curve"] == [1000.0, 1100.0, 1100.0, 1122.0]
    assert result["final_value"] == 1122.0


def test_simulate_raises_on_length_mismatch() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "returns": [0.1, -0.05],
        "position": [True],
    }

    with pytest.raises(ValueError, match="returns and position must have the same length"):
        simulate(config)
