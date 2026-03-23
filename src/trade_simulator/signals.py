from __future__ import annotations

from numbers import Real

from trade_simulator.simulation import simulate


def _validate_numeric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a number")
    return float(value)


def _validate_returns(returns: object) -> list[float]:
    if not isinstance(returns, list):
        raise TypeError("returns must be a list")

    validated_returns = []
    for index, period_return in enumerate(returns):
        if isinstance(period_return, bool) or not isinstance(period_return, Real):
            raise TypeError(f"returns[{index}] must be a number")
        validated_returns.append(float(period_return))

    return validated_returns


def generate_threshold_signals(
    returns: object,
    entry_threshold: object,
    exit_threshold: object,
) -> tuple[list[bool], list[bool]]:
    validated_returns = _validate_returns(returns)
    validated_entry_threshold = _validate_numeric(entry_threshold, "entry_threshold")
    validated_exit_threshold = _validate_numeric(exit_threshold, "exit_threshold")

    entry_signals = []
    exit_signals = []
    is_in_position = False

    for period_return in validated_returns:
        if not is_in_position and period_return >= validated_entry_threshold:
            entry_signals.append(True)
            exit_signals.append(False)
            is_in_position = True
        elif is_in_position and period_return <= validated_exit_threshold:
            entry_signals.append(False)
            exit_signals.append(True)
            is_in_position = False
        else:
            entry_signals.append(False)
            exit_signals.append(False)

    return entry_signals, exit_signals


def simulate_threshold_strategy(config: dict) -> dict:
    entry_signals, exit_signals = generate_threshold_signals(
        config["returns"],
        config["entry_threshold"],
        config["exit_threshold"],
    )

    simulation_config = dict(config)
    simulation_config["entry_signals"] = entry_signals
    simulation_config["exit_signals"] = exit_signals

    result = simulate(simulation_config)
    result["entry_threshold"] = float(config["entry_threshold"])
    result["exit_threshold"] = float(config["exit_threshold"])
    return result
