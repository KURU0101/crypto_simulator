from __future__ import annotations

from pathlib import Path

from trade_simulator.data.ohlcv import load_returns_from_ohlcv_csv


def normalize_symbol(symbol: str) -> str:
    return "".join(character.lower() for character in symbol if character.isalnum())


def build_symbol_work_csv_path(work_dir: str | Path, symbol: str) -> str:
    return str(Path(work_dir) / f"{normalize_symbol(symbol)}_replay_work.csv")


def _validate_source_entry(source: object, *, entry_name: str) -> dict:
    if not isinstance(source, dict):
        raise ValueError(f"{entry_name} must be a dict")
    if "symbol" not in source:
        raise ValueError(f"{entry_name} must include symbol")
    if "ohlcv_csv_path" not in source:
        raise ValueError(f"{entry_name} must include ohlcv_csv_path")
    if not isinstance(source["symbol"], str) or not source["symbol"].strip():
        raise TypeError(f"{entry_name} symbol must be a non-empty string")
    if not isinstance(source["ohlcv_csv_path"], str) or not source["ohlcv_csv_path"].strip():
        raise TypeError(f"{entry_name} ohlcv_csv_path must be a non-empty string")

    normalized_source = dict(source)
    normalized_source["symbol"] = source["symbol"].strip()
    normalized_source["ohlcv_csv_path"] = source["ohlcv_csv_path"].strip()
    return normalized_source


def load_data_sources_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("data source config must be a dict")

    if "data_sources" in config:
        raw_data_sources = config["data_sources"]
        if not isinstance(raw_data_sources, dict):
            raise ValueError("data_sources must be a dict")
        if "symbols" not in raw_data_sources:
            raise ValueError("data_sources must include symbols")
        if not isinstance(raw_data_sources["symbols"], list):
            raise ValueError("data_sources symbols must be a list")

        sources = [
            _validate_source_entry(source, entry_name=f"data_sources.symbols[{index}]")
            for index, source in enumerate(raw_data_sources["symbols"])
        ]
        default_symbol = raw_data_sources.get("default_symbol")
    elif "data_source" in config:
        sources = [_validate_source_entry(config["data_source"], entry_name="data_source")]
        default_symbol = config["data_source"].get("symbol")
    else:
        raise ValueError("config must include data_source or data_sources")

    if not sources:
        raise ValueError("at least one data source is required")

    symbols = [source["symbol"] for source in sources]
    if len(set(symbols)) != len(symbols):
        raise ValueError("symbol must be unique across data sources")

    if default_symbol is None:
        default_symbol = symbols[0]
    if not isinstance(default_symbol, str) or not default_symbol.strip():
        raise TypeError("default_symbol must be a non-empty string")
    if default_symbol not in symbols:
        raise ValueError("default_symbol must match one of the configured symbols")

    return {
        "default_symbol": default_symbol,
        "symbols": list(symbols),
        "sources": sources,
        "sources_by_symbol": {source["symbol"]: source for source in sources},
    }


def select_data_source(config: object, symbol: str | None = None) -> dict:
    data_sources = load_data_sources_config(config)
    selected_symbol = symbol or data_sources["default_symbol"]
    if selected_symbol not in data_sources["sources_by_symbol"]:
        raise ValueError(f"symbol must be one of: {', '.join(data_sources['symbols'])}")
    return dict(data_sources["sources_by_symbol"][selected_symbol])


def load_returns_by_symbol(config: object) -> dict[str, dict]:
    data_sources = load_data_sources_config(config)
    returns_by_symbol: dict[str, dict] = {}

    for source in data_sources["sources"]:
        returns_payload = load_returns_from_ohlcv_csv(source["ohlcv_csv_path"])
        returns_by_symbol[source["symbol"]] = {
            "symbol": source["symbol"],
            "ohlcv_csv_path": source["ohlcv_csv_path"],
            "price_basis": returns_payload["price_basis"],
            "timestamps": returns_payload["timestamps"],
            "return_timestamps": returns_payload["return_timestamps"],
            "returns": returns_payload["returns"],
        }

    return returns_by_symbol


def summarize_data_sources(config: object) -> dict:
    data_sources = load_data_sources_config(config)
    returns_by_symbol = load_returns_by_symbol(config)

    return {
        "default_symbol": data_sources["default_symbol"],
        "symbols": [
            {
                "symbol": symbol,
                "symbol_slug": normalize_symbol(symbol),
                "ohlcv_csv_path": returns_by_symbol[symbol]["ohlcv_csv_path"],
                "price_basis": returns_by_symbol[symbol]["price_basis"],
                "ohlcv_points": len(returns_by_symbol[symbol]["timestamps"]),
                "returns_count": len(returns_by_symbol[symbol]["returns"]),
                "first_timestamp": returns_by_symbol[symbol]["timestamps"][0],
                "last_timestamp": returns_by_symbol[symbol]["timestamps"][-1],
            }
            for symbol in data_sources["symbols"]
        ],
    }
