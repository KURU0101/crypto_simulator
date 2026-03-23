from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.live_decision_runner import (
    FetchOHLCVError,
    build_live_decision_stdout_payload,
    format_live_decision_stdout,
    load_live_decision_runner_config,
    prepare_live_decision_output_directory,
    prune_live_decision_run_directories,
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
            "duration_seconds": 190,
            "emit_progress_log": True,
            "warmup_candles": 2,
        },
        "output": {
            "output_dir": str(output_dir),
            "first_n": 10,
            "last_n": 10,
            "max_run_directories": 10,
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


def _collecting_printer(lines: list[str]):
    def _printer(line: str) -> None:
        lines.append(line)

    return _printer


def _seed_run_directories(base_dir: Path, count: int) -> None:
    for index in range(count):
        run_dir = base_dir / f"20260324T0315{index:02d}Z"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text("{}", encoding="utf-8")


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


def test_live_decision_runner_waits_for_warmup_before_first_decision() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    progress_lines: list[str] = []
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98")),
            _response(_kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103")),
            _response(_kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103"), _kline(6, "100")),
            _response(_kline(3, "101"), _kline(4, "98"), _kline(5, "103"), _kline(6, "100"), _kline(7, "104")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    assert result["summary"]["status"] == "completed"
    assert result["summary"]["warmup_candles"] == 2
    assert result["summary"]["observed_confirmed_candles"] == 4
    assert result["summary"]["warmup_completed"] is True
    assert result["summary"]["warmup_completed_timestamp"] == "2024-01-01T00:04:00Z"
    assert [entry["reason_code"] for entry in result["progress_log"][:2]] == ["warmup_pending", "warmup_pending"]
    assert len(result["decision_log"]) == 2
    assert result["decision_log"][0]["ohlcv_timestamp"] == "2024-01-01T00:05:00Z"
    assert result["decision_log"][1]["ohlcv_timestamp"] == "2024-01-01T00:06:00Z"

    parsed_progress = [json.loads(line) for line in progress_lines]
    assert [entry["reason_code"] for entry in parsed_progress] == [
        "warmup_pending",
        "warmup_pending",
        "decision_evaluated",
        "decision_evaluated",
    ]
    assert all("trade_count" in entry and "equity" in entry and "cash" in entry for entry in parsed_progress)


def test_live_decision_runner_saves_each_run_into_separate_directory(tmp_path: Path) -> None:
    result_one = {
        "output": {"max_run_directories": 10},
        "summary": {"started_at": "2026-03-24T03:15:00Z"},
        "decision_log": [],
        "trade_log": [],
        "equity_history": [],
        "progress_log": [],
    }
    result_two = {
        "output": {"max_run_directories": 10},
        "summary": {"started_at": "2026-03-24T03:16:00Z"},
        "decision_log": [],
        "trade_log": [],
        "equity_history": [],
        "progress_log": [],
    }

    saved_one = save_live_decision_runner_result(result_one, tmp_path / "outputs")
    saved_two = save_live_decision_runner_result(result_two, tmp_path / "outputs")

    assert Path(saved_one["summary"]).parent.name == "20260324T031500Z"
    assert Path(saved_two["summary"]).parent.name == "20260324T031600Z"
    assert Path(saved_one["summary"]).parent != Path(saved_two["summary"]).parent


@pytest.mark.parametrize(
    ("existing_count", "expected_remaining_count", "expected_removed"),
    [
        (9, 10, []),
        (10, 10, ["20260324T031500Z"]),
        (11, 10, ["20260324T031500Z", "20260324T031501Z"]),
    ],
)
def test_live_decision_runner_retains_only_latest_ten_runs(
    tmp_path: Path,
    existing_count: int,
    expected_remaining_count: int,
    expected_removed: list[str],
) -> None:
    output_dir = tmp_path / "outputs"
    _seed_run_directories(output_dir, existing_count)

    result = {
        "output": {"max_run_directories": 10},
        "summary": {"started_at": "2026-03-24T04:00:00Z"},
        "decision_log": [],
        "trade_log": [],
        "equity_history": [],
        "progress_log": [],
    }

    save_live_decision_runner_result(result, output_dir)

    remaining = sorted(path.name for path in output_dir.iterdir() if path.is_dir())
    assert len(remaining) == expected_remaining_count
    assert result["summary"]["removed_run_directories"] == [str(output_dir / name) for name in expected_removed]
    assert "20260324T040000Z" in remaining


def test_prune_live_decision_run_directories_only_targets_safe_run_directories(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _seed_run_directories(output_dir, 10)
    unsafe = output_dir / "manual-notes"
    unsafe.mkdir()

    removed = prune_live_decision_run_directories(output_dir, 10)

    assert removed == [str(output_dir / "20260324T031500Z")]
    assert unsafe.exists()


def test_live_decision_runner_keeps_final_stdout_summary_and_head_tail_only() -> None:
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


def test_live_decision_runner_saves_run_directory_even_when_decision_count_is_zero(tmp_path: Path) -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(tmp_path / "outputs")
    config["runtime"]["duration_seconds"] = 120
    config["runtime"]["warmup_candles"] = 3
    progress_lines: list[str] = []
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98")),
            _response(_kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )
    saved = save_live_decision_runner_result(result, config["output"]["output_dir"])

    assert result["summary"]["evaluated_decisions"] == 0
    assert Path(saved["summary"]).exists()
    assert json.loads(Path(saved["summary"]).read_text(encoding="utf-8"))["evaluated_decisions"] == 0


def test_live_decision_runner_can_finish_right_after_warmup_completion() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 120
    progress_lines: list[str] = []
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98")),
            _response(_kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"), _kline(5, "103")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    assert result["summary"]["warmup_completed"] is True
    assert result["summary"]["evaluated_decisions"] == 0
    assert len(progress_lines) == 2


def test_live_decision_runner_returns_failed_status_on_fetch_failure() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    progress_lines: list[str] = []

    def failing_fetch(symbol: str, interval: str, limit: int) -> dict:
        raise FetchOHLCVError("network failure")

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=failing_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    assert result["summary"]["status"] == "failed"
    assert result["summary"]["error_message"] == "network failure"
    assert progress_lines == []


def test_prepare_live_decision_output_directory_propagates_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mkdir = Path.mkdir

    def failing_mkdir(self: Path, parents: bool = False, exist_ok: bool = False) -> None:
        if self.name == "outputs":
            raise OSError("mkdir failed")
        return original_mkdir(self, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    with pytest.raises(OSError, match="mkdir failed"):
        prepare_live_decision_output_directory(
            tmp_path / "outputs",
            run_started_at="2026-03-24T03:15:00Z",
            max_run_directories=10,
        )


def test_save_live_decision_runner_result_propagates_old_run_deletion_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "outputs"
    _seed_run_directories(output_dir, 10)

    def failing_rmtree(path: Path) -> None:
        raise OSError("delete failed")

    monkeypatch.setattr("trade_simulator.live_decision_runner.shutil.rmtree", failing_rmtree)

    result = {
        "output": {"max_run_directories": 10},
        "summary": {"started_at": "2026-03-24T04:00:00Z"},
        "decision_log": [],
        "trade_log": [],
        "equity_history": [],
        "progress_log": [],
    }

    with pytest.raises(OSError, match="delete failed"):
        save_live_decision_runner_result(result, output_dir)


def test_live_decision_runner_progress_summary_defaults_when_no_decision_data_yet() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 60
    config["runtime"]["warmup_candles"] = 2
    progress_lines: list[str] = []

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "101"), _kline(4, "98"))

    run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    progress = json.loads(progress_lines[0])
    assert progress["trade_count"] == 0
    assert progress["equity"] == 1000.0
    assert progress["cash"] == 1000.0
    assert progress["reason_code"] == "warmup_pending"


def test_live_decision_runner_summary_is_session_scoped_when_context_has_historical_trade() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 130
    progress_lines: list[str] = []
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "102"), _kline(2, "99"), _kline(3, "100"), _kline(4, "100")),
            _response(_kline(1, "102"), _kline(2, "99"), _kline(3, "100"), _kline(4, "100"), _kline(5, "100")),
            _response(_kline(2, "99"), _kline(3, "100"), _kline(4, "100"), _kline(5, "100"), _kline(6, "100")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    assert len(result["decision_log"]) == 1
    assert result["decision_log"][0]["signal_reason_code"] == "no_signal"
    assert result["decision_log"][0]["action_reason_code"] == "stay_flat"
    assert result["summary"]["trade_count"] == 0
    assert result["summary"]["winning_trades"] == 0
    assert result["summary"]["losing_trades"] == 0
    assert result["summary"]["realized_pnl_total"] == 0.0
    assert result["summary"]["session_value_change"] == 0.0
    assert result["summary"]["session_start_state"]["trade_count"] == 1
    assert result["summary"]["session_end_state"]["total_trade_count"] == 1
    assert result["trade_log"] == []

    final_progress = json.loads(progress_lines[-1])
    assert final_progress["trade_count"] == 0


def test_live_decision_runner_summary_and_trade_log_align_when_session_creates_trade() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    progress_lines: list[str] = []
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "100"), _kline(2, "100"), _kline(3, "100"), _kline(4, "100")),
            _response(_kline(1, "100"), _kline(2, "100"), _kline(3, "100"), _kline(4, "100"), _kline(5, "102")),
            _response(_kline(2, "100"), _kline(3, "100"), _kline(4, "100"), _kline(5, "102"), _kline(6, "99")),
            _response(_kline(3, "100"), _kline(4, "100"), _kline(5, "102"), _kline(6, "99"), _kline(7, "99")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=_collecting_printer(progress_lines),
    )

    assert [entry["action_reason_code"] for entry in result["decision_log"]] == ["enter_position", "exit_position"]
    assert result["summary"]["trade_count"] == 1
    assert result["summary"]["winning_trades"] == 1
    assert result["summary"]["realized_pnl_total"] > 0
    assert result["summary"]["session_end_state"]["total_trade_count"] == 1
    assert len(result["trade_log"]) == 1
    assert result["trade_log"][0]["entered_during_session"] is True
    assert result["trade_log"][0]["exited_during_session"] is True
    assert result["trade_log"][0]["entry_return_timestamp"] == "2024-01-01T00:05:00Z"
    assert result["trade_log"][0]["exit_return_timestamp"] == "2024-01-01T00:06:00Z"


def test_live_decision_runner_summary_handles_open_position_at_session_end() -> None:
    clock = FakeClock(start_seconds=250)
    config = _build_live_config(Path("outputs/test"))
    config["runtime"]["duration_seconds"] = 130
    responses = iter(
        [
            _response(_kline(0, "100"), _kline(1, "100"), _kline(2, "100"), _kline(3, "100"), _kline(4, "100")),
            _response(_kline(1, "100"), _kline(2, "100"), _kline(3, "100"), _kline(4, "100"), _kline(5, "102")),
            _response(_kline(2, "100"), _kline(3, "100"), _kline(4, "100"), _kline(5, "102"), _kline(6, "102")),
        ]
    )

    def fake_fetch(symbol: str, interval: str, limit: int) -> dict:
        return next(responses)

    result = run_live_decision_runner(
        config,
        fetch_klines_fn=fake_fetch,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        print_fn=lambda _: None,
    )

    assert result["summary"]["trade_count"] == 1
    assert result["summary"]["session_started_with_open_position"] is False
    assert result["summary"]["open_position_at_end"] is True
    assert len(result["trade_log"]) == 1
    assert result["trade_log"][0]["active_at_session_end"] is True
