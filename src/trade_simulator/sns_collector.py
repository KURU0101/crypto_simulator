from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trade_simulator.sns_adapters import REDDIT_SUBREDDIT_NEW_JSON_URL, SNS_SOURCE_PROFILES
from trade_simulator.sns_signals import build_sns_signal_bundle


class SnsCollectorError(Exception):
    """Raised when SNS collection fails."""


def _utc_now_iso(now_fn: Callable[[], float]) -> str:
    return datetime.fromtimestamp(now_fn(), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id_from_iso8601(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _validate_non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def fetch_reddit_listing(
    listing_url: str,
    *,
    timeout_seconds: int,
    urlopen_fn: Callable[..., object] | None = None,
) -> str:
    if urlopen_fn is None:
        urlopen_fn = urllib.request.urlopen

    request = urllib.request.Request(
        listing_url,
        headers={"User-Agent": "trade-simulator-sns-collector/0.1"},
        method="GET",
    )

    try:
        with urlopen_fn(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        detail = f": {body}" if body else ""
        raise SnsCollectorError(f"failed to fetch SNS listing: HTTP {error.code}{detail}") from error
    except urllib.error.URLError as error:
        raise SnsCollectorError(f"failed to fetch SNS listing: {error.reason}") from error
    except TimeoutError as error:
        raise SnsCollectorError("failed to fetch SNS listing: timeout") from error

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("utf-8", errors="replace")


def parse_reddit_listing_items(json_text: str, *, max_items: int) -> list[dict]:
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise SnsCollectorError("failed to parse SNS listing JSON") from error

    if not isinstance(payload, dict):
        raise SnsCollectorError("SNS listing payload must be a dict")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SnsCollectorError("SNS listing payload must include data dict")
    children = data.get("children")
    if not isinstance(children, list):
        raise SnsCollectorError("SNS listing payload must include data.children list")

    items: list[dict] = []
    for child in children[:max_items]:
        if not isinstance(child, dict):
            raise SnsCollectorError("SNS listing child must be a dict")
        item = child.get("data")
        if not isinstance(item, dict):
            raise SnsCollectorError("SNS listing child must include data dict")
        items.append(dict(item))
    return items


def load_sns_collector_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise ValueError("sns collector config must be a dict")
    if "collector" not in config or not isinstance(config["collector"], dict):
        raise ValueError("sns collector config must include a collector dict")
    if "output" not in config or not isinstance(config["output"], dict):
        raise ValueError("sns collector config must include an output dict")

    collector = dict(config["collector"])
    output = dict(config["output"])

    collector["source"] = _validate_non_empty_string(collector.get("source"), "collector.source")
    if collector["source"] not in SNS_SOURCE_PROFILES:
        supported = ", ".join(sorted(SNS_SOURCE_PROFILES))
        raise ValueError(f"collector.source must be one of: {supported}")

    profile = SNS_SOURCE_PROFILES[collector["source"]]
    collector["listing_url"] = _validate_non_empty_string(
        collector.get("listing_url", profile["default_listing_url"]),
        "collector.listing_url",
    )
    collector["timeout_seconds"] = _validate_positive_int(collector.get("timeout_seconds", 30), "collector.timeout_seconds")
    collector["max_items"] = _validate_positive_int(collector.get("max_items", 50), "collector.max_items")

    output["output_dir"] = _validate_non_empty_string(output.get("output_dir"), "output.output_dir")
    output["save_run_summary"] = bool(output.get("save_run_summary", True))

    return {
        "collector": collector,
        "output": output,
    }


def _empty_observation(*, source: str, listing_url: str, started_at: str) -> dict:
    return {
        "run_id": _run_id_from_iso8601(started_at),
        "status": "completed",
        "signal_type": "sns",
        "source": source,
        "listing_url": listing_url,
        "started_at": started_at,
        "ended_at": started_at,
        "duration_seconds": 0.0,
        "fetched_item_count": 0,
        "normalized_success_count": 0,
        "normalized_failure_count": 0,
        "validation_failure_count": 0,
        "saved_record_count": 0,
        "duplicate_count": 0,
        "missing_field_counts": {},
        "source_distribution": {},
        "symbol_distribution": {},
        "topic_distribution": {},
        "mention_count_summary": {"min": None, "max": None, "average": None, "total": 0},
        "timestamp_by_date": {},
        "timestamp_by_hour_utc": {},
        "warnings": [],
        "errors": [],
        "saved_paths": {},
    }


def _build_observation(
    *,
    source: str,
    listing_url: str,
    started_at: str,
    ended_at: str,
    fetched_item_count: int,
    normalized_records: list[dict],
    normalized_failures: list[dict],
    missing_field_counts: dict[str, int],
    saved_paths: dict[str, str],
    warnings: list[str],
) -> dict:
    source_distribution: dict[str, int] = {}
    symbol_distribution: dict[str, int] = {}
    topic_distribution: dict[str, int] = {}
    timestamp_by_date: dict[str, int] = {}
    timestamp_by_hour_utc: dict[str, int] = {}
    mention_counts: list[int] = []
    unique_dedup_keys: set[str] = set()

    for record in normalized_records:
        source_distribution[record["source"]] = source_distribution.get(record["source"], 0) + 1
        if record["symbol"] is not None:
            symbol_distribution[record["symbol"]] = symbol_distribution.get(record["symbol"], 0) + 1
        if record["topic"] is not None:
            topic_distribution[record["topic"]] = topic_distribution.get(record["topic"], 0) + 1
        mention_counts.append(record["mention_count"])
        if "dedup_key" in record:
            unique_dedup_keys.add(record["dedup_key"])
        timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        date_key = timestamp.strftime("%Y-%m-%d")
        hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00Z")
        timestamp_by_date[date_key] = timestamp_by_date.get(date_key, 0) + 1
        timestamp_by_hour_utc[hour_key] = timestamp_by_hour_utc.get(hour_key, 0) + 1

    started_at_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    ended_at_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    mention_count_summary = {
        "min": min(mention_counts) if mention_counts else None,
        "max": max(mention_counts) if mention_counts else None,
        "average": statistics.fmean(mention_counts) if mention_counts else None,
        "total": sum(mention_counts),
    }

    return {
        "run_id": _run_id_from_iso8601(started_at),
        "status": "completed",
        "signal_type": "sns",
        "source": source,
        "listing_url": listing_url,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": (ended_at_dt - started_at_dt).total_seconds(),
        "fetched_item_count": fetched_item_count,
        "normalized_success_count": len(normalized_records),
        "normalized_failure_count": len(normalized_failures),
        "validation_failure_count": len(normalized_failures),
        "saved_record_count": len(normalized_records),
        "duplicate_count": len(normalized_records) - len(unique_dedup_keys),
        "missing_field_counts": missing_field_counts,
        "source_distribution": source_distribution,
        "symbol_distribution": symbol_distribution,
        "topic_distribution": topic_distribution,
        "mention_count_summary": mention_count_summary,
        "timestamp_by_date": timestamp_by_date,
        "timestamp_by_hour_utc": timestamp_by_hour_utc,
        "warnings": warnings,
        "errors": normalized_failures,
        "saved_paths": saved_paths,
    }


def save_sns_collection_run(
    bundle: dict,
    observation: dict,
    *,
    output_dir: str,
    source: str,
    started_at: str,
    save_run_summary: bool,
) -> dict[str, str]:
    run_id = _run_id_from_iso8601(started_at)
    run_dir = Path(output_dir) / source / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = run_dir / "normalized.json"
    with normalized_path.open("w", encoding="utf-8") as file:
        json.dump(bundle, file, ensure_ascii=False, indent=2)
        file.write("\n")

    saved_paths = {"normalized": str(normalized_path)}
    if save_run_summary:
        summary_path = run_dir / "summary.json"
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(observation, file, ensure_ascii=False, indent=2)
            file.write("\n")
        saved_paths["summary"] = str(summary_path)

    return saved_paths


def run_sns_collector(
    config: dict,
    *,
    fetch_listing_fn: Callable[..., str] | None = None,
    now_fn: Callable[[], float] | None = None,
) -> dict:
    validated = load_sns_collector_config(config)
    collector = validated["collector"]
    output = validated["output"]
    profile = SNS_SOURCE_PROFILES[collector["source"]]

    if fetch_listing_fn is None:
        fetch_listing_fn = fetch_reddit_listing
    if now_fn is None:
        now_fn = time.time

    started_at = _utc_now_iso(now_fn)
    empty_observation = _empty_observation(
        source=collector["source"],
        listing_url=collector["listing_url"],
        started_at=started_at,
    )

    try:
        listing_text = fetch_listing_fn(
            collector["listing_url"],
            timeout_seconds=collector["timeout_seconds"],
        )
        items = parse_reddit_listing_items(listing_text, max_items=collector["max_items"])
    except Exception as error:
        ended_at = _utc_now_iso(now_fn)
        observation = dict(empty_observation)
        observation["status"] = "failed"
        observation["ended_at"] = ended_at
        observation["duration_seconds"] = (
            datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            - datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        ).total_seconds()
        observation["errors"] = [{"message": str(error)}]
        return {
            "bundle": build_sns_signal_bundle([]),
            "observation": observation,
        }

    tracked_fields = profile["required_item_fields"] + profile["tracked_optional_item_fields"]
    missing_field_counts = {field_name: 0 for field_name in tracked_fields}
    normalized_records: list[dict] = []
    normalized_failures: list[dict] = []

    for index, item in enumerate(items):
        for field_name in tracked_fields:
            value = item.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_field_counts[field_name] += 1

        try:
            normalized_records.append(
                profile["adapter"](
                    item,
                    fetched_at=started_at,
                    listing_url=collector["listing_url"],
                )
            )
        except Exception as error:
            normalized_failures.append(
                {
                    "item_index": index,
                    "title": item.get("title"),
                    "message": str(error),
                }
            )

    warnings: list[str] = []
    if not items:
        warnings.append("SNS listing returned no items")

    bundle = build_sns_signal_bundle(normalized_records)
    provisional_observation = _build_observation(
        source=collector["source"],
        listing_url=collector["listing_url"],
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=len(items),
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths={},
        warnings=warnings,
    )
    saved_paths = save_sns_collection_run(
        bundle,
        provisional_observation,
        output_dir=output["output_dir"],
        source=collector["source"],
        started_at=started_at,
        save_run_summary=output["save_run_summary"],
    )
    observation = _build_observation(
        source=collector["source"],
        listing_url=collector["listing_url"],
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=len(items),
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths=saved_paths,
        warnings=warnings,
    )
    if output["save_run_summary"] and "summary" in saved_paths:
        summary_path = Path(saved_paths["summary"])
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(observation, file, ensure_ascii=False, indent=2)
            file.write("\n")

    return {
        "bundle": bundle,
        "observation": observation,
    }


def build_sns_collector_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect one free SNS source and save normalized SNS signals.")
    parser.add_argument("--config", required=True, help="Path to a SNS collector JSON config file.")
    return parser


__all__ = [
    "REDDIT_SUBREDDIT_NEW_JSON_URL",
    "SNS_SOURCE_PROFILES",
    "SnsCollectorError",
    "build_sns_collector_parser",
    "fetch_reddit_listing",
    "load_sns_collector_config",
    "parse_reddit_listing_items",
    "run_sns_collector",
    "save_sns_collection_run",
]
