from __future__ import annotations

from numbers import Real
from typing import Callable

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


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _generate_window_strategy_signals(
    validated_returns: list[float],
    validated_exit_threshold: float,
    is_entry_ready: Callable[[int], bool],
    should_enter: Callable[[int], bool],
) -> tuple[list[bool], list[bool]]:
    entry_signals = []
    exit_signals = []
    is_in_position = False

    for period_index, period_return in enumerate(validated_returns):
        if is_in_position:
            should_exit = period_return >= validated_exit_threshold
            entry_signals.append(False)
            exit_signals.append(should_exit)
            if should_exit:
                is_in_position = False
            continue

        if not is_entry_ready(period_index):
            entry_signals.append(False)
            exit_signals.append(False)
            continue

        entered = should_enter(period_index)
        entry_signals.append(entered)
        exit_signals.append(False)
        if entered:
            is_in_position = True

    return entry_signals, exit_signals


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


def generate_cumulative_drop_signals(
    returns: object,
    entry_window: object,
    entry_cumulative_threshold: object,
    exit_threshold: object,
) -> tuple[list[bool], list[bool]]:
    validated_returns = _validate_returns(returns)
    validated_entry_window = _validate_positive_int(entry_window, "entry_window")
    validated_entry_cumulative_threshold = _validate_numeric(
        entry_cumulative_threshold,
        "entry_cumulative_threshold",
    )
    validated_exit_threshold = _validate_numeric(exit_threshold, "exit_threshold")

    def is_entry_ready(period_index: int) -> bool:
        return period_index + 1 >= validated_entry_window

    def should_enter(period_index: int) -> bool:
        cumulative_return = sum(
            validated_returns[period_index - validated_entry_window + 1 : period_index + 1]
        )
        return cumulative_return <= validated_entry_cumulative_threshold

    return _generate_window_strategy_signals(
        validated_returns,
        validated_exit_threshold,
        is_entry_ready,
        should_enter,
    )


def generate_consecutive_drop_signals(
    returns: object,
    consecutive_periods: object,
    drop_threshold: object,
    exit_threshold: object,
) -> tuple[list[bool], list[bool]]:
    validated_returns = _validate_returns(returns)
    validated_consecutive_periods = _validate_positive_int(consecutive_periods, "consecutive_periods")
    validated_drop_threshold = _validate_numeric(drop_threshold, "drop_threshold")
    validated_exit_threshold = _validate_numeric(exit_threshold, "exit_threshold")

    def is_entry_ready(period_index: int) -> bool:
        return period_index + 1 >= validated_consecutive_periods

    def should_enter(period_index: int) -> bool:
        recent_returns = validated_returns[
            period_index - validated_consecutive_periods + 1 : period_index + 1
        ]
        return all(period <= validated_drop_threshold for period in recent_returns)

    return _generate_window_strategy_signals(
        validated_returns,
        validated_exit_threshold,
        is_entry_ready,
        should_enter,
    )


def _simulate_with_generated_signals(config: dict, entry_signals: list[bool], exit_signals: list[bool]) -> dict:
    simulation_config = dict(config)
    simulation_config["entry_signals"] = entry_signals
    simulation_config["exit_signals"] = exit_signals
    return simulate(simulation_config)


def simulate_threshold_strategy(config: dict) -> dict:
    entry_signals, exit_signals = generate_threshold_signals(
        config["returns"],
        config["entry_threshold"],
        config["exit_threshold"],
    )

    result = _simulate_with_generated_signals(config, entry_signals, exit_signals)
    result["strategy"] = "threshold"
    result["entry_threshold"] = float(config["entry_threshold"])
    result["exit_threshold"] = float(config["exit_threshold"])
    return result


def simulate_cumulative_drop_strategy(config: dict) -> dict:
    entry_signals, exit_signals = generate_cumulative_drop_signals(
        config["returns"],
        config["entry_window"],
        config["entry_cumulative_threshold"],
        config["exit_threshold"],
    )

    result = _simulate_with_generated_signals(config, entry_signals, exit_signals)
    result["strategy"] = "cumulative_drop"
    result["entry_window"] = int(config["entry_window"])
    result["entry_cumulative_threshold"] = float(config["entry_cumulative_threshold"])
    result["exit_threshold"] = float(config["exit_threshold"])
    return result


def simulate_consecutive_drop_strategy(config: dict) -> dict:
    entry_signals, exit_signals = generate_consecutive_drop_signals(
        config["returns"],
        config["consecutive_periods"],
        config["drop_threshold"],
        config["exit_threshold"],
    )

    result = _simulate_with_generated_signals(config, entry_signals, exit_signals)
    result["strategy"] = "consecutive_drop"
    result["consecutive_periods"] = int(config["consecutive_periods"])
    result["drop_threshold"] = float(config["drop_threshold"])
    result["exit_threshold"] = float(config["exit_threshold"])
    return result
