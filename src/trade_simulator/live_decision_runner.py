from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trade_simulator.data.ohlcv import build_close_to_close_returns, normalize_ohlcv_rows
from trade_simulator.signals import (
    generate_consecutive_drop_signals,
    generate_cumulative_drop_signals,
    generate_threshold_signals,
)
from trade_simulator.simulation import simulate


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"


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


def load_live_decision_runner_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("live decision runner config must be a dict")

    required_sections = ("data_source", "runtime", "strategy", "output", "retry")
    for section in required_sections:
        if section not in config or not isinstance(config[section], dict):
            raise ValueError(f"live decision runner config must include a {section} dict")

    data_source = dict(config["data_source"])
    runtime = dict(config["runtime"])
    strategy = dict(config["strategy"])
    output = dict(config["output"])
    retry = dict(config["retry"])

    if "symbol" not in data_source:
        raise ValueError("data_source must include symbol")
    if "interval" not in data_source:
        raise ValueError("data_source must include interval")
    if data_source["interval"] != "1m":
        raise ValueError("data_source interval must be 1m")

    data_source["limit"] = _validate_positive_int(data_source.get("limit", 120), "limit")
    runtime["poll_interval_seconds"] = _validate_non_negative_number(
        runtime.get("poll_interval_seconds", 60),
        "poll_interval_seconds",
    )
    runtime["duration_seconds"] = _validate_non_negative_number(
        runtime.get("duration_seconds", 600),
        "duration_seconds",
    )
    runtime["emit_progress_log"] = _validate_bool(runtime.get("emit_progress_log", True), "emit_progress_log")

    if "output_dir" not in output:
        raise ValueError("output must include output_dir")
    output["first_n"] = _validate_positive_int(output.get("first_n", 10), "first_n")
    output["last_n"] = _validate_positive_int(output.get("last_n", 10), "last_n")

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
        "runtime": runtime,
        "strategy": strategy,
        "output": output,
        "retry": retry,
    }


def _utc_now_iso(now_fn: Callable[[], float]) -> str:
    return datetime.fromtimestamp(now_fn(), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_from_milliseconds(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


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


def _build_strategy_result(strategy_config: dict, returns: list[float]) -> dict:
    strategy_name = strategy_config.get("strategy")
    if strategy_name == "threshold":
        if "entry_threshold" not in strategy_config or "exit_threshold" not in strategy_config:
            raise ValueError("threshold strategy requires entry_threshold and exit_threshold")
        entry_signals, exit_signals = generate_threshold_signals(
            returns,
            strategy_config["entry_threshold"],
            strategy_config["exit_threshold"],
        )
    elif strategy_name == "cumulative_drop":
        required_keys = ("entry_window", "entry_cumulative_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError(
                "cumulative_drop strategy requires entry_window, entry_cumulative_threshold, and exit_threshold"
            )
        entry_signals, exit_signals = generate_cumulative_drop_signals(
            returns,
            strategy_config["entry_window"],
            strategy_config["entry_cumulative_threshold"],
            strategy_config["exit_threshold"],
        )
    elif strategy_name == "consecutive_drop":
        required_keys = ("consecutive_periods", "drop_threshold", "exit_threshold")
        if not all(key in strategy_config for key in required_keys):
            raise ValueError("consecutive_drop strategy requires consecutive_periods, drop_threshold, and exit_threshold")
        entry_signals, exit_signals = generate_consecutive_drop_signals(
            returns,
            strategy_config["consecutive_periods"],
            strategy_config["drop_threshold"],
            strategy_config["exit_threshold"],
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


def _append_decision_entries(
    *,
    strategy_config: dict,
    confirmed_rows: list[dict],
    latest_row: dict,
    decision_log: list[dict],
    equity_history: list[dict],
    poll_index: int,
    fetched_at: str,
    latest_weight_1m: str | None,
) -> dict:
    returns_payload = build_close_to_close_returns(confirmed_rows)
    latest_result = _build_strategy_result(strategy_config, returns_payload["returns"])
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
) -> dict:
    strategy_config = config["strategy"]
    data_source = config["data_source"]
    output = config["output"]

    trade_log: list[dict] = []
    if latest_result is not None:
        trade_log = latest_result["trade_log"]

    final_value = float(strategy_config["initial_cash"])
    trade_count = 0
    periods_in_position = 0
    winning_trades = 0
    losing_trades = 0
    realized_pnl_total = 0.0
    open_position_at_end = False

    if latest_result is not None:
        final_value = latest_result["final_value"]
        trade_count = latest_result["trade_count"]
        periods_in_position = latest_result["periods_in_position"]
        winning_trades = latest_result["winning_trades"]
        losing_trades = latest_result["losing_trades"]
        realized_pnl_total = latest_result["realized_pnl_total"]
        open_position_at_end = bool(latest_result["position"] and latest_result["position"][-1])

    summary = {
        "simulation_name": strategy_config.get("simulation_name", strategy_config.get("name", "live_decision_runner")),
        "runner_name": "live_decision_runner",
        "status": status,
        "stop_reason": stop_reason,
        "error_message": error_message,
        "symbol": data_source["symbol"],
        "interval": data_source["interval"],
        "poll_interval_seconds": config["runtime"]["poll_interval_seconds"],
        "duration_seconds": config["runtime"]["duration_seconds"],
        "configured_fetch_limit": data_source["limit"],
        "output_dir": output["output_dir"],
        "started_at": started_at,
        "ended_at": ended_at,
        "poll_count": poll_count,
        "evaluated_decisions": len(decision_log),
        "no_new_confirmed_candle_polls": counters["no_new_confirmed_candle_polls"],
        "data_insufficient_polls": counters["data_insufficient_polls"],
        "fetch_failures": counters["fetch_failures"],
        "rate_limit_events": counters["rate_limit_events"],
        "last_confirmed_timestamp": last_confirmed_timestamp,
        "latest_used_weight_1m": counters["latest_used_weight_1m"],
        "final_value": final_value,
        "trade_count": trade_count,
        "periods_in_position": periods_in_position,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "realized_pnl_total": realized_pnl_total,
        "open_position_at_end": open_position_at_end,
    }

    return {
        "data_source": data_source,
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
    fetch_klines_fn: Callable[[str, str, int], dict] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    now_fn: Callable[[], float] | None = None,
    stop_requested_fn: Callable[[], bool] | None = None,
) -> dict:
    validated_config = load_live_decision_runner_config(config)

    if fetch_klines_fn is None:
        fetch_klines_fn = fetch_binance_spot_klines
    if sleep_fn is None:
        sleep_fn = time.sleep
    if now_fn is None:
        now_fn = time.time
    if stop_requested_fn is None:
        stop_requested_fn = lambda: False

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
        "latest_used_weight_1m": None,
    }

    confirmed_rows: list[dict] = []
    last_confirmed_timestamp: str | None = None
    decision_log: list[dict] = []
    trade_log: list[dict] = []
    equity_history: list[dict] = []
    progress_log: list[dict] = []
    latest_result: dict | None = None
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

            if not latest_confirmed_rows:
                counters["data_insufficient_polls"] += 1
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

                    if len(confirmed_rows) < 2:
                        counters["data_insufficient_polls"] += 1
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
                        latest_result = _append_decision_entries(
                            strategy_config=validated_config["strategy"],
                            confirmed_rows=confirmed_rows,
                            latest_row=confirmed_rows[-1],
                            decision_log=decision_log,
                            equity_history=equity_history,
                            poll_index=poll_index,
                            fetched_at=fetched_at,
                            latest_weight_1m=latest_weight_1m,
                        )
                        trade_log = latest_result["trade_log"]
                elif newest_timestamp <= last_confirmed_timestamp:
                    counters["no_new_confirmed_candle_polls"] += 1
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

                        if len(confirmed_rows) < 2:
                            counters["data_insufficient_polls"] += 1
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

                        latest_result = _append_decision_entries(
                            strategy_config=validated_config["strategy"],
                            confirmed_rows=confirmed_rows,
                            latest_row=row,
                            decision_log=decision_log,
                            equity_history=equity_history,
                            poll_index=poll_index,
                            fetched_at=fetched_at,
                            latest_weight_1m=latest_weight_1m,
                        )
                        trade_log = latest_result["trade_log"]

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
    )
    payload["trade_log"] = trade_log
    return payload


def save_live_decision_runner_result(result: dict, output_dir: str | Path) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_map = {
        "summary": output_path / "summary.json",
        "decision_log": output_path / "decision_log.json",
        "trade_log": output_path / "trade_log.json",
        "equity_history": output_path / "equity_history.json",
        "progress_log": output_path / "progress_log.json",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    from trade_simulator.config import load_config

    parser = build_live_decision_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = run_live_decision_runner(config)
    save_live_decision_runner_result(result, result["output"]["output_dir"])
    print(format_live_decision_stdout(result))
    return 0 if result["summary"]["status"] != "failed" else 1
