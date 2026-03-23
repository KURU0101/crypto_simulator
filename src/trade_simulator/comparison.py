from __future__ import annotations

from trade_simulator.signals import simulate_threshold_strategy
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

    if "entry_threshold" in result and "exit_threshold" in result:
        summary["entry_threshold"] = result["entry_threshold"]
        summary["exit_threshold"] = result["exit_threshold"]

    return summary


def run_case(case: dict) -> dict:
    if "entry_signals" in case and "exit_signals" in case:
        return simulate(case)

    if "entry_threshold" in case and "exit_threshold" in case:
        return simulate_threshold_strategy(case)

    raise ValueError(
        "each comparison case must include entry_signals and exit_signals or entry_threshold and exit_threshold"
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
