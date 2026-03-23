from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trade_simulator.data.ohlcv import build_close_to_close_returns, normalize_ohlcv_rows
from trade_simulator.signals import generate_threshold_signals
from trade_simulator.simulation import simulate


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
CASE_DEFINITIONS = [
    {"name": "baseline", "entry_threshold": 0.0015, "exit_threshold": -0.001},
    {"name": "entry_strict", "entry_threshold": 0.0018, "exit_threshold": -0.001},
    {"name": "exit_loose", "entry_threshold": 0.0015, "exit_threshold": -0.0015},
    {"name": "exit_tight", "entry_threshold": 0.0015, "exit_threshold": -0.0007},
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch local comparison days from Binance 1m klines and analyze fixed threshold cases."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--scan-start", required=True, help="Start date in YYYY-MM-DD (UTC)")
    parser.add_argument("--scan-end", required=True, help="End date in YYYY-MM-DD (UTC, inclusive)")
    parser.add_argument(
        "--select-date",
        action="append",
        default=[],
        help="Explicit day to compare in YYYY-MM-DD. When omitted, days are auto-selected from the scan range.",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path for the full analysis report.",
    )
    parser.add_argument(
        "--save-csv-dir",
        help="Optional directory to save fetched OHLCV day CSVs.",
    )
    return parser


def parse_utc_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("scan-end must be on or after scan-start")

    current = start_date
    dates = []
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def fetch_1m_klines_for_day(symbol: str, target_date: date) -> list[dict]:
    start_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    rows: list[dict] = []

    while True:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": "1m",
                "limit": 1000,
                "startTime": start_ms,
                "endTime": end_ms,
            }
        )
        url = f"{BINANCE_SPOT_KLINES_URL}?{query}"
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, list):
            raise ValueError("Binance kline response must be a list")
        if not payload:
            break

        for item in payload:
            if not isinstance(item, list) or len(item) < 6:
                raise ValueError("Binance kline item must be a list with at least 6 elements")
            open_time_ms = int(item[0])
            rows.append(
                {
                    "timestamp": datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume": item[5],
                }
            )

        last_open_time_ms = int(payload[-1][0])
        next_start_ms = last_open_time_ms + 60_000
        if next_start_ms >= end_ms or len(payload) < 1000:
            break
        start_ms = next_start_ms

    normalized_rows = normalize_ohlcv_rows(rows)
    return normalized_rows


def maybe_save_csv(rows: list[dict], output_dir: str | None, symbol: str, target_date: date) -> str | None:
    if output_dir is None:
        return None

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    csv_path = path / f"{symbol.lower()}_{target_date.isoformat()}_1m.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(
            {
                "timestamp": row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in rows
        )
    return str(csv_path)


def calculate_day_profile(rows: list[dict]) -> dict:
    closes = [float(row["close"]) for row in rows]
    returns_payload = build_close_to_close_returns(rows)
    returns = returns_payload["returns"]
    signed_periods = [1 if period > 0 else -1 if period < 0 else 0 for period in returns]
    sign_changes = sum(1 for previous, current in zip(signed_periods, signed_periods[1:]) if previous != current)
    absolute_return = abs((closes[-1] / closes[0]) - 1.0)
    realized_vol = sum(abs(period) for period in returns)
    volatility_efficiency = 0.0 if realized_vol == 0 else absolute_return / realized_vol

    return {
        "row_count": len(rows),
        "return_count": len(returns),
        "first_timestamp": rows[0]["timestamp"],
        "last_timestamp": rows[-1]["timestamp"],
        "open_price": closes[0],
        "close_price": closes[-1],
        "high_price": max(float(row["high"]) for row in rows),
        "low_price": min(float(row["low"]) for row in rows),
        "daily_return": (closes[-1] / closes[0]) - 1.0,
        "realized_volatility_sum_abs_return": realized_vol,
        "volatility_efficiency": volatility_efficiency,
        "sign_change_count": sign_changes,
        "positive_return_count": sum(1 for period in returns if period > 0),
        "negative_return_count": sum(1 for period in returns if period < 0),
    }


def select_comparison_days(day_profiles: dict[str, dict]) -> list[dict]:
    available = [(day, profile) for day, profile in day_profiles.items() if profile["return_count"] > 0]
    if len(available) < 3:
        raise ValueError("at least three days with returns are required")

    upward_day, upward_profile = max(available, key=lambda item: item[1]["daily_return"])
    downward_candidates = [item for item in available if item[0] != upward_day]
    downward_day, downward_profile = min(
        downward_candidates,
        key=lambda item: (item[1]["daily_return"], -item[1]["sign_change_count"]),
    )
    sideways_candidates = [item for item in available if item[0] not in {upward_day, downward_day}]
    sideways_day, sideways_profile = min(
        sideways_candidates,
        key=lambda item: (
            abs(item[1]["daily_return"]),
            -item[1]["sign_change_count"],
            item[1]["volatility_efficiency"],
        ),
    )

    return [
        {
            "date": upward_day,
            "pattern": "upward_bias",
            "reason": (
                "scan range 内で daily_return が最も大きく、上昇優位日の比較対象として扱いやすい"
            ),
            "profile": upward_profile,
        },
        {
            "date": sideways_day,
            "pattern": "sideways_noisy",
            "reason": (
                "daily_return が小さく、符号反転が多いため横ばい / ノイズ多めとして扱いやすい"
            ),
            "profile": sideways_profile,
        },
        {
            "date": downward_day,
            "pattern": "downward_or_reversal",
            "reason": (
                "scan range 内で daily_return が最も弱く、下落または反転優位の確認に使いやすい"
            ),
            "profile": downward_profile,
        },
    ]


def analyze_case(day_rows: list[dict], case_definition: dict) -> dict:
    returns_payload = build_close_to_close_returns(day_rows)
    returns = returns_payload["returns"]
    return_timestamps = returns_payload["return_timestamps"]
    entry_signals, exit_signals = generate_threshold_signals(
        returns,
        case_definition["entry_threshold"],
        case_definition["exit_threshold"],
    )
    simulation_result = simulate(
        {
            "simulation_name": case_definition["name"],
            "initial_cash": 100000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": returns,
            "entry_signals": entry_signals,
            "exit_signals": exit_signals,
        }
    )

    completed_trades = []
    open_trades = []
    for trade_index, trade in enumerate(simulation_result["trade_log"]):
        trade_snapshot = {
            "trade_index": trade_index,
            "entry_index": trade["entry_index"],
            "entry_timestamp": return_timestamps[trade["entry_index"]],
            "holding_periods": trade["holding_periods"],
            "pnl_amount": trade["pnl_amount"],
            "exited": trade["exited"],
        }
        if trade["exit_index"] is not None:
            trade_snapshot["exit_index"] = trade["exit_index"]
            trade_snapshot["exit_timestamp"] = return_timestamps[trade["exit_index"]]
        if trade["exited"]:
            completed_trades.append(trade_snapshot)
        else:
            open_trades.append(trade_snapshot)

    reentry_opportunities_blocked = 0
    blocked_examples = []
    position = simulation_result["position"]
    for period_index, is_in_position in enumerate(position):
        if is_in_position and returns[period_index] >= case_definition["entry_threshold"]:
            reentry_opportunities_blocked += 1
            if len(blocked_examples) < 5:
                blocked_examples.append(
                    {
                        "timestamp": return_timestamps[period_index],
                        "period_return": returns[period_index],
                    }
                )

    wasted_trade_candidates = [
        trade
        for trade in completed_trades
        if trade["pnl_amount"] <= 0 and trade["holding_periods"] <= 3
    ]

    best_trades = sorted(completed_trades, key=lambda trade: trade["pnl_amount"], reverse=True)[:3]
    worst_trades = sorted(completed_trades, key=lambda trade: trade["pnl_amount"])[:3]
    open_position_at_end = bool(position and position[-1])

    return {
        "case": case_definition,
        "summary": {
            "trade_count": simulation_result["trade_count"],
            "realized_pnl_total": simulation_result["realized_pnl_total"],
            "periods_in_position": simulation_result["periods_in_position"],
            "open_position_at_end": open_position_at_end,
            "entry_signal_count": sum(1 for signal in entry_signals if signal),
            "exit_signal_count": sum(1 for signal in exit_signals if signal),
            "completed_trade_count": len(completed_trades),
            "open_trade_count": len(open_trades),
            "winning_trades": simulation_result["winning_trades"],
            "losing_trades": simulation_result["losing_trades"],
            "average_holding_period": simulation_result["average_holding_period"],
            "reentry_opportunities_blocked": reentry_opportunities_blocked,
            "wasted_trade_candidate_count": len(wasted_trade_candidates),
        },
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "wasted_trade_candidates": wasted_trade_candidates[:5],
        "blocked_reentry_examples": blocked_examples,
        "open_trades": open_trades,
        "signal_counts_by_return_bucket": summarize_signal_buckets(returns, entry_signals, exit_signals),
    }


def summarize_signal_buckets(
    returns: list[float],
    entry_signals: list[bool],
    exit_signals: list[bool],
) -> dict[str, dict[str, int]]:
    entry_counter: Counter[str] = Counter()
    exit_counter: Counter[str] = Counter()
    for period_return, entry_signal, exit_signal in zip(returns, entry_signals, exit_signals):
        bucket = classify_return_bucket(period_return)
        if entry_signal:
            entry_counter[bucket] += 1
        if exit_signal:
            exit_counter[bucket] += 1
    return {
        "entry": dict(entry_counter),
        "exit": dict(exit_counter),
    }


def classify_return_bucket(period_return: float) -> str:
    if period_return <= -0.003:
        return "<=-0.30%"
    if period_return <= -0.0015:
        return "(-0.30%,-0.15%]"
    if period_return <= -0.0007:
        return "(-0.15%,-0.07%]"
    if period_return < 0:
        return "(-0.07%,0%)"
    if period_return < 0.0015:
        return "[0%,0.15%)"
    if period_return < 0.003:
        return "[0.15%,0.30%)"
    return ">=0.30%"


def build_report(args: argparse.Namespace) -> dict:
    start_date = parse_utc_date(args.scan_start)
    end_date = parse_utc_date(args.scan_end)
    scan_dates = iter_dates(start_date, end_date)

    fetched_days: dict[str, list[dict]] = {}
    day_profiles: dict[str, dict] = {}
    saved_csv_paths: dict[str, str] = {}

    for target_date in scan_dates:
        rows = fetch_1m_klines_for_day(args.symbol, target_date)
        day_key = target_date.isoformat()
        fetched_days[day_key] = rows
        day_profiles[day_key] = calculate_day_profile(rows)
        saved_csv_path = maybe_save_csv(rows, args.save_csv_dir, args.symbol, target_date)
        if saved_csv_path is not None:
            saved_csv_paths[day_key] = saved_csv_path

    if args.select_date:
        selected_days = []
        for day_key in args.select_date:
            if day_key not in fetched_days:
                raise ValueError(f"selected date is outside the fetched range or unavailable: {day_key}")
            selected_days.append(
                {
                    "date": day_key,
                    "pattern": "explicit",
                    "reason": "明示指定された比較対象日",
                    "profile": day_profiles[day_key],
                }
            )
    else:
        selected_days = select_comparison_days(day_profiles)

    comparisons = []
    for selection in selected_days:
        day_key = selection["date"]
        day_rows = fetched_days[day_key]
        comparisons.append(
            {
                "selection": selection,
                "saved_csv_path": saved_csv_paths.get(day_key),
                "cases": [analyze_case(day_rows, case_definition) for case_definition in CASE_DEFINITIONS],
            }
        )

    return {
        "symbol": args.symbol,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "scan_day_profiles": day_profiles,
        "selected_days": selected_days,
        "case_definitions": CASE_DEFINITIONS,
        "comparisons": comparisons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_report(args)
    formatted = json.dumps(report, ensure_ascii=False, indent=2)
    print(formatted)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(formatted + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
