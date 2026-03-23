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

from trade_simulator.sns_adapters import (
    REDDIT_SUBREDDIT_NEW_JSON_URL,
    SNS_SOURCE_PROFILES,
    build_youtube_channel_feed_url,
    parse_youtube_feed_items,
)
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


def _validate_string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a list")
    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(_validate_non_empty_string(item, f"{name}[{index}]"))
    return normalized


def fetch_sns_text(
    url: str,
    *,
    timeout_seconds: int,
    urlopen_fn: Callable[..., object] | None = None,
) -> str:
    if urlopen_fn is None:
        urlopen_fn = urllib.request.urlopen

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "trade-simulator-sns-collector/0.2"},
        method="GET",
    )

    try:
        with urlopen_fn(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        detail = f": {body}" if body else ""
        raise SnsCollectorError(f"failed to fetch SNS source: HTTP {error.code}{detail}") from error
    except urllib.error.URLError as error:
        raise SnsCollectorError(f"failed to fetch SNS source: {error.reason}") from error
    except TimeoutError as error:
        raise SnsCollectorError("failed to fetch SNS source: timeout") from error

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


def _validate_youtube_channel(channel: object, *, group_name: str, index: int, group_defaults: dict) -> dict:
    if not isinstance(channel, dict):
        raise TypeError(f"{group_name}.channels[{index}] must be a dict")
    normalized = dict(channel)
    normalized["channel_id"] = _validate_non_empty_string(normalized.get("channel_id"), f"{group_name}.channels[{index}].channel_id")
    normalized["channel_label"] = _validate_non_empty_string(
        normalized.get("channel_label"),
        f"{group_name}.channels[{index}].channel_label",
    )
    normalized["publisher_type"] = _validate_non_empty_string(
        normalized.get("publisher_type", group_defaults["publisher_type"]),
        f"{group_name}.channels[{index}].publisher_type",
    )
    normalized["theme_tags"] = _validate_string_list(
        normalized.get("theme_tags", [group_defaults["group_theme"]]),
        f"{group_name}.channels[{index}].theme_tags",
    )
    normalized["enabled"] = bool(normalized.get("enabled", True))
    normalized["feed_url"] = build_youtube_channel_feed_url(normalized["channel_id"])
    return normalized


def _validate_youtube_group(group: object, *, index: int) -> dict:
    if not isinstance(group, dict):
        raise TypeError(f"collector.groups[{index}] must be a dict")
    normalized = dict(group)
    group_name = f"collector.groups[{index}]"
    normalized["group_id"] = _validate_non_empty_string(normalized.get("group_id"), f"{group_name}.group_id")
    normalized["group_label"] = _validate_non_empty_string(normalized.get("group_label"), f"{group_name}.group_label")
    normalized["group_theme"] = _validate_non_empty_string(normalized.get("group_theme"), f"{group_name}.group_theme")
    normalized["publisher_type"] = _validate_non_empty_string(normalized.get("publisher_type"), f"{group_name}.publisher_type")
    channels = normalized.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError(f"{group_name}.channels must be a non-empty list")
    normalized["channels"] = [
        _validate_youtube_channel(channel, group_name=group_name, index=channel_index, group_defaults=normalized)
        for channel_index, channel in enumerate(channels)
    ]
    return normalized


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
    collector["timeout_seconds"] = _validate_positive_int(collector.get("timeout_seconds", 30), "collector.timeout_seconds")
    default_max_items = 50 if profile["kind"] == "reddit" else 20
    collector["max_items"] = _validate_positive_int(collector.get("max_items", default_max_items), "collector.max_items")

    if profile["kind"] == "reddit":
        collector["listing_url"] = _validate_non_empty_string(
            collector.get("listing_url", profile["default_listing_url"]),
            "collector.listing_url",
        )
    elif profile["kind"] == "youtube":
        groups = collector.get("groups")
        if not isinstance(groups, list) or not groups:
            raise ValueError("collector.groups must be a non-empty list")
        collector["groups"] = [_validate_youtube_group(group, index=index) for index, group in enumerate(groups)]
    else:
        raise ValueError(f"unsupported sns collector kind: {profile['kind']}")

    output["output_dir"] = _validate_non_empty_string(output.get("output_dir"), "output.output_dir")
    output["save_run_summary"] = bool(output.get("save_run_summary", True))

    return {
        "collector": collector,
        "output": output,
    }


def _empty_observation(*, source: str, started_at: str, listing_url: str | None = None) -> dict:
    observation = {
        "run_id": _run_id_from_iso8601(started_at),
        "status": "completed",
        "signal_type": "sns",
        "source": source,
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
        "group_distribution": {},
        "group_theme_distribution": {},
        "publisher_type_distribution": {},
        "channel_distribution": {},
        "symbol_distribution": {},
        "topic_distribution": {},
        "mention_count_summary": {"min": None, "max": None, "average": None, "total": 0},
        "timestamp_by_date": {},
        "timestamp_by_hour_utc": {},
        "warnings": [],
        "errors": [],
        "saved_paths": {},
    }
    if listing_url is not None:
        observation["listing_url"] = listing_url
    return observation


def _build_observation(
    *,
    source: str,
    started_at: str,
    ended_at: str,
    fetched_item_count: int,
    normalized_records: list[dict],
    normalized_failures: list[dict],
    missing_field_counts: dict[str, int],
    saved_paths: dict[str, str],
    warnings: list[str],
    source_context: dict | None = None,
) -> dict:
    source_distribution: dict[str, int] = {}
    group_distribution: dict[str, int] = {}
    group_theme_distribution: dict[str, int] = {}
    publisher_type_distribution: dict[str, int] = {}
    channel_distribution: dict[str, int] = {}
    symbol_distribution: dict[str, int] = {}
    topic_distribution: dict[str, int] = {}
    timestamp_by_date: dict[str, int] = {}
    timestamp_by_hour_utc: dict[str, int] = {}
    mention_counts: list[int] = []
    unique_dedup_keys: set[str] = set()

    for record in normalized_records:
        source_distribution[record["source"]] = source_distribution.get(record["source"], 0) + 1
        metadata = record.get("metadata", {})
        if metadata.get("group_id"):
            group_distribution[metadata["group_id"]] = group_distribution.get(metadata["group_id"], 0) + 1
        if metadata.get("group_theme"):
            group_theme_distribution[metadata["group_theme"]] = group_theme_distribution.get(metadata["group_theme"], 0) + 1
        if metadata.get("publisher_type"):
            publisher_type_distribution[metadata["publisher_type"]] = (
                publisher_type_distribution.get(metadata["publisher_type"], 0) + 1
            )
        if metadata.get("channel_id"):
            channel_key = f"{metadata['channel_label']} ({metadata['channel_id']})"
            channel_distribution[channel_key] = channel_distribution.get(channel_key, 0) + 1
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

    observation = {
        "run_id": _run_id_from_iso8601(started_at),
        "status": "completed",
        "signal_type": "sns",
        "source": source,
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
        "group_distribution": group_distribution,
        "group_theme_distribution": group_theme_distribution,
        "publisher_type_distribution": publisher_type_distribution,
        "channel_distribution": channel_distribution,
        "symbol_distribution": symbol_distribution,
        "topic_distribution": topic_distribution,
        "mention_count_summary": mention_count_summary,
        "timestamp_by_date": timestamp_by_date,
        "timestamp_by_hour_utc": timestamp_by_hour_utc,
        "warnings": warnings,
        "errors": normalized_failures,
        "saved_paths": saved_paths,
    }
    if source_context:
        observation.update(source_context)
    return observation


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


def _run_reddit_sns_collector(
    collector: dict,
    output: dict,
    profile: dict,
    *,
    fetch_text_fn: Callable[..., str],
    now_fn: Callable[[], float],
) -> dict:
    started_at = _utc_now_iso(now_fn)
    empty_observation = _empty_observation(
        source=collector["source"],
        listing_url=collector["listing_url"],
        started_at=started_at,
    )

    try:
        listing_text = fetch_text_fn(
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
        return {"bundle": build_sns_signal_bundle([]), "observation": observation}

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
            normalized_records.append(profile["adapter"](item, fetched_at=started_at, listing_url=collector["listing_url"]))
        except Exception as error:
            normalized_failures.append({"item_index": index, "title": item.get("title"), "message": str(error)})

    warnings: list[str] = []
    if not items:
        warnings.append("SNS listing returned no items")

    bundle = build_sns_signal_bundle(normalized_records)
    source_context = {"listing_url": collector["listing_url"]}
    provisional_observation = _build_observation(
        source=collector["source"],
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=len(items),
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths={},
        warnings=warnings,
        source_context=source_context,
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
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=len(items),
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths=saved_paths,
        warnings=warnings,
        source_context=source_context,
    )
    if output["save_run_summary"] and "summary" in saved_paths:
        summary_path = Path(saved_paths["summary"])
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(observation, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return {"bundle": bundle, "observation": observation}


def _run_youtube_sns_collector(
    collector: dict,
    output: dict,
    profile: dict,
    *,
    fetch_text_fn: Callable[..., str],
    now_fn: Callable[[], float],
) -> dict:
    started_at = _utc_now_iso(now_fn)
    configured_channels = [
        {
            "group_id": group["group_id"],
            "group_label": group["group_label"],
            "group_theme": group["group_theme"],
            "group_publisher_type": group["publisher_type"],
            **channel,
        }
        for group in collector["groups"]
        for channel in group["channels"]
        if channel["enabled"]
    ]
    source_context = {
        "configured_group_count": len(collector["groups"]),
        "configured_channel_count": len(configured_channels),
    }
    empty_observation = _empty_observation(source=collector["source"], started_at=started_at)
    empty_observation.update(source_context)

    tracked_fields = profile["required_item_fields"] + profile["tracked_optional_item_fields"]
    missing_field_counts = {field_name: 0 for field_name in tracked_fields}
    normalized_records: list[dict] = []
    normalized_failures: list[dict] = []
    warnings: list[str] = []
    fetched_item_count = 0
    successful_channel_count = 0
    failed_channel_count = 0
    empty_channel_count = 0

    for channel in configured_channels:
        try:
            feed_text = fetch_text_fn(channel["feed_url"], timeout_seconds=collector["timeout_seconds"])
            items = parse_youtube_feed_items(feed_text, max_items=collector["max_items"])
            successful_channel_count += 1
        except Exception as error:
            failed_channel_count += 1
            normalized_failures.append(
                {
                    "channel_id": channel["channel_id"],
                    "channel_label": channel["channel_label"],
                    "group_id": channel["group_id"],
                    "message": str(error),
                }
            )
            continue

        if not items:
            empty_channel_count += 1
            warnings.append(f"youtube channel returned no items: {channel['channel_label']} ({channel['channel_id']})")

        fetched_item_count += len(items)
        for index, item in enumerate(items):
            for field_name in tracked_fields:
                value = item.get(field_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing_field_counts[field_name] += 1
            try:
                normalized_records.append(profile["adapter"](item, fetched_at=started_at, channel_context=channel))
            except Exception as error:
                normalized_failures.append(
                    {
                        "channel_id": channel["channel_id"],
                        "channel_label": channel["channel_label"],
                        "group_id": channel["group_id"],
                        "item_index": index,
                        "title": item.get("title"),
                        "message": str(error),
                    }
                )

    source_context.update(
        {
            "successful_channel_count": successful_channel_count,
            "failed_channel_count": failed_channel_count,
            "empty_channel_count": empty_channel_count,
        }
    )

    if failed_channel_count:
        warnings.append(f"youtube channel fetch failures: {failed_channel_count}")
    if not normalized_records and failed_channel_count == len(configured_channels):
        ended_at = _utc_now_iso(now_fn)
        observation = dict(empty_observation)
        observation.update(source_context)
        observation["status"] = "failed"
        observation["ended_at"] = ended_at
        observation["duration_seconds"] = (
            datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            - datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        ).total_seconds()
        observation["warnings"] = warnings
        observation["errors"] = normalized_failures
        return {"bundle": build_sns_signal_bundle([]), "observation": observation}

    bundle = build_sns_signal_bundle(normalized_records)
    provisional_observation = _build_observation(
        source=collector["source"],
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=fetched_item_count,
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths={},
        warnings=warnings,
        source_context=source_context,
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
        started_at=started_at,
        ended_at=_utc_now_iso(now_fn),
        fetched_item_count=fetched_item_count,
        normalized_records=normalized_records,
        normalized_failures=normalized_failures,
        missing_field_counts=missing_field_counts,
        saved_paths=saved_paths,
        warnings=warnings,
        source_context=source_context,
    )
    if output["save_run_summary"] and "summary" in saved_paths:
        summary_path = Path(saved_paths["summary"])
        with summary_path.open("w", encoding="utf-8") as file:
            json.dump(observation, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return {"bundle": bundle, "observation": observation}


def run_sns_collector(
    config: dict,
    *,
    fetch_text_fn: Callable[..., str] | None = None,
    fetch_listing_fn: Callable[..., str] | None = None,
    now_fn: Callable[[], float] | None = None,
) -> dict:
    validated = load_sns_collector_config(config)
    collector = validated["collector"]
    output = validated["output"]
    profile = SNS_SOURCE_PROFILES[collector["source"]]

    if fetch_text_fn is None:
        fetch_text_fn = fetch_sns_text
    if fetch_listing_fn is not None:
        fetch_text_fn = fetch_listing_fn
    if now_fn is None:
        now_fn = time.time

    if profile["kind"] == "reddit":
        return _run_reddit_sns_collector(
            collector,
            output,
            profile,
            fetch_text_fn=fetch_text_fn,
            now_fn=now_fn,
        )
    if profile["kind"] == "youtube":
        return _run_youtube_sns_collector(
            collector,
            output,
            profile,
            fetch_text_fn=fetch_text_fn,
            now_fn=now_fn,
        )
    raise ValueError(f"unsupported sns collector kind: {profile['kind']}")


def build_sns_collector_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect one free SNS source and save normalized SNS signals.")
    parser.add_argument("--config", required=True, help="Path to a SNS collector JSON config file.")
    return parser


__all__ = [
    "REDDIT_SUBREDDIT_NEW_JSON_URL",
    "SNS_SOURCE_PROFILES",
    "SnsCollectorError",
    "build_sns_collector_parser",
    "fetch_sns_text",
    "load_sns_collector_config",
    "parse_reddit_listing_items",
    "run_sns_collector",
    "save_sns_collection_run",
]
