"""trade_simulator package."""

from trade_simulator.comparison import run_case, run_comparisons, summarize_case_result
from trade_simulator.data import build_close_to_close_returns, load_ohlcv_csv, load_returns_from_ohlcv_csv
from trade_simulator.live_decision_runner import load_live_decision_runner_config, run_live_decision_runner
from trade_simulator.pseudo_realtime_replay import load_pseudo_realtime_config, run_pseudo_realtime_replay
from trade_simulator.signals import (
    generate_consecutive_drop_signals,
    generate_cumulative_drop_signals,
    generate_threshold_signals,
    simulate_consecutive_drop_strategy,
    simulate_cumulative_drop_strategy,
    simulate_threshold_strategy,
)
from trade_simulator.simulation import simulate

__all__ = [
    "generate_consecutive_drop_signals",
    "generate_cumulative_drop_signals",
    "generate_threshold_signals",
    "build_close_to_close_returns",
    "load_ohlcv_csv",
    "load_live_decision_runner_config",
    "load_returns_from_ohlcv_csv",
    "load_pseudo_realtime_config",
    "run_case",
    "run_comparisons",
    "run_live_decision_runner",
    "run_pseudo_realtime_replay",
    "simulate",
    "simulate_consecutive_drop_strategy",
    "simulate_cumulative_drop_strategy",
    "simulate_threshold_strategy",
    "summarize_case_result",
]
