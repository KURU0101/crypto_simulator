from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.live_decision_cli import main as live_decision_main
from trade_simulator.live_decision_runner import (
    FetchOHLCVError,
    build_live_decision_stdout_payload,
    format_live_decision_stdout,
    load_live_decision_runner_config,
    run_live_decision_runner,
    save_live_decision_runner_result,
)


class FakeClock:
    def __init__(self, start_seconds: float) -> None:
        self.current = start_seconds
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


def _build_live_config(output_dir: Path) -> dict:
    return {
        "data_source": {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "limit": 5,
        },
        "runtime": {
            "poll_interval_seconds": 60,
            "duration_seconds": 130,
            "emit_progress_log": True,
        },
        "output": {
            "output_dir": str(output_dir),
            "first_n": 10,
            "last_n": 10,
        },
        "retry": {
            "max_attempts": 2,
            "initial_backoff_seconds": 5,
            "backoff_multiplier": 2.0,
            "max_backoff_seconds": 60,
        },
        "strategy": {
            "name": "live_threshold_runner",
            "simulation_name": "live_threshold_runner",
            "strategy": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "entry_threshold": 0.015,
            "exit_threshold": -0.02,
        },
    }


def _kline(minute_index: int, close: str) -> list[object]:
    open_time_ms = minute_index * 60_000
    close_time_ms = open_time_ms + 59_999
    close_value = float(close)
    return [
        open_time_ms,
        close,
        f"{close_value + 1:.1f}",
        f"{close_value - 1:.1f}",
        close,
        "10",
        close_time_ms,
        "100",
        1,
        "5",
        "50",
        "0",
    ]


def _response(*klines: list[object], used_weight_1m: str = "3") -> dict:
    rows = []
    for kline in klines:
        rows.append(
            {
                "timestamp": f"2024-01-01T00:{int(kline[0] / 60_000):02d}:00Z",
                "open": kline[1],
                "high": kline[2],
                "low": kline[3],
                "close": kline[4],
                "volume": kline[5],
                "close_time_ms": kline[6],
            }
        )
    return {
        "rows": rows,
        "used_weight_1m": used_weight_1m,
    }


def test_load_live_decision_runner_config_validates_required_sections() -> None:
    with pytest.raises(ValueError, match="live decision runner config must include a runtime dict"):
        load_live_decision_runner_config({"data_source": {}, "strategy": {}, "output": {}, "retry": {}})

    with pytest.raises(ValueError, match="data_source interval must be 1m"):
        load_live_decision_runner_config(
            {
                "data_source": {"symbol": "BTCUSDT", "interval": "5m"},
                "runtime": {},
                "strategy": {},
                "output": {"output_dir": "outputs/live"},
                "retry": {},
            }
        )


def test_live_decision_runner_generates_summary_and_output_files(tmp_path: Path) -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(tmp_path / "outputs")
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98")),
            _response(_kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103")),
            _response(_kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103"), _kline(6, "100")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        assert symbol == "BTCUSDT"
        assert interval == "1m"
        assert limit == 5
        return next(responses)

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)
    paths = save_live_decision_runner_result(result, config["output"]["output_dir"])

    assert result["summary"]["status"] == "completed"
    assert result["summary"]["stop_reason"] == "duration_elapsed"
    assert result["summary"]["evaluated_decisions"] == 3
    assert result["summary"]["poll_count"] == 3
    assert result["summary"]["last_confirmed_timestamp"] == "2024-01-01T00:05:00Z"
    assert len(result["decision_log"]) == 3
    assert len(result["equity_history"]) == 3
    assert result["decision_log"][0]["ohlcv_timestamp"] == "2024-01-01T00:03:00Z"
    assert result["decision_log"][1]["ohlcv_timestamp"] == "2024-01-01T00:04:00Z"
    assert result["decision_log"][2]["ohlcv_timestamp"] == "2024-01-01T00:05:00Z"
    assert Path(paths["summary"]).exists()
    assert Path(paths["decision_log"]).exists()
    assert Path(paths["trade_log"]).exists()
    assert Path(paths["equity_history"]).exists()
    assert json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))["status"] == "completed"


def test_live_decision_runner_handles_keyboard_interrupt_and_still_saves(tmp_path: Path) -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(tmp_path / "outputs")
    response = _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"))

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return response

    def interrupting_sleep(seconds: float) -> None:
        raise KeyboardInterrupt

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=interrupting_sleep,
        now_fn=clock.now,
    )
    save_live_decision_runner_result(result, config["output"]["output_dir"])

    assert result["summary"]["status"] == "interrupted"
    assert result["summary"]["stop_reason"] == "keyboard_interrupt"
    assert Path(config["output"]["output_dir"], "summary.json").exists()
    assert len(result["decision_log"]) == 1


def test_live_decision_runner_skips_same_timestamp_until_new_confirmed_candle() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["poll_interval_seconds"] = 1
    config["runtime"]["duration_seconds"] = 3
    repeated = _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"))
    responses = iter([repeated, repeated, repeated])

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert len(result["decision_log"]) == 1
    assert result["summary"]["no_new_confirmed_candle_polls"] == 2
    assert [entry["reason_code"] for entry in result["progress_log"]] == [
        "no_new_confirmed_candle",
        "no_new_confirmed_candle",
    ]


def test_live_decision_runner_limits_stdout_to_summary_and_head_tail_only() -> None:
    result = {
        "output": {"first_n": 10, "last_n": 10},
        "summary": {"status": "completed"},
        "decision_log": [{"decision_index": index} for index in range(25)],
    }

    payload = build_live_decision_stdout_payload(result)
    rendered = format_live_decision_stdout(result)

    assert payload["decision_log_first"] == [{"decision_index": index} for index in range(10)]
    assert payload["decision_log_last"] == [{"decision_index": index} for index in range(15, 25)]
    assert '"decision_index": 12' not in rendered
    assert '"decision_index": 24' in rendered


def test_live_decision_runner_shows_all_decisions_when_fewer_than_ten() -> None:
    result = {
        "output": {"first_n": 10, "last_n": 10},
        "summary": {"status": "completed"},
        "decision_log": [{"decision_index": index} for index in range(3)],
    }

    payload = build_live_decision_stdout_payload(result)

    assert payload["decision_log_first"] == [{"decision_index": 0}, {"decision_index": 1}, {"decision_index": 2}]
    assert "decision_log_last" not in payload


def test_live_decision_runner_retries_after_http_429_with_backoff() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 1
    responses = iter(
        [
            FetchOHLCVError("rate limited", status_code=429, headers={"Retry-After": "7"}),
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert result["summary"]["status"] == "completed"
    assert result["summary"]["rate_limit_events"] == 1
    assert clock.sleep_calls[0] == 1


def test_live_decision_runner_returns_failed_status_on_fetch_failure() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 1

    def failing_fetch(symbol: str, interval: str, limit: int) -> dict:
        raise FetchOHLCVError("network failure")

    result = run_live_decision_runner(config, fetch_klines_fn=failing_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert result["summary"]["status"] == "failed"
    assert result["summary"]["stop_reason"] == "error"
    assert result["summary"]["fetch_failures"] == 2
    assert result["summary"]["error_message"] == "network failure"


def test_live_decision_runner_returns_failed_status_on_empty_response() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return {"rows": [], "used_weight_1m": "1"}

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert result["summary"]["status"] == "failed"
    assert result["summary"]["error_message"] == "kline response rows must not be empty"


def test_live_decision_runner_returns_failed_status_on_invalid_response_format() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return {"rows": [{"timestamp": "2024-01-01T00:00:00Z"}], "used_weight_1m": "1"}

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert result["summary"]["status"] == "failed"
    assert result["summary"]["stop_reason"] == "error"


def test_live_decision_runner_handles_long_no_new_confirmed_candle_period() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["poll_interval_seconds"] = 1
    config["runtime"]["duration_seconds"] = 4
    single = _response(_kline(3, "98"))
    responses = iter([single, single, single, single])

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(config, fetch_klines_fn=fake_fetch, sleep_fn=clock.sleep, now_fn=clock.now)

    assert result["summary"]["status"] == "completed"
    assert result["summary"]["evaluated_decisions"] == 0
    assert result["summary"]["data_insufficient_polls"] == 1
    assert result["summary"]["no_new_confirmed_candle_polls"] == 3


def test_save_live_decision_runner_result_propagates_directory_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = {
        "summary": {},
        "decision_log": [],
        "trade_log": [],
        "equity_history": [],
        "progress_log": [],
    }

    def raise_os_error(self: Path, parents: bool, exist_ok: bool) -> None:
        raise OSError("mkdir failed")

    monkeypatch.setattr(Path, "mkdir", raise_os_error)

    with pytest.raises(OSError, match="mkdir failed"):
        save_live_decision_runner_result(result, tmp_path / "outputs")


def test_live_decision_cli_writes_files_and_prints_truncated_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "live.json"
    output_dir = tmp_path / "outputs"
    config = _build_live_config(output_dir)
    config["runtime"]["duration_seconds"] = 0
    config_path.write_text(json.dumps(config), encoding="utf-8")

    exit_code = live_decision_main(["--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"summary"' in captured.out
    assert '"decision_log_first"' in captured.out
    assert Path(output_dir, "summary.json").exists()
