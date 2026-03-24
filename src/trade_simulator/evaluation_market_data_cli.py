from __future__ import annotations

import argparse
import json

from trade_simulator._evaluation_market_data_shared_state import DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH
from trade_simulator.evaluation_market_data import (
    DEFAULT_MARKET_DATA_CACHE_ROOT,
    resolve_evaluation_market_data,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch or reuse cached market data for a single evaluation period.")
    parser.add_argument("--source", required=True, help="Public JSON market data source. Current minimum: binance_spot.")
    parser.add_argument("--symbol", required=True, help="Market symbol, for example BTCUSDT.")
    parser.add_argument("--start", required=True, help="Inclusive period start in ISO 8601 UTC.")
    parser.add_argument("--end", required=True, help="Exclusive period end in ISO 8601 UTC.")
    parser.add_argument("--interval", required=True, help="Exchange interval string, for example 1m or 1h.")
    parser.add_argument(
        "--cache-root",
        default=str(DEFAULT_MARKET_DATA_CACHE_ROOT),
        help="Directory where normalized OHLCV CSV artifacts are stored.",
    )
    parser.add_argument(
        "--shared-state-db-path",
        default=str(DEFAULT_MARKET_DATA_SHARED_STATE_DB_PATH),
        help="Path to the market data shared truth SQLite DB.",
    )
    parser.add_argument(
        "--period-signature",
        default="",
        help="Optional audit-only period signature. It is stored as metadata and not used for reuse decisions.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = resolve_evaluation_market_data(
        source=args.source,
        symbol=args.symbol,
        interval=args.interval,
        window_start=args.start,
        window_end=args.end,
        cache_root=args.cache_root,
        shared_state_db_path=args.shared_state_db_path,
        period_signature=args.period_signature,
    )
    render_payload = {
        "acquisition_key": result["acquisition_key"],
        "source": result["source"],
        "symbol": result["symbol"],
        "interval": result["interval"],
        "window_start": result["window_start"],
        "window_end": result["window_end"],
        "status": result["status"],
        "fetched": result["fetched"],
        "reused_existing_artifact": result["reused_existing_artifact"],
        "artifact_path": result["artifact_path"],
        "artifact_kind": result["artifact_kind"],
        "row_count": result["row_count"],
    }
    print(json.dumps(render_payload, ensure_ascii=False, indent=2))
    return 0
