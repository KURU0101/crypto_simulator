from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trade_simulator.data.ohlcv import build_close_to_close_returns, normalize_ohlcv_rows
from trade_simulator.simulation import simulate


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
RUN_DIRECTORY_NAME_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")


class LiveDecisionRunnerError(Exception):
    """Base exception for live decision runner failures."""


class FetchOHLCVError(LiveDecisionRunnerError):
    """Raised when OHLCV fetching fails."""

    def __init__(self, message: str, *, status_code: int | None = None, headers: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


def _validate_non_negative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    numeric_value = float(value)
    if numeric_value < 0:
        raise ValueError(f"{name} must be non-negative")
    if not math.isfinite(numeric_value):
        raise ValueError(f"{name} must be finite")
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


def _validate_live_data_source_entry(source: object, *, entry_name: str) -> dict:
    if not isinstance(source, dict):
        raise ValueError(f"{entry_name} must be a dict")
    if "symbol" not in source:
        raise ValueError(f"{entry_name} must include symbol")
    if "interval" not in source:
        raise ValueError(f"{entry_name} must include interval")
    if not isinstance(source["symbol"], str) or not source["symbol"].strip():
        raise TypeError(f"{entry_name} symbol must be a non-empty string")
    if not isinstance(source["interval"], str) or not source["interval"].strip():
        raise TypeError(f"{entry_name} interval must be a non-empty string")

    normalized_source = dict(source)
    normalized_source["symbol"] = source["symbol"].strip()
    normalized_source["interval"] = source["interval"].strip()
    if normalized_source["interval"] != "1m":
        raise ValueError(f"{entry_name} interval must be 1m")
    normalized_source["limit"] = _validate_positive_int(normalized_source.get("limit", 120), f"{entry_name} limit")
    return normalized_source


def _load_live_data_sources_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("live decision runner config must be a dict")

    if "data_sources" in config:
        raw_data_sources = config["data_sources"]
        if not isinstance(raw_data_sources, dict):
            raise ValueError("data_sources must be a dict")
        if "symbols" not in raw_data_sources:
            raise ValueError("data_sources must include symbols")
        if not isinstance(raw_data_sources["symbols"], list):
            raise ValueError("data_sources symbols must be a list")
        sources = [
            _validate_live_data_source_entry(source, entry_name=f"data_sources.symbols[{index}]")
            for index, source in enumerate(raw_data_sources["symbols"])
        ]
        default_symbol = raw_data_sources.get("default_symbol")
    elif "data_source" in config:
        sources = [_validate_live_data_source_entry(config["data_source"], entry_name="data_source")]
        default_symbol = sources[0]["symbol"]
    else:
        raise ValueError("live decision runner config must include a data_source dict or data_sources dict")

    if not sources:
        raise ValueError("at least one live data source is required")

    symbols = [source["symbol"] for source in sources]
    if len(set(symbols)) != len(symbols):
        raise ValueError("symbol must be unique across live data sources")

    if default_symbol is None:
        default_symbol = symbols[0]
    if not isinstance(default_symbol, str) or not default_symbol.strip():
        raise TypeError("default_symbol must be a non-empty string")
    if default_symbol not in symbols:
        raise ValueError("default_symbol must match one of the configured symbols")

    return {
        "default_symbol": default_symbol,
        "symbols": list(symbols),
        "sources": sources,
        "sources_by_symbol": {source["symbol"]: source for source in sources},
    }


def _select_live_data_source(config: object, symbol: str | None = None) -> tuple[dict, dict]:
    data_sources = _load_live_data_sources_config(config)
    selected_symbol = symbol or data_sources["default_symbol"]
    if selected_symbol not in data_sources["sources_by_symbol"]:
        raise ValueError(f"symbol must be one of: {', '.join(data_sources['symbols'])}")
    return dict(data_sources["sources_by_symbol"][selected_symbol]), data_sources


def load_live_decision_runner_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("live decision runner config must be a dict")

    required_sections = ("runtime", "strategy", "output", "retry")
    for section in required_sections:
        if section not in config or not isinstance(config[section], dict):
            raise ValueError(f"live decision runner config must include a {section} dict")

    data_source, data_sources = _select_live_data_source(config)
    runtime = dict(config["runtime"])
    strategy = dict(config["strategy"])
    output = dict(config["output"])
    retry = dict(config["retry"])
    runtime["poll_interval_seconds"] = _validate_non_negative_number(
        runtime.get("poll_interval_seconds", 60),
        "poll_interval_seconds",
    )
    runtime["duration_seconds"] = _validate_non_negative_number(
        runtime.get("duration_seconds", 600),
        "duration_seconds",
    )
    runtime["emit_progress_log"] = _validate_bool(runtime.get("emit_progress_log", True), "emit_progress_log")
    runtime["warmup_candles"] = _validate_positive_int(runtime.get("warmup_candles", 1), "warmup_candles")

    if "output_dir" not in output:
        raise ValueError("output must include output_dir")
    output["first_n"] = _validate_positive_int(output.get("first_n", 10), "first_n")
    output["last_n"] = _validate_positive_int(output.get("last_n", 10), "last_n")
    output["max_run_directories"] = _validate_positive_int(
        output.get("max_run_directories", 10),
        "max_run_directories",
    )

    retry["max_attempts"] = _validate_positive_int(retry.get("max_attempts", 2), "max_attempts")
    retry["initial_backoff_seconds"] = _validate_non_negative_number(
        retry.get("initial_backoff_seconds", 5.0),
        "initial_backoff_seconds",
    )
    retry["backoff_multiplier"] = _validate_non_negative_number(
        retry.get("backoff_multiplier", 2.0),
        "backoff_multiplier",
    )
    retry["max_backoff_seconds"] = _validate_non_negative_number(
        retry.get("max_backoff_seconds", 60.0),
        "max_backoff_seconds",
    )

    return {
        "data_source": data_source,
        "data_sources": data_sources,
        "runtime": runtime,
        "strategy": strategy,
        "output": output,
        "retry": retry,
    }


def _utc_now_iso(now_fn: Callable[[], float]) -> str:
    return datetime.fromtimestamp(now_fn(), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_from_milliseconds(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id_from_iso8601(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_retry_after_seconds(headers: dict[str, str]) -> float | None:
    retry_after = headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        retry_after_seconds = float(retry_after)
    except ValueError:
        return None
    if retry_after_seconds < 0:
        return None
    return retry_after_seconds


def fetch_binance_spot_klines(symbol: str, interval: str, limit: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
    )
    url = f"{BINANCE_SPOT_KLINES_URL}?{query}"
    request = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = {key: value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        headers = {key: value for key, value in error.headers.items()}
        body = error.read().decode("utf-8", errors="ignore")
        message = f"failed to fetch klines: HTTP {error.code}"
        if body:
            message = f"{message}: {body}"
        raise FetchOHLCVError(message, status_code=error.code, headers=headers) from error
    except urllib.error.URLError as error:
        raise FetchOHLCVError(f"failed to fetch klines: {error.reason}") from error
    except TimeoutError as error:
        raise FetchOHLCVError("failed to fetch klines: timeout") from error
    except json.JSONDecodeError as error:
        raise FetchOHLCVError("failed to decode klines response as JSON") from error

    if not isinstance(payload, list):
        raise FetchOHLCVError("kline response must be a list", headers=headers)

    rows = []
    for index, item in enumerate(payload):
        if not isinstance(item, list) or len(item) < 7:
            raise FetchOHLCVError(f"kline response item must be a list with at least 7 fields at index {index}")
        if not isinstance(item[0], int) or not isinstance(item[6], int):
            raise FetchOHLCVError(f"kline response timestamps must be integers at index {index}")

        rows.append(
            {
                "timestamp": _timestamp_from_milliseconds(item[0]),
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
                "close_time_ms": item[6],
            }
        )

    return {
        "rows": rows,
        "headers": headers,
        "used_weight_1m": headers.get("X-MBX-USED-WEIGHT-1M"),
    }


def _select_confirmed_rows(rows: list[dict], now_timestamp_ms: int) -> list[dict]:
    confirmed_rows = []
    for row in rows:
        close_time_ms = row.get("close_time_ms")
        if not isinstance(close_time_ms, int):
            raise ValueError("close_time_ms must be an int")
        if close_time_ms <= now_timestamp_ms:
            confirmed_rows.append({key: value for key, value in row.items() if key != "close_time_ms"})

    if not confirmed_rows:
        return []

    return normalize_ohlcv_rows(confirmed_rows)


def _build_strategy_result(
    strategy_config: dict,
    returns: list[float],
    *,
    start_signal_index: int,
) -> dict:
    strategy_name = strategy_config.get("strategy")
    if strategy_name == "threshold":
        if "entry_threshold" not in strategy_config or "exit_threshold" not in strategy_config:
            raise ValueError("threshold strategy requires entry_threshold and exit_threshold")
        entry_signals, exit_signals = _build_threshold_signals(
            returns,
            start_signal_index,
            float(strategy_config["entry_threshold"]),
            float(strategy_config["exit_threshold"]),
        )
    elif strategy_name == "cumulative_drop":
        required_keys = ("entry_window", "entry_cumulative_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError(
                "cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold"
            )
        entry_signals, exit_signals = _build_cumulative_drop_signals(
            returns,
            start_signal_index,
            _validate_positive_int(strategy_config["entry_window"], "entry_window"),
            float(strategy_config["entry_cumulative_threshold"]),
            float(strategy_config["exit_threshold"]),
        )
    elif strategy_name == "consecutive_drop":
        required_keys = ("consecutive_periods", "drop_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError("consecutive_drop strategy requires consecutive_periods, drop_threshold, and exit_threshold")
        entry_signals, exit_signals = _build_consecutive_drop_signals(
            returns,
            start_signal_index,
            _validate_positive_int(strategy_config["consecutive_periods"], "consecutive_periods"),
            float(strategy_config["drop_threshold"]),
            float(strategy_config["exit_threshold"]),
        )
    else:
        raise ValueError("strategy must be one of threshold, cumulative_drop, or consecutive_drop")

    simulation_config = dict(strategy_config)
    simulation_config["returns"] = list(returns)
    simulation_config["entry_signals"] = entry_signals
    simulation_config["exit_signals"] = exit_signals
    if "simulation_name" not in simulation_config:
        simulation_config["simulation_name"] = simulation_config.get("name", "live_decision_runner")

    result = simulate(simulation_config)
    result["strategy"] = strategy_name
    return result


def _derive_signal_reason_code(strategy_name: str | None, entry_signal: bool, exit_signal: bool) -> str:
    if entry_signal:
        if strategy_name == "threshold":
            return "threshold_entry_signal"
        if strategy_name == "cumulative_drop":
            return "cumulative_drop_entry_signal"
        if strategy_name == "consecutive_drop":
            return "consecutive_drop_entry_signal"
        return "entry_signal"

    if exit_signal:
        if strategy_name == "threshold":
            return "threshold_exit_signal"
        if strategy_name == "cumulative_drop":
            return "cumulative_drop_exit_signal"
        if strategy_name == "consecutive_drop":
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


def _build_progress_entry(
    *,
    poll_index: int,
    fetched_at: str,
    reason_code: str,
    confirmed_rows: int,
    last_confirmed_timestamp: str | None,
    used_weight_1m: str | None,
    detail: str | None = None,
) -> dict:
    entry = {
        "poll_index": poll_index,
        "fetched_at": fetched_at,
        "reason_code": reason_code,
        "confirmed_rows": confirmed_rows,
        "last_confirmed_timestamp": last_confirmed_timestamp,
        "used_weight_1m": used_weight_1m,
    }
    if detail is not None:
        entry["detail"] = detail
    return entry


def _derive_cash_value(latest_result: dict | None, initial_cash: float) -> float:
    if latest_result is None:
        return initial_cash

    position = latest_result.get("position", [])
    is_in_position = bool(position and position[-1])
    if is_in_position:
        return 0.0
    return float(latest_result["final_value"])


def _derive_session_end_state(
    *,
    initial_cash: float,
    latest_result: dict | None,
) -> dict:
    if latest_result is None:
        return {
            "equity": initial_cash,
            "cash": initial_cash,
            "trade_count": 0,
            "realized_pnl_total": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "open_position": False,
        }

    return {
        "equity": float(latest_result["final_value"]),
        "cash": _derive_cash_value(latest_result, initial_cash),
        "trade_count": int(latest_result["trade_count"]),
        "realized_pnl_total": float(latest_result["realized_pnl_total"]),
        "winning_trades": int(latest_result["winning_trades"]),
        "losing_trades": int(latest_result["losing_trades"]),
        "open_position": bool(latest_result["position"] and latest_result["position"][-1]),
    }


def _build_flat_session_start_state(initial_cash: float) -> dict:
    return {
        "equity": initial_cash,
        "cash": initial_cash,
        "trade_count": 0,
        "realized_pnl_total": 0.0,
        "winning_trades": 0,
        "losing_trades": 0,
        "open_position": False,
    }


def _build_threshold_signals(
    returns: list[float],
    start_signal_index: int,
    entry_threshold: float,
    exit_threshold: float,
) -> tuple[list[bool], list[bool]]:
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
) -> tuple[list[bool], list[bool]]:
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
) -> tuple[list[bool], list[bool]]:
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


def build_live_progress_stdout_payload(
    *,
    poll_index: int,
    fetched_at: str,
    latest_result: dict | None,
    initial_cash: float,
    reason_code: str,
    last_confirmed_timestamp: str | None,
    symbol: str,
) -> dict:
    session_end_state = _derive_session_end_state(
        initial_cash=initial_cash,
        latest_result=latest_result,
    )

    return {
        "type": "live_progress",
        "symbol": symbol,
        "poll_index": poll_index,
        "fetched_at": fetched_at,
        "reason_code": reason_code,
        "trade_count": session_end_state["trade_count"],
        "equity": session_end_state["equity"],
        "cash": session_end_state["cash"],
        "last_confirmed_timestamp": last_confirmed_timestamp,
    }


def format_live_progress_stdout(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _append_decision_entries(
    *,
    strategy_config: dict,
    confirmed_rows: list[dict],
    session_start_index: int,
    latest_row: dict,
    decision_log: list[dict],
    equity_history: list[dict],
    poll_index: int,
    fetched_at: str,
    latest_weight_1m: str | None,
) -> dict:
    returns_payload = build_close_to_close_returns(confirmed_rows)
    latest_result = _build_strategy_result(
        strategy_config,
        returns_payload["returns"],
        start_signal_index=session_start_index,
    )
    entry_signal = latest_result["entry_signals"][-1]
    exit_signal = latest_result["exit_signals"][-1]
    current_in_position = latest_result["position"][-1]
    previous_in_position = False
    if latest_result["position"][:-1]:
        previous_in_position = latest_result["position"][-2]

    decision_log.append(
        {
            "decision_index": len(decision_log),
            "poll_index": poll_index,
            "phase": "live",
            "fetched_at": fetched_at,
            "ohlcv_timestamp": latest_row["timestamp"],
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
            "cash_after_tick": _derive_cash_value(latest_result, float(strategy_config["initial_cash"])),
            "used_weight_1m": latest_weight_1m,
        }
    )
    equity_history.append(
        {
            "decision_index": len(decision_log) - 1,
            "poll_index": poll_index,
            "phase": "live",
            "fetched_at": fetched_at,
            "ohlcv_timestamp": latest_row["timestamp"],
            "return_timestamp": returns_payload["return_timestamps"][-1],
            "equity": latest_result["final_value"],
            "cash": _derive_cash_value(latest_result, float(strategy_config["initial_cash"])),
            "in_position": current_in_position,
        }
    )
    return latest_result


def _run_fetch_with_retry(
    *,
    fetch_klines_fn: Callable[[str, str, int], dict],
    symbol: str,
    interval: str,
    limit: int,
    retry_config: dict,
    sleep_fn: Callable[[float], None],
    now_fn: Callable[[], float],
    counters: dict,
) -> dict:
    delay_seconds = float(retry_config["initial_backoff_seconds"])
    max_attempts = int(retry_config["max_attempts"])
    max_backoff_seconds = float(retry_config["max_backoff_seconds"])
    backoff_multiplier = float(retry_config["backoff_multiplier"])

    last_error: Exception | None = None

    for attempt_index in range(max_attempts):
        try:
            return fetch_klines_fn(symbol, interval, limit)
        except KeyboardInterrupt:
            raise
        except FetchOHLCVError as error:
            counters["fetch_failures"] += 1
            last_error = error

            if error.status_code == 429:
                counters["rate_limit_events"] += 1

            if attempt_index + 1 >= max_attempts:
                break

            if error.status_code == 429:
                retry_after_seconds = _parse_retry_after_seconds(error.headers)
                sleep_seconds = delay_seconds
                if retry_after_seconds is not None:
                    sleep_seconds = max(sleep_seconds, retry_after_seconds)
            else:
                sleep_seconds = delay_seconds

            remaining_seconds = max(0.0, float(retry_config.get("duration_seconds", 0.0)) - (now_fn() - counters["started_at"]))
            sleep_fn(min(sleep_seconds, remaining_seconds) if remaining_seconds > 0 else sleep_seconds)
            delay_seconds = min(max_backoff_seconds, max(delay_seconds * backoff_multiplier, delay_seconds))
        except Exception as error:
            counters["fetch_failures"] += 1
            last_error = error
            if attempt_index + 1 >= max_attempts:
                break
            remaining_seconds = max(0.0, float(retry_config.get("duration_seconds", 0.0)) - (now_fn() - counters["started_at"]))
            sleep_fn(min(delay_seconds, remaining_seconds) if remaining_seconds > 0 else delay_seconds)
            delay_seconds = min(max_backoff_seconds, max(delay_seconds * backoff_multiplier, delay_seconds))

    if last_error is None:
        raise FetchOHLCVError("failed to fetch klines")
    if isinstance(last_error, FetchOHLCVError):
        raise last_error
    raise FetchOHLCVError(str(last_error)) from last_error


def _build_runtime_payload(
    *,
    config: dict,
    confirmed_rows: list[dict],
    decision_log: list[dict],
    equity_history: list[dict],
    progress_log: list[dict],
    latest_result: dict | None,
    status: str,
    stop_reason: str,
    started_at: str,
    ended_at: str,
    last_confirmed_timestamp: str | None,
    poll_count: int,
    counters: dict,
    error_message: str | None,
    run_context: dict | None,
) -> dict:
    strategy_config = config["strategy"]
    data_source = config["data_source"]
    data_sources = config["data_sources"]
    output = config["output"]
    initial_cash = float(strategy_config["initial_cash"])
    session_start_state = _build_flat_session_start_state(initial_cash)
    session_end_state = _derive_session_end_state(
        initial_cash=initial_cash,
        latest_result=latest_result,
    )

    return_timestamps: list[str] = []
    if len(confirmed_rows) >= 2:
        return_timestamps = build_close_to_close_returns(confirmed_rows)["return_timestamps"]
    trade_log: list[dict] = []
    if latest_result is not None:
        for trade in latest_result["trade_log"]:
            session_trade_entry = dict(trade)
            session_trade_entry["session_trade_index"] = len(trade_log)
            session_trade_entry["entry_return_timestamp"] = return_timestamps[trade["entry_index"]]
            session_trade_entry["exit_return_timestamp"] = None
            if trade["exit_index"] is not None:
                session_trade_entry["exit_return_timestamp"] = return_timestamps[trade["exit_index"]]
            session_trade_entry["entered_during_session"] = True
            session_trade_entry["exited_during_session"] = trade["exit_index"] is not None
            session_trade_entry["active_at_session_end"] = trade["exit_index"] is None
            trade_log.append(session_trade_entry)

    summary = {
        "simulation_name": strategy_config.get("simulation_name", strategy_config.get("name", "live_decision_runner")),
        "runner_name": "live_decision_runner",
        "status": status,
        "stop_reason": stop_reason,
        "error_message": error_message,
        "symbol": data_source["symbol"],
        "default_symbol": data_sources["default_symbol"],
        "available_symbols": data_sources["symbols"],
        "interval": data_source["interval"],
        "poll_interval_seconds": config["runtime"]["poll_interval_seconds"],
        "duration_seconds": config["runtime"]["duration_seconds"],
        "configured_fetch_limit": data_source["limit"],
        "output_dir": output["output_dir"],
        "run_id": None,
        "run_directory": None,
        "max_run_directories": output["max_run_directories"],
        "started_at": started_at,
        "ended_at": ended_at,
        "poll_count": poll_count,
        "evaluated_decisions": len(decision_log),
        "warmup_candles": config["runtime"]["warmup_candles"],
        "observed_confirmed_candles": counters["observed_confirmed_candles"],
        "warmup_completed": counters["observed_confirmed_candles"] >= config["runtime"]["warmup_candles"],
        "warmup_completed_timestamp": counters["warmup_completed_timestamp"],
        "no_new_confirmed_candle_polls": counters["no_new_confirmed_candle_polls"],
        "data_insufficient_polls": counters["data_insufficient_polls"],
        "fetch_failures": counters["fetch_failures"],
        "rate_limit_events": counters["rate_limit_events"],
        "last_confirmed_timestamp": last_confirmed_timestamp,
        "latest_used_weight_1m": counters["latest_used_weight_1m"],
        "aggregation_scope": {
            "trade_count": "live_session_only",
            "winning_trades": "live_session_only",
            "losing_trades": "live_session_only",
            "realized_pnl_total": "live_session_only",
            "final_value": "session_end_absolute_equity",
            "final_cash": "session_end_absolute_cash",
            "open_position_at_end": "session_end_absolute_position_state",
            "trade_log": "live_session_trades_only",
        },
        "session_start_state": session_start_state,
        "session_end_state": session_end_state,
        "trade_count": session_end_state["trade_count"],
        "winning_trades": session_end_state["winning_trades"],
        "losing_trades": session_end_state["losing_trades"],
        "realized_pnl_total": session_end_state["realized_pnl_total"],
        "session_value_change": session_end_state["equity"] - session_start_state["equity"],
        "session_started_with_open_position": False,
        "final_value": session_end_state["equity"],
        "final_cash": session_end_state["cash"],
        "open_position_at_end": session_end_state["open_position"],
    }

    if run_context is not None:
        summary["run_id"] = run_context["run_id"]
        summary["run_directory"] = run_context["run_directory"]

    return {
        "data_source": data_source,
        "data_sources": data_sources,
        "runtime": config["runtime"],
        "output": output,
        "retry": config["retry"],
        "strategy": {
            key: value for key, value in strategy_config.items() if key not in {"returns", "entry_signals", "exit_signals"}
        },
        "summary": summary,
        "decision_log": decision_log,
        "trade_log": trade_log,
        "equity_history": equity_history,
        "progress_log": progress_log,
    }


def run_live_decision_runner(
    config: dict,
    *,
    symbol: str | None = None,
    fetch_klines_fn: Callable[[str, str, int], dict] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    now_fn: Callable[[], float] | None = None,
    stop_requested_fn: Callable[[], bool] | None = None,
    print_fn: Callable[[str], None] | None = None,
) -> dict:
    selected_config = dict(config)
    if symbol is not None:
        data_source, data_sources = _select_live_data_source(config, symbol=symbol)
        selected_config["data_source"] = data_source
        selected_config["data_sources"] = {
            "default_symbol": data_source["symbol"],
            "symbols": list(data_sources["sources"]),
        }

    validated_config = load_live_decision_runner_config(selected_config)

    if fetch_klines_fn is None:
        fetch_klines_fn = fetch_binance_spot_klines
    if sleep_fn is None:
        sleep_fn = time.sleep
    if now_fn is None:
        now_fn = time.time
    if stop_requested_fn is None:
        stop_requested_fn = lambda: False
    if print_fn is None:
        print_fn = print

    data_source = validated_config["data_source"]
    runtime = validated_config["runtime"]
    retry = dict(validated_config["retry"])

    started_at = _utc_now_iso(now_fn)
    started_at_seconds = now_fn()
    retry["duration_seconds"] = runtime["duration_seconds"]

    counters = {
        "started_at": started_at_seconds,
        "fetch_failures": 0,
        "rate_limit_events": 0,
        "no_new_confirmed_candle_polls": 0,
        "data_insufficient_polls": 0,
        "observed_confirmed_candles": 0,
        "warmup_completed_timestamp": None,
        "latest_used_weight_1m": None,
    }

    confirmed_rows: list[dict] = []
    last_confirmed_timestamp: str | None = None
    decision_log: list[dict] = []
    equity_history: list[dict] = []
    progress_log: list[dict] = []
    latest_result: dict | None = None
    session_start_signal_index: int | None = None
    status = "completed"
    stop_reason = "duration_elapsed"
    error_message: str | None = None
    poll_index = 0

    try:
        while now_fn() - started_at_seconds < runtime["duration_seconds"]:
            if stop_requested_fn():
                stop_reason = "stop_requested"
                break

            fetched_at = _utc_now_iso(now_fn)
            poll_index += 1

            response = _run_fetch_with_retry(
                fetch_klines_fn=fetch_klines_fn,
                symbol=data_source["symbol"],
                interval=data_source["interval"],
                limit=data_source["limit"],
                retry_config=retry,
                sleep_fn=sleep_fn,
                now_fn=now_fn,
                counters=counters,
            )

            counters["latest_used_weight_1m"] = response.get("used_weight_1m")

            raw_rows = response.get("rows")
            if not isinstance(raw_rows, list):
                raise ValueError("fetch_klines_fn must return a dict with a rows list")
            if not raw_rows:
                raise ValueError("kline response rows must not be empty")

            current_now_ms = int(now_fn() * 1000)
            latest_confirmed_rows = _select_confirmed_rows(raw_rows, current_now_ms)
            latest_weight_1m = response.get("used_weight_1m")
            progress_reason_code = "no_new_confirmed_candle"

            if not latest_confirmed_rows:
                counters["data_insufficient_polls"] += 1
                progress_reason_code = "no_confirmed_candle_available"
                if runtime["emit_progress_log"]:
                    progress_log.append(
                        _build_progress_entry(
                            poll_index=poll_index,
                            fetched_at=fetched_at,
                            reason_code="no_confirmed_candle_available",
                            confirmed_rows=0,
                            last_confirmed_timestamp=last_confirmed_timestamp,
                            used_weight_1m=latest_weight_1m,
                            )
                    )
            else:
                newest_timestamp = latest_confirmed_rows[-1]["timestamp"]
                if last_confirmed_timestamp is None:
                    confirmed_rows = list(latest_confirmed_rows)
                    last_confirmed_timestamp = newest_timestamp
                    counters["observed_confirmed_candles"] += 1
                    if counters["observed_confirmed_candles"] == runtime["warmup_candles"]:
                        counters["warmup_completed_timestamp"] = last_confirmed_timestamp
                        session_start_signal_index = max(len(confirmed_rows) - 1, 0)

                    if counters["observed_confirmed_candles"] <= runtime["warmup_candles"]:
                        progress_reason_code = "warmup_pending"
                        if runtime["emit_progress_log"]:
                            progress_log.append(
                                _build_progress_entry(
                                    poll_index=poll_index,
                                    fetched_at=fetched_at,
                                    reason_code="warmup_pending",
                                    confirmed_rows=len(confirmed_rows),
                                    last_confirmed_timestamp=last_confirmed_timestamp,
                                    used_weight_1m=latest_weight_1m,
                                    detail=(
                                        f"observed {counters['observed_confirmed_candles']} of "
                                        f"{runtime['warmup_candles']} warmup candles"
                                    ),
                                )
                            )
                    elif len(confirmed_rows) < 2:
                        counters["data_insufficient_polls"] += 1
                        progress_reason_code = "waiting_for_second_confirmed_candle"
                        if runtime["emit_progress_log"]:
                            progress_log.append(
                                _build_progress_entry(
                                    poll_index=poll_index,
                                    fetched_at=fetched_at,
                                    reason_code="waiting_for_second_confirmed_candle",
                                    confirmed_rows=len(confirmed_rows),
                                    last_confirmed_timestamp=last_confirmed_timestamp,
                                    used_weight_1m=latest_weight_1m,
                                )
                            )
                    else:
                        progress_reason_code = "decision_evaluated"
                        latest_result = _append_decision_entries(
                            strategy_config=validated_config["strategy"],
                            confirmed_rows=confirmed_rows,
                            session_start_index=(
                                session_start_signal_index
                                if session_start_signal_index is not None
                                else max(len(confirmed_rows) - 1, 0)
                            ),
                            latest_row=confirmed_rows[-1],
                            decision_log=decision_log,
                            equity_history=equity_history,
                            poll_index=poll_index,
                            fetched_at=fetched_at,
                            latest_weight_1m=latest_weight_1m,
                        )
                elif newest_timestamp <= last_confirmed_timestamp:
                    counters["no_new_confirmed_candle_polls"] += 1
                    progress_reason_code = "no_new_confirmed_candle"
                    if runtime["emit_progress_log"]:
                        progress_log.append(
                            _build_progress_entry(
                                poll_index=poll_index,
                                fetched_at=fetched_at,
                                reason_code="no_new_confirmed_candle",
                                confirmed_rows=len(latest_confirmed_rows),
                                last_confirmed_timestamp=last_confirmed_timestamp,
                                used_weight_1m=latest_weight_1m,
                            )
                        )
                else:
                    new_rows = [row for row in latest_confirmed_rows if row["timestamp"] > last_confirmed_timestamp]

                    for row in new_rows:
                        confirmed_rows.append(row)
                        last_confirmed_timestamp = row["timestamp"]
                        counters["observed_confirmed_candles"] += 1
                        if counters["observed_confirmed_candles"] == runtime["warmup_candles"]:
                            counters["warmup_completed_timestamp"] = last_confirmed_timestamp
                            session_start_signal_index = max(len(confirmed_rows) - 1, 0)

                        if counters["observed_confirmed_candles"] <= runtime["warmup_candles"]:
                            progress_reason_code = "warmup_pending"
                            if runtime["emit_progress_log"]:
                                progress_log.append(
                                    _build_progress_entry(
                                        poll_index=poll_index,
                                        fetched_at=fetched_at,
                                        reason_code="warmup_pending",
                                        confirmed_rows=len(confirmed_rows),
                                        last_confirmed_timestamp=last_confirmed_timestamp,
                                        used_weight_1m=latest_weight_1m,
                                        detail=(
                                            f"observed {counters['observed_confirmed_candles']} of "
                                            f"{runtime['warmup_candles']} warmup candles"
                                        ),
                                    )
                                )
                            continue

                        if len(confirmed_rows) < 2:
                            counters["data_insufficient_polls"] += 1
                            progress_reason_code = "waiting_for_second_confirmed_candle"
                            if runtime["emit_progress_log"]:
                                progress_log.append(
                                    _build_progress_entry(
                                        poll_index=poll_index,
                                        fetched_at=fetched_at,
                                        reason_code="waiting_for_second_confirmed_candle",
                                        confirmed_rows=len(confirmed_rows),
                                        last_confirmed_timestamp=last_confirmed_timestamp,
                                        used_weight_1m=latest_weight_1m,
                                    )
                                )
                            continue

                        progress_reason_code = "decision_evaluated"
                        latest_result = _append_decision_entries(
                            strategy_config=validated_config["strategy"],
                            confirmed_rows=confirmed_rows,
                            session_start_index=(
                                session_start_signal_index
                                if session_start_signal_index is not None
                                else max(len(confirmed_rows) - 1, 0)
                            ),
                            latest_row=row,
                            decision_log=decision_log,
                            equity_history=equity_history,
                            poll_index=poll_index,
                            fetched_at=fetched_at,
                            latest_weight_1m=latest_weight_1m,
                        )

            print_fn(
                format_live_progress_stdout(
                    build_live_progress_stdout_payload(
                        poll_index=poll_index,
                        fetched_at=fetched_at,
                        latest_result=latest_result,
                        initial_cash=float(validated_config["strategy"]["initial_cash"]),
                        reason_code=progress_reason_code,
                        last_confirmed_timestamp=last_confirmed_timestamp,
                        symbol=data_source["symbol"],
                    )
                )
            )

            remaining_seconds = runtime["duration_seconds"] - (now_fn() - started_at_seconds)
            if remaining_seconds <= 0:
                break

            sleep_seconds = min(runtime["poll_interval_seconds"], remaining_seconds)
            if sleep_seconds > 0:
                sleep_fn(sleep_seconds)
    except KeyboardInterrupt:
        status = "interrupted"
        stop_reason = "keyboard_interrupt"
    except Exception as error:
        status = "failed"
        stop_reason = "error"
        error_message = str(error)

    ended_at = _utc_now_iso(now_fn)

    payload = _build_runtime_payload(
        config=validated_config,
        confirmed_rows=confirmed_rows,
        decision_log=decision_log,
        equity_history=equity_history,
        progress_log=progress_log,
        latest_result=latest_result,
        status=status,
        stop_reason=stop_reason,
        started_at=started_at,
        ended_at=ended_at,
        last_confirmed_timestamp=last_confirmed_timestamp,
        poll_count=poll_index,
        counters=counters,
        error_message=error_message,
        run_context=None,
    )
    return payload


def _list_safe_run_directories(output_dir: str | Path) -> list[Path]:
    output_path = Path(output_dir)
    if not output_path.exists():
        return []

    resolved_output_path = output_path.resolve()
    run_directories = []
    for candidate in output_path.iterdir():
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        if not RUN_DIRECTORY_NAME_PATTERN.match(candidate.name):
            continue
        try:
            resolved_candidate = candidate.resolve()
        except OSError:
            continue
        if resolved_candidate.parent != resolved_output_path:
            continue
        run_directories.append(candidate)

    run_directories.sort(key=lambda path: path.name)
    return run_directories


def prune_live_decision_run_directories(output_dir: str | Path, max_run_directories: int) -> list[str]:
    removed_directories: list[str] = []
    run_directories = _list_safe_run_directories(output_dir)
    removable_count = max(0, len(run_directories) - max_run_directories + 1)

    for path in run_directories[:removable_count]:
        shutil.rmtree(path)
        removed_directories.append(str(path))

    return removed_directories


def prepare_live_decision_output_directory(
    output_dir: str | Path,
    *,
    run_started_at: str,
    max_run_directories: int,
) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    removed_directories = prune_live_decision_run_directories(output_path, max_run_directories)
    run_id = _run_id_from_iso8601(run_started_at)
    run_directory = output_path / run_id
    run_directory.mkdir()
    return {
        "run_id": run_id,
        "run_directory": str(run_directory),
        "removed_directories": removed_directories,
    }


def save_live_decision_runner_result(
    result: dict,
    output_dir: str | Path,
    *,
    run_context: dict | None = None,
) -> dict:
    output_path = Path(output_dir)
    max_run_directories = int(result.get("output", {}).get("max_run_directories", 10))

    if run_context is None:
        run_context = prepare_live_decision_output_directory(
            output_path,
            run_started_at=result["summary"]["started_at"],
            max_run_directories=max_run_directories,
        )

    result["summary"]["run_id"] = run_context["run_id"]
    result["summary"]["run_directory"] = run_context["run_directory"]
    result["summary"]["removed_run_directories"] = list(run_context.get("removed_directories", []))

    file_map = {
        "summary": Path(run_context["run_directory"]) / "summary.json",
        "decision_log": Path(run_context["run_directory"]) / "decision_log.json",
        "trade_log": Path(run_context["run_directory"]) / "trade_log.json",
        "equity_history": Path(run_context["run_directory"]) / "equity_history.json",
        "progress_log": Path(run_context["run_directory"]) / "progress_log.json",
    }

    for key, path in file_map.items():
        with path.open("w", encoding="utf-8") as file:
            json.dump(result[key], file, ensure_ascii=False, indent=2)
            file.write("\n")

    return {key: str(path) for key, path in file_map.items()}


def build_live_decision_stdout_payload(result: dict) -> dict:
    output_config = result.get("output", {})
    first_n = int(output_config.get("first_n", 10))
    last_n = int(output_config.get("last_n", 10))
    decision_log = list(result.get("decision_log", []))

    if len(decision_log) <= first_n:
        first_entries = decision_log
        last_entries: list[dict] = []
    elif len(decision_log) <= first_n + last_n:
        first_entries = decision_log
        last_entries = []
    else:
        first_entries = decision_log[:first_n]
        last_entries = decision_log[-last_n:]

    payload = {
        "summary": result.get("summary", {}),
        "decision_log_first": first_entries,
    }
    if last_entries:
        payload["decision_log_last"] = last_entries
    return payload


def format_live_decision_stdout(result: dict) -> str:
    return json.dumps(build_live_decision_stdout_payload(result), ensure_ascii=False, indent=2)


def build_live_decision_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the live decision runner with confirmed-candle polling.")
    parser.add_argument("--config", required=True, help="Path to a live decision runner JSON config file.")
    parser.add_argument("--symbol", help="Configured symbol to run. Defaults to data_sources.default_symbol.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from trade_simulator.config import load_config

    parser = build_live_decision_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = run_live_decision_runner(config, symbol=args.symbol)
    save_live_decision_runner_result(result, result["output"]["output_dir"])
    print(format_live_decision_stdout(result))
    return 0 if result["summary"]["status"] != "failed" else 1
