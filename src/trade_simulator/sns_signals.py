from __future__ import annotations

from pathlib import Path

from trade_simulator.external_signal_common import (
    _require_finite_number,
    _require_non_empty_string,
    _require_non_negative_int,
    _require_optional_string,
    load_json_or_ndjson,
    normalize_symbol_for_external_signal,
    normalize_timestamp_to_utc_z,
    normalize_topic,
)


def normalize_sns_signal_record(record: object, *, entry_name: str = "sns_signal") -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"{entry_name} must be a dict")

    normalized = dict(record)
    normalized["source"] = _require_non_empty_string(record.get("source"), f"{entry_name}.source").lower()
    normalized["timestamp"] = normalize_timestamp_to_utc_z(record.get("timestamp"), f"{entry_name}.timestamp")
    normalized["mention_count"] = _require_non_negative_int(record.get("mention_count"), f"{entry_name}.mention_count")
    normalized["positive_score"] = _require_finite_number(record.get("positive_score"), f"{entry_name}.positive_score")
    normalized["negative_score"] = _require_finite_number(record.get("negative_score"), f"{entry_name}.negative_score")
    normalized["neutral_score"] = _require_finite_number(record.get("neutral_score"), f"{entry_name}.neutral_score")
    normalized["activity_score"] = _require_finite_number(record.get("activity_score"), f"{entry_name}.activity_score")
    normalized["anomaly_score"] = _require_finite_number(record.get("anomaly_score"), f"{entry_name}.anomaly_score")

    raw_symbol = _require_optional_string(record.get("symbol"), f"{entry_name}.symbol")
    raw_topic = _require_optional_string(record.get("topic"), f"{entry_name}.topic")
    if raw_symbol is None and raw_topic is None:
        raise ValueError(f"{entry_name} must include symbol or topic")

    normalized["symbol"] = normalize_symbol_for_external_signal(raw_symbol) if raw_symbol is not None else None
    normalized["topic"] = normalize_topic(raw_topic) if raw_topic is not None else None

    metadata = record.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{entry_name}.metadata must be a dict")
    normalized["metadata"] = dict(metadata)

    normalized["entity_key"] = normalized["symbol"] if normalized["symbol"] is not None else normalized["topic"]
    normalized["entity_kind"] = "symbol" if normalized["symbol"] is not None else "topic"
    return normalized


def normalize_sns_signal_records(records: object) -> list[dict]:
    if not isinstance(records, list):
        raise TypeError("sns signal records must be a list")
    normalized = [
        normalize_sns_signal_record(record, entry_name=f"sns_signals[{index}]") for index, record in enumerate(records)
    ]
    normalized.sort(key=lambda record: (record["timestamp"], record["source"], record["entity_key"]))
    return normalized


def build_sns_signal_bundle(records: object) -> dict:
    normalized_records = normalize_sns_signal_records(records)
    by_symbol: dict[str, list[dict]] = {}
    by_topic: dict[str, list[dict]] = {}

    for record in normalized_records:
        if record["symbol"] is not None:
            by_symbol.setdefault(record["symbol"], []).append(record)
        if record["topic"] is not None:
            by_topic.setdefault(record["topic"], []).append(record)

    summary = {
        "record_count": len(normalized_records),
        "sources": sorted({record["source"] for record in normalized_records}),
        "symbols": sorted(by_symbol),
        "topics": sorted(by_topic),
        "first_timestamp": normalized_records[0]["timestamp"] if normalized_records else None,
        "last_timestamp": normalized_records[-1]["timestamp"] if normalized_records else None,
        "total_mentions": sum(record["mention_count"] for record in normalized_records),
        "max_activity_score": max((record["activity_score"] for record in normalized_records), default=None),
        "max_anomaly_score": max((record["anomaly_score"] for record in normalized_records), default=None),
    }

    return {
        "signal_type": "sns",
        "schema_version": "1.0",
        "records": normalized_records,
        "by_symbol": by_symbol,
        "by_topic": by_topic,
        "summary": summary,
    }


def load_sns_signal_bundle(path: str | Path) -> dict:
    return build_sns_signal_bundle(load_json_or_ndjson(path))


__all__ = [
    "build_sns_signal_bundle",
    "load_sns_signal_bundle",
    "normalize_sns_signal_record",
    "normalize_sns_signal_records",
]
