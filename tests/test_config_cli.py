from pathlib import Path

import pytest

from trade_simulator.comparison import run_comparisons
from trade_simulator.comparison_cli import format_comparison_results, load_comparison_cases, main as comparison_main
from trade_simulator.config import load_config


def test_package_imports() -> None:
    import trade_simulator  # noqa: F401


def test_load_config() -> None:
    config_path = Path("config/simulation.example.json")
    config = load_config(config_path)

    assert config["simulation_name"] == "example_simulation"
    assert config["initial_cash"] == 100000
    assert config["fee_rate"] == 0.0
    assert config["slippage_rate"] == 0.0
    assert config["returns"] == [0.01, -0.02, 0.03, 0.01]
    assert config["entry_signals"] == [True, False, True, False]
    assert config["exit_signals"] == [False, True, False, False]


def test_load_comparison_config() -> None:
    config_path = Path("config/comparison.example.json")
    cases = load_config(config_path)

    assert len(cases) == 6
    assert cases[0]["name"] == "threshold_baseline"
    assert cases[0]["strategy"] == "threshold"
    assert cases[1]["name"] == "threshold_with_cost"
    assert cases[1]["fee_rate"] == 0.001
    assert cases[1]["slippage_rate"] == 0.001
    assert cases[2]["name"] == "cumulative_drop_fast"
    assert cases[2]["strategy"] == "cumulative_drop"
    assert cases[2]["entry_window"] == 3
    assert cases[3]["name"] == "cumulative_drop_strict"
    assert cases[3]["entry_cumulative_threshold"] == -0.026
    assert cases[4]["name"] == "consecutive_drop_fast"
    assert cases[4]["strategy"] == "consecutive_drop"
    assert cases[5]["name"] == "consecutive_drop_strict"
    assert cases[5]["consecutive_periods"] == 4
    assert all(case["initial_cash"] == 100000 for case in cases)


def test_load_comparison_cases_accepts_root_list_config() -> None:
    cases = load_comparison_cases("config/comparison.example.json")

    assert len(cases) == 6
    assert cases[0]["name"] == "threshold_baseline"
    assert cases[-1]["name"] == "consecutive_drop_strict"


def test_load_comparison_cases_reads_cases_from_dict_config(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text(
        """
        {
          "cases": [
            {
              "name": "single",
              "simulation_name": "single",
              "initial_cash": 1000,
              "strategy": "cumulative_drop",
              "fee_rate": 0.0,
              "slippage_rate": 0.0,
              "returns": [],
              "entry_window": 3,
              "entry_cumulative_threshold": -0.01,
              "exit_threshold": 0.005
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    cases = load_comparison_cases(str(config_path))

    assert cases == [
        {
            "name": "single",
            "simulation_name": "single",
            "initial_cash": 1000,
            "strategy": "cumulative_drop",
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [],
            "entry_window": 3,
            "entry_cumulative_threshold": -0.01,
            "exit_threshold": 0.005,
        }
    ]


def test_load_comparison_cases_raises_when_cases_key_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"name": "missing_cases"}', encoding="utf-8")

    with pytest.raises(ValueError, match="comparison config must be a list or include a cases list"):
        load_comparison_cases(str(config_path))


def test_load_comparison_cases_raises_when_cases_is_not_a_list(tmp_path: Path) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"cases": {"name": "invalid"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="comparison config cases must be a list"):
        load_comparison_cases(str(config_path))


def test_format_comparison_results_returns_json_with_summary_fields() -> None:
    results = [
        {
            "name": "baseline",
            "final_value": 1000.0,
            "trade_count": 0,
            "completed_trade_count": 0,
            "open_trade_count": 0,
            "periods_in_position": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "realized_pnl_total": 0.0,
            "total_realized_pnl": 0.0,
            "average_pnl_per_completed_trade": 0.0,
            "average_holding_period": 0.0,
            "total_cost_amount": 0.0,
            "strategy": "threshold",
            "entry_threshold": 0.01,
            "exit_threshold": -0.01,
        }
    ]

    formatted = format_comparison_results(results)

    assert '"name": "baseline"' in formatted
    assert '"final_value": 1000.0' in formatted
    assert '"strategy": "threshold"' in formatted
    assert '"completed_trade_count": 0' in formatted
    assert '"total_realized_pnl": 0.0' in formatted
    assert '"total_cost_amount": 0.0' in formatted


def test_comparison_main_prints_same_results_as_run_comparisons(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = comparison_main(["--config", "config/comparison.example.json"])

    captured = capsys.readouterr()
    results = load_config(Path("config/comparison.example.json"))

    assert exit_code == 0
    assert captured.out == format_comparison_results(run_comparisons(results)) + "\n"


def test_comparison_main_handles_empty_cases_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "comparison.json"
    config_path.write_text('{"cases": []}', encoding="utf-8")

    exit_code = comparison_main(["--config", str(config_path)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "[]\n"
