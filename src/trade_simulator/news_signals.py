from __future__ import annotations

from pathlib import Path

from trade_simulator.external_signal_common import (
    _require_finite_number,
    _require_non_empty_string,
    _require_optional_string,
    load_json_or_ndjson,
    normalize_symbol_for_external_signal,
    normalize_timestamp_to_utc_z,
    normalize_topic,
)


def normalize_news_signal_record(record: object, *, entry_name: str = "news_signal") -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"{entry_name} must be a dict")

    normalized = dict(record)
    normalized["source"] = _require_non_empty_string(record.get("source"), f"{entry_name}.source").lower()
    normalized["published_at"] = normalize_timestamp_to_utc_z(record.get("published_at"), f"{entry_name}.published_at")
    normalized["headline"] = _require_non_empty_string(record.get("headline"), f"{entry_name}.headline")
    normalized["relevance_score"] = _require_finite_number(record.get("relevance_score"), f"{entry_name}.relevance_score")
    normalized["sentiment_score"] = _require_finite_number(record.get("sentiment_score"), f"{entry_name}.sentiment_score")
    normalized["impact_score"] = _require_finite_number(record.get("impact_score"), f"{entry_name}.impact_score")
    normalized["category"] = _require_non_empty_string(record.get("category"), f"{entry_name}.category").lower()

    raw_symbol = _require_optional_string(record.get("symbol"), f"{entry_name}.symbol")
    raw_asset = _require_optional_string(record.get("asset"), f"{entry_name}.asset")
    raw_topic = _require_optional_string(record.get("topic"), f"{entry_name}.topic")
    if raw_symbol is None and raw_asset is None and raw_topic is None:
        raise ValueError(f"{entry_name} must include symbol, asset, or topic")

    normalized["symbol"] = normalize_symbol_for_external_signal(raw_symbol) if raw_symbol is not None else None
    normalized["asset"] = normalize_symbol_for_external_signal(raw_asset) if raw_asset is not None else None
    normalized["topic"] = normalize_topic(raw_topic) if raw_topic is not None else None

    url = _require_optional_string(record.get("url"), f"{entry_name}.url")
    source_id = _require_optional_string(record.get("source_id"), f"{entry_name}.source_id")
    if url is None and source_id is None:
        raise ValueError(f"{entry_name} must include url or source_id")
    normalized["url"] = url
    normalized["source_id"] = source_id

    metadata = record.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{entry_name}.metadata must be a dict")
    normalized["metadata"] = dict(metadata)

    entity_key = normalized["symbol"] or normalized["asset"] or normalized["topic"]
    entity_kind = "symbol" if normalized["symbol"] is not None else ("asset" if normalized["asset"] is not None else "topic")
    normalized["entity_key"] = entity_key
    normalized["entity_kind"] = entity_kind
    return normalized


def normalize_news_signal_records(records: object) -> list[dict]:
    if not isinstance(records, list):
        raise TypeError("news signal records must be a list")
    normalized = [
        normalize_news_signal_record(record, entry_name=f"news_signals[{index}]") for index, record in enumerate(records)
    ]
    normalized.sort(key=lambda record: (record["published_at"], record["source"], record["entity_key"], record["headline"]))
    return normalized


def build_news_signal_bundle(records: object) -> dict:
    normalized_records = normalize_news_signal_records(records)
    by_symbol: dict[str, list[dict]] = {}
    by_asset: dict[str, list[dict]] = {}
    by_topic: dict[str, list[dict]] = {}

    for record in normalized_records:
        if record["symbol"] is not None:
            by_symbol.setdefault(record["symbol"], []).append(record)
        if record["asset"] is not None:
            by_asset.setdefault(record["asset"], []).append(record)
        if record["topic"] is not None:
            by_topic.setdefault(record["topic"], []).append(record)

    summary = {
        "record_count": len(normalized_records),
        "sources": sorted({record["source"] for record in normalized_records}),
        "symbols": sorted(by_symbol),
        "assets": sorted(by_asset),
        "topics": sorted(by_topic),
        "first_published_at": normalized_records[0]["published_at"] if normalized_records else None,
        "last_published_at": normalized_records[-1]["published_at"] if normalized_records else None,
        "max_relevance_score": max((record["relevance_score"] for record in normalized_records), default=None),
        "max_impact_score": max((record["impact_score"] for record in normalized_records), default=None),
    }

    return {
        "signal_type": "news",
        "schema_version": "1.0",
        "records": normalized_records,
        "by_symbol": by_symbol,
        "by_asset": by_asset,
        "by_topic": by_topic,
        "summary": summary,
    }


def load_news_signal_bundle(path: str | Path) -> dict:
    return build_news_signal_bundle(load_json_or_ndjson(path))


__all__ = [
    "build_news_signal_bundle",
    "load_news_signal_bundle",
    "normalize_news_signal_record",
    "normalize_news_signal_records",
]
