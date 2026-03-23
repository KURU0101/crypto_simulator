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
    assert config["fee_rate"] == 0.0
    assert config["slippage_rate"] == 0.0
    assert config["returns"] == [0.01, -0.02, 0.03, 0.01]
    assert config["entry_signals"] == [True, False, True, False]
    assert config["exit_signals"] == [False, True, False, False]


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
