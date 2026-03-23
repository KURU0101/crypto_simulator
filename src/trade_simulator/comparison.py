from __future__ import annotations

from trade_simulator.signals import simulate_cumulative_drop_strategy, simulate_threshold_strategy
from trade_simulator.simulation import simulate


def summarize_case_result(name: str, result: dict) -> dict:
    exited_trade_count = sum(1 for trade in result["trade_log"] if trade["exited"])
    win_rate = 0.0
    if exited_trade_count:
        win_rate = result["winning_trades"] / exited_trade_count

    summary = {
        "name": name,
        "final_value": result["final_value"],
        "trade_count": result["trade_count"],
        "periods_in_position": result["periods_in_position"],
        "winning_trades": result["winning_trades"],
        "losing_trades": result["losing_trades"],
        "win_rate": win_rate,
        "realized_pnl_total": result["realized_pnl_total"],
        "average_holding_period": result["average_holding_period"],
    }

    if "strategy" in result:
        summary["strategy"] = result["strategy"]

    if "exit_threshold" in result:
        summary["exit_threshold"] = result["exit_threshold"]

    if "entry_threshold" in result:
        summary["entry_threshold"] = result["entry_threshold"]

    if "entry_window" in result and "entry_cumulative_threshold" in result:
        summary["entry_window"] = result["entry_window"]
        summary["entry_cumulative_threshold"] = result["entry_cumulative_threshold"]

    return summary


def run_case(case: dict) -> dict:
    strategy = case.get("strategy")

    if strategy == "manual":
        if "entry_signals" in case and "exit_signals" in case:
            return simulate(case)
        raise ValueError("manual strategy requires entry_signals and exit_signals")

    if strategy == "threshold":
        if "entry_threshold" in case and "exit_threshold" in case:
            return simulate_threshold_strategy(case)
        raise ValueError("threshold strategy requires entry_threshold and exit_threshold")

    if strategy == "cumulative_drop":
        if all(key in case for key in ("entry_window", "entry_cumulative_threshold", "exit_threshold")):
            return simulate_cumulative_drop_strategy(case)
        raise ValueError(
            "cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold"
        )

    if strategy is not None:
        raise ValueError("strategy must be one of manual, threshold, or cumulative_drop")

    if "entry_signals" in case and "exit_signals" in case:
        return simulate(case)

    if "entry_threshold" in case and "exit_threshold" in case:
        return simulate_threshold_strategy(case)

    if all(key in case for key in ("entry_window", "entry_cumulative_threshold", "exit_threshold")):
        return simulate_cumulative_drop_strategy(case)

    raise ValueError(
        "each comparison case must include manual signals, threshold parameters, or cumulative_drop parameters"
    )


def run_comparisons(cases: list[dict]) -> list[dict]:
    summaries = []

    for case in cases:
        if "name" not in case:
            raise ValueError("each comparison case must include a name")

        config = {key: value for key, value in case.items() if key != "name"}
        result = run_case(config)
        summaries.append(summarize_case_result(case["name"], result))

    return summaries
