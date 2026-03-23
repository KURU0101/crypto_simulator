from pathlib import Path

import pytest

from trade_simulator.config import load_config
from trade_simulator.pseudo_realtime_cli import main as pseudo_realtime_main
from trade_simulator.pseudo_realtime_replay import (
    initialize_work_csv,
    load_pseudo_realtime_config,
    run_pseudo_realtime_replay,
)


def _write_source_csv(csv_path: Path) -> None:
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                "2024-01-01T01:00:00Z,100,103,99,102,11",
                "2024-01-01T02:00:00Z,102,103,100,101,12",
                "2024-01-01T03:00:00Z,101,104,100,103,13",
                "2024-01-01T04:00:00Z,103,104,100,99,14",
            ]
        ),
        encoding="utf-8",
    )


def _build_config(source_csv_path: Path, work_csv_path: Path) -> dict:
    return {
        "data_source": {
            "symbol": "BTC/USDT",
            "ohlcv_csv_path": str(source_csv_path),
        },
        "replay": {
            "work_csv_path": str(work_csv_path),
            "warmup_rows": 2,
            "mode": "fast",
            "tick_interval_seconds": 0.0,
            "emit_progress_log": True,
        },
        "strategy": {
            "name": "threshold_replay_test",
            "simulation_name": "threshold_replay_test",
            "strategy": "threshold",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "entry_threshold": 0.015,
            "exit_threshold": -0.03,
        },
    }


def test_initialize_work_csv_rejects_same_path(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "source.csv"
    _write_source_csv(source_csv_path)

    with pytest.raises(ValueError, match="work_csv_path must be different from ohlcv_csv_path"):
        initialize_work_csv(source_csv_path, source_csv_path)


def test_load_pseudo_realtime_config_validates_required_sections() -> None:
    with pytest.raises(ValueError, match="pseudo-realtime config must include a data_source dict"):
        load_pseudo_realtime_config({"replay": {}, "strategy": {}})

    with pytest.raises(ValueError, match="replay must include warmup_rows"):
        load_pseudo_realtime_config(
            {
                "data_source": {"ohlcv_csv_path": "data.csv"},
                "replay": {"work_csv_path": "work.csv"},
                "strategy": {"initial_cash": 1000},
            }
        )


def test_pseudo_realtime_replay_appends_rows_and_emits_logs(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "source.csv"
    work_csv_path = tmp_path / "work.csv"
    _write_source_csv(source_csv_path)
    config = _build_config(source_csv_path, work_csv_path)

    result = run_pseudo_realtime_replay(config)

    work_rows = work_csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(work_rows) == 6

    assert len(result["decision_log"]) == 5
    assert len(result["equity_history"]) == 5
    assert len(result["progress_log"]) == 5
    assert result["decision_log"][0]["phase"] == "warmup"
    assert result["decision_log"][1]["phase"] == "warmup"
    assert result["decision_log"][2]["phase"] == "replay"
    assert result["decision_log"][0]["signal_reason_code"] == "warmup_pending"
    assert result["decision_log"][2]["signal_reason_code"] == "no_signal"
    assert result["decision_log"][3]["signal_reason_code"] == "threshold_entry_signal"
    assert result["decision_log"][3]["action_reason_code"] == "enter_position"
    assert result["decision_log"][4]["action_reason_code"] == "exit_position"
    assert result["summary"]["evaluated_ticks"] == 3
    assert result["summary"]["trade_count"] == 1
    assert result["summary"]["open_position_at_end"] is False
    assert result["trade_log"][0]["entry_index"] == 2
    assert result["trade_log"][0]["exit_index"] == 3


def test_pseudo_realtime_replay_respects_warmup_rows_before_judgment(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "source.csv"
    work_csv_path = tmp_path / "work.csv"
    _write_source_csv(source_csv_path)
    config = _build_config(source_csv_path, work_csv_path)
    config["replay"]["warmup_rows"] = 3

    result = run_pseudo_realtime_replay(config)

    assert [entry["phase"] for entry in result["decision_log"]] == [
        "warmup",
        "warmup",
        "warmup",
        "replay",
        "replay",
    ]
    assert result["decision_log"][3]["signal_reason_code"] == "threshold_entry_signal"
    assert result["decision_log"][3]["action_reason_code"] == "enter_position"
    assert result["decision_log"][4]["action_reason_code"] == "exit_position"


def test_pseudo_realtime_replay_reloads_work_csv_each_tick_after_warmup(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "source.csv"
    work_csv_path = tmp_path / "work.csv"
    _write_source_csv(source_csv_path)
    config = _build_config(source_csv_path, work_csv_path)

    result = run_pseudo_realtime_replay(config)

    replay_entries = [entry for entry in result["decision_log"] if entry["phase"] == "replay"]
    assert [entry["return_timestamp"] for entry in replay_entries] == [
        "2024-01-01T02:00:00Z",
        "2024-01-01T03:00:00Z",
        "2024-01-01T04:00:00Z",
    ]
    assert result["replay"]["evaluation_mode"] == "reload_work_csv_and_recompute_full_history_each_tick"


def test_pseudo_realtime_replay_raises_for_short_source_data(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "short.csv"
    source_csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2024-01-01T00:00:00Z,100,101,99,100,10",
                "2024-01-01T01:00:00Z,100,101,99,101,11",
            ]
        ),
        encoding="utf-8",
    )
    config = _build_config(source_csv_path, tmp_path / "work.csv")
    config["replay"]["warmup_rows"] = 2

    with pytest.raises(ValueError, match="source OHLCV csv must include more rows than warmup_rows"):
        run_pseudo_realtime_replay(config)


def test_pseudo_realtime_replay_raises_for_missing_required_column(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "bad.csv"
    source_csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,volume",
                "2024-01-01T00:00:00Z,100,101,99,10",
            ]
        ),
        encoding="utf-8",
    )
    config = _build_config(source_csv_path, tmp_path / "work.csv")

    with pytest.raises(ValueError, match="missing required OHLCV columns: close"):
        run_pseudo_realtime_replay(config)


def test_pseudo_realtime_replay_realtime_mode_uses_sleep_fn_without_flaky_waits(tmp_path: Path) -> None:
    source_csv_path = tmp_path / "source.csv"
    work_csv_path = tmp_path / "work.csv"
    _write_source_csv(source_csv_path)
    config = _build_config(source_csv_path, work_csv_path)
    config["replay"]["mode"] = "realtime"
    config["replay"]["tick_interval_seconds"] = 0.25

    sleep_calls = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    result = run_pseudo_realtime_replay(config, sleep_fn=fake_sleep)

    assert result["summary"]["evaluated_ticks"] == 3
    assert sleep_calls == [0.25, 0.25, 0.25, 0.25]


def test_pseudo_realtime_cli_main_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source_csv_path = tmp_path / "source.csv"
    work_csv_path = tmp_path / "work.csv"
    config_path = tmp_path / "pseudo_realtime.json"
    _write_source_csv(source_csv_path)

    config = _build_config(source_csv_path, work_csv_path)
    config_path.write_text(
        Path("config/pseudo_realtime_replay.example.json").read_text(encoding="utf-8").replace(
            "data/btcusdt_1h_sample.csv",
            str(source_csv_path),
        ).replace(
            "var/btcusdt_1h_replay_work.csv",
            str(work_csv_path),
        ),
        encoding="utf-8",
    )

    assert load_config(config_path)["replay"]["work_csv_path"] == str(work_csv_path)

    exit_code = pseudo_realtime_main(["--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"summary"' in captured.out
    assert '"decision_log"' in captured.out
