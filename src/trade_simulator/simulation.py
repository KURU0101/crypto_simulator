from __future__ import annotations


def simulate(config: dict) -> dict:
    initial_cash = float(config["initial_cash"])
    monthly_return_rate = float(config["monthly_return_rate"])
    months = int(config["months"])

    final_value = initial_cash * ((1 + monthly_return_rate) ** months)

    return {
        "simulation_name": config["simulation_name"],
        "initial_cash": initial_cash,
        "monthly_return_rate": monthly_return_rate,
        "months": months,
        "final_value": final_value,
    }
