from __future__ import annotations


def simulate(config: dict) -> dict:
    initial_cash = float(config["initial_cash"])
    returns = [float(period_return) for period_return in config["returns"]]

    equity_curve = [initial_cash]
    current_value = initial_cash

    for period_return in returns:
        current_value *= 1 + period_return
        equity_curve.append(current_value)

    return {
        "simulation_name": config["simulation_name"],
        "initial_cash": initial_cash,
        "returns": returns,
        "equity_curve": equity_curve,
        "final_value": current_value,
    }
