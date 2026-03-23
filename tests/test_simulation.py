from pathlib import Path

from trade_simulator.config import load_config
from trade_simulator.simulation import simulate


def test_package_imports() -> None:
    import trade_simulator  # noqa: F401


def test_load_config() -> None:
    config_path = Path("config/simulation.example.json")
    config = load_config(config_path)

    assert config["simulation_name"] == "example_simulation"
    assert config["initial_cash"] == 1000000


def test_simulate_result_structure() -> None:
    config = {
        "simulation_name": "test",
        "initial_cash": 1000,
        "monthly_return_rate": 0.01,
        "months": 2,
    }

    result = simulate(config)

    assert set(result) == {
        "simulation_name",
        "initial_cash",
        "monthly_return_rate",
        "months",
        "final_value",
    }
    assert result["simulation_name"] == "test"
    assert result["final_value"] > result["initial_cash"]
