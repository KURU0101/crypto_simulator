"""trade_simulator package."""

from trade_simulator.comparison import run_case, run_comparisons, summarize_case_result
from trade_simulator.signals import generate_threshold_signals, simulate_threshold_strategy
from trade_simulator.simulation import simulate

__all__ = [
    "generate_threshold_signals",
    "run_case",
    "run_comparisons",
    "simulate",
    "simulate_threshold_strategy",
    "summarize_case_result",
]
