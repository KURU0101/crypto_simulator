from __future__ import annotations


def simulate(config: dict) -> dict:
    initial_cash = float(config["initial_cash"])
    returns = [float(period_return) for period_return in config["returns"]]
    entry_signals = [bool(signal) for signal in config["entry_signals"]]
    exit_signals = [bool(signal) for signal in config["exit_signals"]]
    fee_rate = float(config.get("fee_rate", 0.0))
    slippage_rate = float(config.get("slippage_rate", 0.0))

    if len(returns) != len(entry_signals) or len(returns) != len(exit_signals):
        raise ValueError("returns, entry_signals, and exit_signals must have the same length")
    if fee_rate < 0:
        raise ValueError("fee_rate must be non-negative")
    if slippage_rate < 0:
        raise ValueError("slippage_rate must be non-negative")

    position = []
    equity_curve = [initial_cash]
    current_value = initial_cash
    is_in_position = False
    trade_log = []
    active_trade = None

    for period_index, (period_return, entry_signal, exit_signal) in enumerate(
        zip(returns, entry_signals, exit_signals)
    ):
        executed_entry = False
        executed_exit = False

        if exit_signal:
            executed_exit = is_in_position
            is_in_position = False
        elif entry_signal:
            executed_entry = not is_in_position
            is_in_position = True

        if executed_exit and active_trade is not None:
            active_trade["exit_index"] = period_index
            active_trade["exited"] = True

        event_count = int(executed_entry) + int(executed_exit)
        if event_count:
            current_value -= current_value * (fee_rate + slippage_rate) * event_count

        if executed_entry:
            active_trade = {
                "entry_index": period_index,
                "exit_index": None,
                "holding_periods": 0,
                "entered": True,
                "exited": False,
                "entry_equity": current_value,
                "pnl_amount": None,
            }
            trade_log.append(active_trade)

        position.append(is_in_position)

        if is_in_position:
            current_value *= 1 + period_return
            if active_trade is not None:
                active_trade["holding_periods"] += 1
        equity_curve.append(current_value)

        if executed_exit and active_trade is not None:
            active_trade["pnl_amount"] = current_value - active_trade["entry_equity"]
            del active_trade["entry_equity"]
            active_trade = None

    trade_count = 0
    was_in_position = False

    for is_in_position in position:
        if is_in_position and not was_in_position:
            trade_count += 1
        was_in_position = is_in_position

    periods_in_position = sum(position)

    if active_trade is not None:
        active_trade["pnl_amount"] = current_value - active_trade["entry_equity"]
        del active_trade["entry_equity"]

    return {
        "simulation_name": config["simulation_name"],
        "initial_cash": initial_cash,
        "returns": returns,
        "entry_signals": entry_signals,
        "exit_signals": exit_signals,
        "fee_rate": fee_rate,
        "slippage_rate": slippage_rate,
        "position": position,
        "trade_count": trade_count,
        "periods_in_position": periods_in_position,
        "trade_log": trade_log,
        "equity_curve": equity_curve,
        "final_value": current_value,
    }
