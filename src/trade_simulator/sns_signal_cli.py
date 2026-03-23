from __future__ import annotations

from trade_simulator.external_signal_cli import run_external_signal_cli
from trade_simulator.sns_signals import load_sns_signal_bundle


def main(argv: list[str] | None = None) -> int:
    return run_external_signal_cli(argv, signal_type="sns", loader=load_sns_signal_bundle)
