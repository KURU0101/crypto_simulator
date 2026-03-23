from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Callable, List, Tuple

from trade_simulator.data import build_symbol_work_csv_path, load_data_sources_config, select_data_source
from trade_simulator.data.ohlcv import REQUIRED_OHLCV_COLUMNS, load_returns_from_ohlcv_csv
from trade_simulator.simulation import simulate


SignalPair = Tuple[List[bool], List[bool]]


def _validate_non_negative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")

    numeric_value = float(value)
    if numeric_value < 0:
        raise ValueError(f"{name} must be non-negative")

    return numeric_value


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _validate_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


def load_pseudo_realtime_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("pseudo-realtime config must be a dict")
    if "replay" not in config or not isinstance(config["replay"], dict):
        raise ValueError("pseudo-realtime config must include a replay dict")
    if "strategy" not in config or not isinstance(config["strategy"], dict):
        raise ValueError("pseudo-realtime config must include a strategy dict")

    data_source_config = {}
    if "data_source" in config:
        data_source_config["data_source"] = config["data_source"]
    if "data_sources" in config:
        data_source_config["data_sources"] = config["data_sources"]
    if not data_source_config:
        raise ValueError("pseudo-realtime config must include a data_source dict or data_sources dict")

    data_sources = load_data_sources_config(data_source_config)
    data_source = dict(select_data_source(data_source_config))
    replay = dict(config["replay"])
    strategy = dict(config["strategy"])

    if "warmup_rows" not in replay:
        raise ValueError("replay must include warmup_rows")
    if "work_csv_path" not in replay and "work_dir" not in replay:
        raise ValueError("replay must include work_csv_path or work_dir")

    mode = replay.get("mode", "fast")
    if mode not in {"fast", "realtime"}:
        raise ValueError("replay mode must be one of fast or realtime")

    tick_interval_seconds = replay.get("tick_interval_seconds", 0.0)
    emit_progress_log = replay.get("emit_progress_log", False)

    replay["mode"] = mode
    replay["warmup_rows"] = _validate_positive_int(replay["warmup_rows"], "warmup_rows")
    replay["tick_interval_seconds"] = _validate_non_negative_number(
        tick_interval_seconds,
        "tick_interval_seconds",
    )
    replay["emit_progress_log"] = _validate_bool(emit_progress_log, "emit_progress_log")
    replay["selected_symbol"] = data_source["symbol"]
    replay["available_symbols"] = data_sources["symbols"]
    replay["default_symbol"] = data_sources["default_symbol"]
    if "work_csv_path" in replay:
        if not isinstance(replay["work_csv_path"], str) or not replay["work_csv_path"].strip():
            raise TypeError("work_csv_path must be a non-empty string")
    else:
        work_dir = replay["work_dir"]
        if not isinstance(work_dir, str) or not work_dir.strip():
            raise TypeError("work_dir must be a non-empty string")
        replay["work_csv_path"] = build_symbol_work_csv_path(work_dir, data_source["symbol"])

    return {
        "data_source": data_source,
        "replay": replay,
        "strategy": strategy,
    }


def initialize_work_csv(source_csv_path: str | Path, work_csv_path: str | Path) -> list[str]:
    source_path = Path(source_csv_path)
    work_path = Path(work_csv_path)

    if source_path.resolve() == work_path.resolve():
        raise ValueError("work_csv_path must be different from ohlcv_csv_path")

    with source_path.open("r", encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None:
            raise ValueError("OHLCV csv must include a header")

        missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in reader.fieldnames]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"missing required OHLCV columns: {missing}")

        fieldnames = list(reader.fieldnames)

    work_path.parent.mkdir(parents=True, exist_ok=True)
    with work_path.open("w", encoding="utf-8", newline="") as work_file:
        writer = csv.DictWriter(work_file, fieldnames=fieldnames)
        writer.writeheader()

    return fieldnames


def append_row_to_work_csv(work_csv_path: str | Path, fieldnames: list[str], row: dict) -> None:
    work_path = Path(work_csv_path)
    with work_path.open("a", encoding="utf-8", newline="") as work_file:
        writer = csv.DictWriter(work_file, fieldnames=fieldnames)
        writer.writerow({name: row.get(name, "") for name in fieldnames})


def _build_threshold_signals(
    returns: list[float],
    start_signal_index: int,
    entry_threshold: float,
    exit_threshold: float,
) -> SignalPair:
    entry_signals = [False] * len(returns)
    exit_signals = [False] * len(returns)
    is_in_position = False

    for period_index in range(start_signal_index, len(returns)):
        period_return = returns[period_index]
        if not is_in_position and period_return >= entry_threshold:
            entry_signals[period_index] = True
            is_in_position = True
        elif is_in_position and period_return <= exit_threshold:
            exit_signals[period_index] = True
            is_in_position = False

    return entry_signals, exit_signals


def _build_cumulative_drop_signals(
    returns: list[float],
    start_signal_index: int,
    entry_window: int,
    entry_cumulative_threshold: float,
    exit_threshold: float,
) -> SignalPair:
    entry_signals = [False] * len(returns)
    exit_signals = [False] * len(returns)
    is_in_position = False

    for period_index in range(start_signal_index, len(returns)):
        period_return = returns[period_index]
        if is_in_position:
            should_exit = period_return >= exit_threshold
            exit_signals[period_index] = should_exit
            if should_exit:
                is_in_position = False
            continue

        if period_index + 1 < entry_window:
            continue

        cumulative_return = sum(returns[period_index - entry_window + 1 : period_index + 1])
        should_enter = cumulative_return <= entry_cumulative_threshold
        entry_signals[period_index] = should_enter
        if should_enter:
            is_in_position = True

    return entry_signals, exit_signals


def _build_consecutive_drop_signals(
    returns: list[float],
    start_signal_index: int,
    consecutive_periods: int,
    drop_threshold: float,
    exit_threshold: float,
) -> SignalPair:
    entry_signals = [False] * len(returns)
    exit_signals = [False] * len(returns)
    is_in_position = False

    for period_index in range(start_signal_index, len(returns)):
        period_return = returns[period_index]
        if is_in_position:
            should_exit = period_return >= exit_threshold
            exit_signals[period_index] = should_exit
            if should_exit:
                is_in_position = False
            continue

        if period_index + 1 < consecutive_periods:
            continue

        recent_returns = returns[period_index - consecutive_periods + 1 : period_index + 1]
        should_enter = all(period <= drop_threshold for period in recent_returns)
        entry_signals[period_index] = should_enter
        if should_enter:
            is_in_position = True

    return entry_signals, exit_signals


def _build_strategy_signals(strategy_config: dict, returns: list[float], warmup_rows: int) -> SignalPair:
    strategy = strategy_config.get("strategy")
    start_signal_index = max(warmup_rows - 1, 0)

    if strategy == "manual":
        if "entry_signals" not in strategy_config or "exit_signals" not in strategy_config:
            raise ValueError("manual strategy requires entry_signals and exit_signals")
        entry_signals = [bool(signal) for signal in strategy_config["entry_signals"]]
        exit_signals = [bool(signal) for signal in strategy_config["exit_signals"]]
        if len(returns) != len(entry_signals) or len(returns) != len(exit_signals):
            raise ValueError("manual strategy requires signals aligned with returns")
        for signal_index in range(min(start_signal_index, len(entry_signals))):
            entry_signals[signal_index] = False
            exit_signals[signal_index] = False
        return entry_signals, exit_signals

    if strategy == "threshold":
        if "entry_threshold" not in strategy_config or "exit_threshold" not in strategy_config:
            raise ValueError("threshold strategy requires entry_threshold and exit_threshold")
        return _build_threshold_signals(
            returns,
            start_signal_index,
            float(strategy_config["entry_threshold"]),
            float(strategy_config["exit_threshold"]),
        )

    if strategy == "cumulative_drop":
        required_keys = ("entry_window", "entry_cumulative_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError(
                "cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold"
            )
        return _build_cumulative_drop_signals(
            returns,
            start_signal_index,
            _validate_positive_int(strategy_config["entry_window"], "entry_window"),
            float(strategy_config["entry_cumulative_threshold"]),
            float(strategy_config["exit_threshold"]),
        )

    if strategy == "consecutive_drop":
        required_keys = ("consecutive_periods", "drop_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError(
                "consecutive_drop strategy requires consecutive_periods, drop_threshold, and exit_threshold"
            )
        return _build_consecutive_drop_signals(
            returns,
            start_signal_index,
            _validate_positive_int(strategy_config["consecutive_periods"], "consecutive_periods"),
            float(strategy_config["drop_threshold"]),
            float(strategy_config["exit_threshold"]),
        )

    raise ValueError("strategy must be one of manual, threshold, cumulative_drop, or consecutive_drop")


def _build_strategy_result(strategy_config: dict, returns: list[float], warmup_rows: int) -> dict:
    entry_signals, exit_signals = _build_strategy_signals(strategy_config, returns, warmup_rows)

    simulation_config = dict(strategy_config)
    simulation_config["returns"] = list(returns)
    simulation_config["entry_signals"] = entry_signals
    simulation_config["exit_signals"] = exit_signals
    if "simulation_name" not in simulation_config:
        simulation_config["simulation_name"] = simulation_config.get("name", "pseudo_realtime_replay")

    result = simulate(simulation_config)

    strategy = strategy_config.get("strategy")
    if strategy is not None:
        result["strategy"] = strategy
    if "entry_threshold" in strategy_config:
        result["entry_threshold"] = float(strategy_config["entry_threshold"])
    if "exit_threshold" in strategy_config:
        result["exit_threshold"] = float(strategy_config["exit_threshold"])
    if "entry_window" in strategy_config:
        result["entry_window"] = int(strategy_config["entry_window"])
    if "entry_cumulative_threshold" in strategy_config:
        result["entry_cumulative_threshold"] = float(strategy_config["entry_cumulative_threshold"])
    if "consecutive_periods" in strategy_config:
        result["consecutive_periods"] = int(strategy_config["consecutive_periods"])
    if "drop_threshold" in strategy_config:
        result["drop_threshold"] = float(strategy_config["drop_threshold"])

    return result


def _derive_signal_reason_code(strategy: str | None, entry_signal: bool, exit_signal: bool) -> str:
    if entry_signal:
        if strategy == "manual":
            return "manual_entry_signal"
        if strategy == "threshold":
            return "threshold_entry_signal"
        if strategy == "cumulative_drop":
            return "cumulative_drop_entry_signal"
        if strategy == "consecutive_drop":
            return "consecutive_drop_entry_signal"
        return "entry_signal"

    if exit_signal:
        if strategy == "manual":
            return "manual_exit_signal"
        if strategy == "threshold":
            return "threshold_exit_signal"
        if strategy == "cumulative_drop":
            return "cumulative_drop_exit_signal"
        if strategy == "consecutive_drop":
            return "consecutive_drop_exit_signal"
        return "exit_signal"

    return "no_signal"


def _derive_action_reason_code(
    previous_in_position: bool,
    current_in_position: bool,
    entry_signal: bool,
    exit_signal: bool,
) -> str:
    if not previous_in_position and current_in_position:
        return "enter_position"
    if previous_in_position and not current_in_position:
        return "exit_position"
    if previous_in_position and current_in_position:
        if exit_signal:
            return "exit_signal_ignored"
        return "hold_position"
    if entry_signal:
        return "entry_signal_ignored"
    return "stay_flat"


def _build_warmup_decision_entry(
    tick_index: int,
    ohlcv_timestamp: str,
    initial_cash: float,
) -> tuple[dict, dict]:
    decision_entry = {
        "tick_index": tick_index,
        "phase": "warmup",
        "ohlcv_timestamp": ohlcv_timestamp,
        "return_timestamp": None,
        "latest_return": None,
        "entry_signal": False,
        "exit_signal": False,
        "signal_reason_code": "warmup_pending",
        "action_reason_code": "warmup_skip",
        "position_after_tick": False,
        "equity_after_tick": initial_cash,
    }
    equity_entry = {
        "tick_index": tick_index,
        "phase": "warmup",
        "ohlcv_timestamp": ohlcv_timestamp,
        "return_timestamp": None,
        "equity": initial_cash,
        "in_position": False,
    }
    return decision_entry, equity_entry


def run_pseudo_realtime_replay(
    config: dict,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict:
    validated_config = load_pseudo_realtime_config(config)
    data_source = validated_config["data_source"]
    replay_config = validated_config["replay"]
    strategy_config = validated_config["strategy"]

    source_csv_path = data_source["ohlcv_csv_path"]
    work_csv_path = replay_config["work_csv_path"]
    warmup_rows = replay_config["warmup_rows"]
    mode = replay_config["mode"]
    tick_interval_seconds = replay_config["tick_interval_seconds"]
    emit_progress_log = replay_config["emit_progress_log"]
    initial_cash = float(strategy_config["initial_cash"])

    if sleep_fn is None:
        sleep_fn = time.sleep

    fieldnames = initialize_work_csv(source_csv_path, work_csv_path)

    decision_log = []
    equity_history = []
    progress_log = []
    latest_result = None
    appended_rows = 0

    source_path = Path(source_csv_path)
    with source_path.open("r", encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        current_row = next(reader, None)

        while current_row is not None:
            next_row = next(reader, None)
            append_row_to_work_csv(work_csv_path, fieldnames, current_row)
            appended_rows += 1

            ohlcv_timestamp = current_row["timestamp"]

            if appended_rows <= warmup_rows:
                decision_entry, equity_entry = _build_warmup_decision_entry(
                    tick_index=appended_rows - 1,
                    ohlcv_timestamp=ohlcv_timestamp,
                    initial_cash=initial_cash,
                )
            else:
                returns_payload = load_returns_from_ohlcv_csv(work_csv_path)
                latest_result = _build_strategy_result(
                    strategy_config,
                    returns_payload["returns"],
                    warmup_rows=warmup_rows,
                )

                entry_signal = latest_result["entry_signals"][-1]
                exit_signal = latest_result["exit_signals"][-1]
                current_in_position = latest_result["position"][-1]
                previous_in_position = False
                if latest_result["position"][:-1]:
                    previous_in_position = latest_result["position"][-2]

                decision_entry = {
                    "tick_index": appended_rows - 1,
                    "phase": "replay",
                    "ohlcv_timestamp": ohlcv_timestamp,
                    "return_timestamp": returns_payload["return_timestamps"][-1],
                    "latest_return": latest_result["returns"][-1],
                    "entry_signal": entry_signal,
                    "exit_signal": exit_signal,
                    "signal_reason_code": _derive_signal_reason_code(
                        latest_result.get("strategy"),
                        entry_signal,
                        exit_signal,
                    ),
                    "action_reason_code": _derive_action_reason_code(
                        previous_in_position,
                        current_in_position,
                        entry_signal,
                        exit_signal,
                    ),
                    "position_after_tick": current_in_position,
                    "equity_after_tick": latest_result["final_value"],
                }
                equity_entry = {
                    "tick_index": appended_rows - 1,
                    "phase": "replay",
                    "ohlcv_timestamp": ohlcv_timestamp,
                    "return_timestamp": returns_payload["return_timestamps"][-1],
                    "equity": latest_result["final_value"],
                    "in_position": current_in_position,
                }

            decision_log.append(decision_entry)
            equity_history.append(equity_entry)

            if emit_progress_log:
                progress_log.append(
                    {
                        "tick_index": appended_rows - 1,
                        "phase": decision_entry["phase"],
                        "ohlcv_timestamp": ohlcv_timestamp,
                        "processed_ohlcv_points": appended_rows,
                        "work_csv_path": str(work_csv_path),
                    }
                )

            if mode == "realtime" and tick_interval_seconds > 0 and next_row is not None:
                sleep_fn(tick_interval_seconds)

            current_row = next_row

    if appended_rows == 0:
        raise ValueError("source OHLCV csv must include at least one data row")
    if appended_rows <= warmup_rows:
        raise ValueError("source OHLCV csv must include more rows than warmup_rows")

    final_result = latest_result
    if final_result is None:
        raise ValueError("pseudo-realtime replay did not produce an evaluated result")

    summary = {
        "simulation_name": final_result["simulation_name"],
        "symbol": data_source.get("symbol", "BTC/USDT"),
        "available_symbols": replay_config["available_symbols"],
        "source_csv_path": source_csv_path,
        "work_csv_path": work_csv_path,
        "mode": mode,
        "warmup_rows": warmup_rows,
        "tick_interval_seconds": tick_interval_seconds,
        "total_ohlcv_points": appended_rows,
        "evaluated_ticks": appended_rows - warmup_rows,
        "final_value": final_result["final_value"],
        "trade_count": final_result["trade_count"],
        "periods_in_position": final_result["periods_in_position"],
        "winning_trades": final_result["winning_trades"],
        "losing_trades": final_result["losing_trades"],
        "realized_pnl_total": final_result["realized_pnl_total"],
        "open_position_at_end": bool(final_result["position"] and final_result["position"][-1]),
    }

    payload = {
        "data_source": {
            "symbol": data_source.get("symbol", "BTC/USDT"),
            "ohlcv_csv_path": source_csv_path,
            "work_csv_path": work_csv_path,
        },
        "replay": {
            "mode": mode,
            "warmup_rows": warmup_rows,
            "tick_interval_seconds": tick_interval_seconds,
            "evaluation_mode": "reload_work_csv_and_recompute_full_history_each_tick",
            "emit_progress_log": emit_progress_log,
        },
        "strategy": {
            key: value
            for key, value in strategy_config.items()
            if key not in {"returns", "entry_signals", "exit_signals"}
        },
        "summary": summary,
        "decision_log": decision_log,
        "trade_log": final_result["trade_log"],
        "equity_history": equity_history,
        "progress_log": progress_log,
    }

    return payload
