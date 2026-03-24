from __future__ import annotations

from trade_simulator.signals import (
    simulate_consecutive_drop_strategy,
    simulate_cumulative_drop_strategy,
    simulate_threshold_strategy,
)
from trade_simulator.simulation import simulate

STRATEGY_SPECS: dict[str, dict[str, object]] = {
    "manual": {
        "runner": simulate,
        "required_keys": ("entry_signals", "exit_signals"),
        "error_message": "manual strategy requires entry_signals and exit_signals",
    },
    "threshold": {
        "runner": simulate_threshold_strategy,
        "required_keys": ("entry_threshold", "exit_threshold"),
        "error_message": "threshold strategy requires entry_threshold and exit_threshold",
    },
    "cumulative_drop": {
        "runner": simulate_cumulative_drop_strategy,
        "required_keys": ("entry_window", "entry_cumulative_threshold", "exit_threshold"),
        "error_message": (
            "cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold"
        ),
    },
    "consecutive_drop": {
        "runner": simulate_consecutive_drop_strategy,
        "required_keys": ("consecutive_periods", "drop_threshold", "exit_threshold"),
        "error_message": "consecutive_drop strategy requires consecutive_periods, drop_threshold, and exit_threshold",
    },
}


def _has_required_keys(case: dict, required_keys: tuple[str, ...]) -> bool:
    return all(key in case for key in required_keys)


def _run_registered_strategy(strategy: str, case: dict) -> dict:
    spec = STRATEGY_SPECS[strategy]
    required_keys = spec["required_keys"]
    if not isinstance(required_keys, tuple):
        raise TypeError("required_keys must be a tuple")
    if not _has_required_keys(case, required_keys):
        error_message = spec["error_message"]
        if not isinstance(error_message, str):
            raise TypeError("error_message must be a string")
        raise ValueError(error_message)

    runner = spec["runner"]
    if not callable(runner):
        raise TypeError("runner must be callable")
    return runner(case)


def summarize_case_result(name: str, result: dict) -> dict:
    completed_trade_count = sum(1 for trade in result["trade_log"] if trade["exited"])
    open_trade_count = len(result["trade_log"]) - completed_trade_count
    win_rate = 0.0
    if completed_trade_count:
        win_rate = result["winning_trades"] / completed_trade_count

    average_pnl_per_completed_trade = 0.0
    if completed_trade_count:
        average_pnl_per_completed_trade = result["realized_pnl_total"] / completed_trade_count

    summary = {
        "name": name,
        "final_value": result["final_value"],
        "trade_count": result["trade_count"],
        "completed_trade_count": completed_trade_count,
        "open_trade_count": open_trade_count,
        "periods_in_position": result["periods_in_position"],
        "winning_trades": result["winning_trades"],
        "losing_trades": result["losing_trades"],
        "win_rate": win_rate,
        "realized_pnl_total": result["realized_pnl_total"],
        "total_realized_pnl": result["realized_pnl_total"],
        "average_pnl_per_completed_trade": average_pnl_per_completed_trade,
        "average_holding_period": result["average_holding_period"],
    }

    if "total_cost_amount" in result:
        summary["total_cost_amount"] = result["total_cost_amount"]

    if "strategy" in result:
        summary["strategy"] = result["strategy"]

    if "exit_threshold" in result:
        summary["exit_threshold"] = result["exit_threshold"]

    if "entry_threshold" in result:
        summary["entry_threshold"] = result["entry_threshold"]

    if "entry_window" in result and "entry_cumulative_threshold" in result:
        summary["entry_window"] = result["entry_window"]
        summary["entry_cumulative_threshold"] = result["entry_cumulative_threshold"]

    if "consecutive_periods" in result and "drop_threshold" in result:
        summary["consecutive_periods"] = result["consecutive_periods"]
        summary["drop_threshold"] = result["drop_threshold"]

    return summary


def _true_signal_indexes(signals: object) -> list[int]:
    if not isinstance(signals, list):
        return []
    return [index for index, value in enumerate(signals) if value is True]


def _true_signal_timestamps(signals: object, return_timestamps: object) -> list[str]:
    if not isinstance(signals, list) or not isinstance(return_timestamps, list):
        return []

    timestamps: list[str] = []
    for index, value in enumerate(signals):
        if value is not True:
            continue
        if index >= len(return_timestamps):
            continue
        timestamp = return_timestamps[index]
        if isinstance(timestamp, str):
            timestamps.append(timestamp)
    return timestamps


def _build_external_signal_comparison_metadata(case: dict) -> dict:
    external_signal = case.get("external_signal")
    if not isinstance(external_signal, dict):
        return {}

    metadata: dict[str, object] = {
        "external_signal": {
            "consumption_series_name": external_signal.get("consumption_series_name", "weighted_matching_signal_count"),
            "entry_count_threshold": external_signal.get("entry_count_threshold", 1),
        }
    }

    blended_weights = external_signal.get("blended_weights")
    if isinstance(blended_weights, dict):
        metadata["external_signal"]["blended_weights"] = {
            "symbol": blended_weights.get("symbol"),
            "topic": blended_weights.get("topic"),
        }

    consumption_features = case.get("external_signal_consumption_features")
    if isinstance(consumption_features, dict):
        summary = consumption_features.get("summary")
        if isinstance(summary, dict):
            blended_definition = summary.get("blended_definition")
            if isinstance(blended_definition, dict):
                metadata["external_signal"]["blended_definition"] = dict(blended_definition)

        return_timestamps = consumption_features.get("return_timestamps")
    else:
        return_timestamps = None

    entry_indexes = _true_signal_indexes(case.get("entry_signals"))
    exit_indexes = _true_signal_indexes(case.get("exit_signals"))
    metadata["signal_summary"] = {
        "entry_signal_count": len(entry_indexes),
        "exit_signal_count": len(exit_indexes),
        "entry_signal_indexes": entry_indexes,
        "exit_signal_indexes": exit_indexes,
        "entry_signal_timestamps": _true_signal_timestamps(case.get("entry_signals"), return_timestamps),
        "exit_signal_timestamps": _true_signal_timestamps(case.get("exit_signals"), return_timestamps),
    }
    return metadata


def run_case(case: dict) -> dict:
    strategy = case.get("strategy")

    if strategy is not None:
        if strategy not in STRATEGY_SPECS:
            raise ValueError("strategy must be one of manual, threshold, cumulative_drop, or consecutive_drop")
        return _run_registered_strategy(strategy, case)

    for inferred_strategy, spec in STRATEGY_SPECS.items():
        required_keys = spec["required_keys"]
        if not isinstance(required_keys, tuple):
            raise TypeError("required_keys must be a tuple")
        if _has_required_keys(case, required_keys):
            return _run_registered_strategy(inferred_strategy, case)

    raise ValueError(
        "each comparison case must include manual signals, threshold parameters, cumulative_drop parameters, or consecutive_drop parameters"
    )


def run_comparisons(cases: list[dict]) -> list[dict]:
    summaries = []

    for case in cases:
        if "name" not in case:
            raise ValueError("each comparison case must include a name")

        config = {key: value for key, value in case.items() if key != "name"}
        result = run_case(config)
        summary = summarize_case_result(case["name"], result)
        summary.update(_build_external_signal_comparison_metadata(case))
        summaries.append(summary)

    return summaries
