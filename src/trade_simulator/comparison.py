from __future__ import annotations

from trade_simulator.simulation import simulate


def summarize_case_result(name: str, result: dict) -> dict:
    return {
        "name": name,
        "final_value": result["final_value"],
        "trade_count": result["trade_count"],
        "periods_in_position": result["periods_in_position"],
        "winning_trades": result["winning_trades"],
        "losing_trades": result["losing_trades"],
        "realized_pnl_total": result["realized_pnl_total"],
        "average_holding_period": result["average_holding_period"],
    }


def run_comparisons(cases: list[dict]) -> list[dict]:
    summaries = []

    for case in cases:
        if "name" not in case:
            raise ValueError("each comparison case must include a name")

        config = {key: value for key, value in case.items() if key != "name"}
        result = simulate(config)
        summaries.append(summarize_case_result(case["name"], result))

    return summaries
