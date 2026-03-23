from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


SUMMARY_ROOTS = {
    "news": "news_signals",
    "sns": "sns_signals",
}

REQUIRED_SUMMARY_FIELDS = (
    "signal_type",
    "source",
    "run_id",
    "started_at",
    "ended_at",
    "status",
)

COUNT_FIELDS = (
    "fetched_item_count",
    "normalized_success_count",
    "validation_failure_count",
    "saved_record_count",
    "duplicate_count",
)

COMMON_DISTRIBUTION_FIELDS = (
    "topic_distribution",
    "symbol_distribution",
)

# Legacy summaries may still expose source-specific fields at the top level for
# compatibility. The integrated observer intentionally does not depend on them.
LEGACY_SOURCE_SPECIFIC_TOP_LEVEL_FIELDS = (
    "feed_url",
    "listing_url",
    "configured_group_count",
    "configured_channel_count",
    "successful_channel_count",
    "failed_channel_count",
    "empty_channel_count",
    "story_list",
    "list_url",
    "item_url_template",
)


def scan_saved_signal_summaries(root_dir: str | Path = "var") -> list[dict]:
    """Read saved external-signal run summaries using only the common schema."""
    root_path = Path(root_dir)
    entries: list[dict] = []

    for signal_type, relative_root in SUMMARY_ROOTS.items():
        signal_root = root_path / relative_root
        if not signal_root.exists():
            continue
        if not signal_root.is_dir():
            raise ValueError(f"summary root must be a directory: {signal_root}")

        for source_dir in sorted((path for path in signal_root.iterdir() if path.is_dir()), key=lambda path: path.name):
            run_dirs = sorted((path for path in source_dir.iterdir() if path.is_dir()), key=lambda path: path.name)
            for run_dir in run_dirs:
                entries.append(_read_summary_entry(run_dir=run_dir, signal_type=signal_type, source=source_dir.name))

    return _sort_entries(entries)


def build_integrated_summary_report(
    entries: Iterable[dict],
    *,
    signal_type: str = "all",
    source: str | None = None,
    latest_only: bool = False,
    group_by: str = "overall",
) -> dict:
    filtered_entries = _filter_entries(entries, signal_type=signal_type, source=source, latest_only=latest_only)
    groups = _group_entries(filtered_entries, group_by=group_by)

    return {
        "filters": {
            "signal_type": signal_type,
            "source": source,
            "latest_only": latest_only,
            "group_by": group_by,
        },
        "totals": _compute_totals(filtered_entries),
        "groups": [
            {
                "key": group_key,
                "totals": _compute_totals(group_entries),
                "runs": group_entries,
            }
            for group_key, group_entries in groups
        ],
        "runs": filtered_entries,
    }


def _read_summary_entry(*, run_dir: Path, signal_type: str, source: str) -> dict:
    summary_path = run_dir / "summary.json"
    base_entry = _base_entry(signal_type=signal_type, source=source, run_dir=run_dir)

    if not summary_path.exists():
        entry = dict(base_entry)
        entry["status"] = "missing_summary"
        entry["errors"] = [{"message": "summary.json is missing"}]
        entry["error_count"] = len(entry["errors"])
        return entry

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        entry = dict(base_entry)
        entry["status"] = "invalid_summary"
        entry["errors"] = [{"message": f"summary.json is not valid JSON: {error.msg}"}]
        entry["saved_paths"] = {"summary": str(summary_path)}
        entry["error_count"] = len(entry["errors"])
        return entry

    if not isinstance(payload, dict):
        entry = dict(base_entry)
        entry["status"] = "invalid_summary"
        entry["errors"] = [{"message": "summary.json must contain a JSON object"}]
        entry["saved_paths"] = {"summary": str(summary_path)}
        entry["error_count"] = len(entry["errors"])
        return entry

    entry = dict(base_entry)
    _apply_common_summary_fields(
        entry,
        payload=payload,
        summary_path=summary_path,
        default_signal_type=signal_type,
        default_source=source,
        default_run_id=run_dir.name,
    )
    return entry


def _base_entry(*, signal_type: str, source: str, run_dir: Path) -> dict:
    return {
        "signal_type": signal_type,
        "source": source,
        "run_id": run_dir.name,
        "status": "unknown",
        "started_at": None,
        "ended_at": None,
        "fetched_item_count": 0,
        "normalized_success_count": 0,
        "validation_failure_count": 0,
        "saved_record_count": 0,
        "duplicate_count": 0,
        "warnings": [],
        "errors": [],
        "saved_paths": {"summary": str(run_dir / "summary.json")},
        "source_specific": {},
        "has_source_specific": False,
        "warning_count": 0,
        "error_count": 0,
        "topic_distribution": {},
        "symbol_distribution": {},
        "topic_distribution_overview": "none",
        "symbol_distribution_overview": "none",
        "missing_required_fields": [],
        "run_directory": str(run_dir),
    }


def _apply_common_summary_fields(
    entry: dict,
    *,
    payload: dict,
    summary_path: Path,
    default_signal_type: str,
    default_source: str,
    default_run_id: str,
) -> None:
    """Populate one observer entry from summary fields that are shared across sources."""
    entry["run_id"] = _read_string(payload.get("run_id")) or default_run_id
    entry["signal_type"] = _read_string(payload.get("signal_type")) or default_signal_type
    entry["source"] = _read_string(payload.get("source")) or default_source
    entry["status"] = _read_string(payload.get("status")) or "invalid_summary"
    entry["started_at"] = _read_string(payload.get("started_at"))
    entry["ended_at"] = _read_string(payload.get("ended_at"))
    for field_name in COUNT_FIELDS:
        entry[field_name] = _read_non_negative_int(payload.get(field_name))
    entry["warnings"] = _normalize_messages(payload.get("warnings"))
    entry["errors"] = _normalize_errors(payload.get("errors"))
    entry["saved_paths"] = _normalize_saved_paths(payload.get("saved_paths"), summary_path=summary_path)
    entry["source_specific"] = _normalize_source_specific(payload)
    entry["missing_required_fields"] = _missing_required_fields(entry)
    entry["has_source_specific"] = bool(entry["source_specific"])
    entry["warning_count"] = len(entry["warnings"])
    entry["error_count"] = len(entry["errors"])
    for field_name in COMMON_DISTRIBUTION_FIELDS:
        entry[field_name] = _normalize_distribution(payload.get(field_name))
    entry["topic_distribution_overview"] = _distribution_overview(entry["topic_distribution"])
    entry["symbol_distribution_overview"] = _distribution_overview(entry["symbol_distribution"])


def _filter_entries(
    entries: Iterable[dict],
    *,
    signal_type: str,
    source: str | None,
    latest_only: bool,
) -> list[dict]:
    filtered = [
        dict(entry)
        for entry in entries
        if (signal_type == "all" or entry["signal_type"] == signal_type)
        and (source is None or entry["source"] == source)
    ]
    if latest_only:
        filtered = _latest_entries(filtered)
    return _sort_entries(filtered)


def _latest_entries(entries: Iterable[dict]) -> list[dict]:
    latest_by_key: dict[tuple[str, str], dict] = {}
    for entry in entries:
        key = (entry["signal_type"], entry["source"])
        current = latest_by_key.get(key)
        if current is None or _entry_sort_key(entry) > _entry_sort_key(current):
            latest_by_key[key] = dict(entry)
    return list(latest_by_key.values())


def _group_entries(entries: list[dict], *, group_by: str) -> list[tuple[str, list[dict]]]:
    if group_by == "overall":
        return [("all", entries)]

    groups: dict[str, list[dict]] = {}
    for entry in entries:
        if group_by == "signal_type":
            group_key = entry["signal_type"]
        elif group_by == "source":
            group_key = f"{entry['signal_type']}:{entry['source']}"
        else:
            raise ValueError(f"unsupported group_by: {group_by}")
        groups.setdefault(group_key, []).append(entry)

    return [(group_key, _sort_entries(group_entries)) for group_key, group_entries in sorted(groups.items())]


def _compute_totals(entries: Iterable[dict]) -> dict:
    items = list(entries)
    totals = {
        "run_count": len(items),
        "completed_count": 0,
        "failed_count": 0,
        "warning_run_count": 0,
        "error_run_count": 0,
        "invalid_run_count": 0,
        "source_specific_run_count": 0,
        "signal_types": {},
        "sources": {},
        "status_distribution": {},
        "latest_started_at": None,
        "latest_ended_at": None,
    }
    for field_name in COUNT_FIELDS:
        totals[field_name] = 0

    topic_distribution: dict[str, int] = {}
    symbol_distribution: dict[str, int] = {}

    for entry in items:
        status = entry["status"]
        totals["status_distribution"][status] = totals["status_distribution"].get(status, 0) + 1
        totals["signal_types"][entry["signal_type"]] = totals["signal_types"].get(entry["signal_type"], 0) + 1
        totals["sources"][entry["source"]] = totals["sources"].get(entry["source"], 0) + 1
        if status == "completed":
            totals["completed_count"] += 1
        elif status == "failed":
            totals["failed_count"] += 1
        else:
            totals["invalid_run_count"] += 1
        if entry["warning_count"] > 0:
            totals["warning_run_count"] += 1
        if entry["error_count"] > 0:
            totals["error_run_count"] += 1
        if entry["has_source_specific"]:
            totals["source_specific_run_count"] += 1
        for field_name in COUNT_FIELDS:
            totals[field_name] += entry[field_name]
        if entry["started_at"] and (totals["latest_started_at"] is None or entry["started_at"] > totals["latest_started_at"]):
            totals["latest_started_at"] = entry["started_at"]
        if entry["ended_at"] and (totals["latest_ended_at"] is None or entry["ended_at"] > totals["latest_ended_at"]):
            totals["latest_ended_at"] = entry["ended_at"]
        _merge_distribution(topic_distribution, entry["topic_distribution"])
        _merge_distribution(symbol_distribution, entry["symbol_distribution"])

    totals["topic_distribution"] = topic_distribution
    totals["symbol_distribution"] = symbol_distribution
    totals["topic_distribution_overview"] = _distribution_overview(topic_distribution)
    totals["symbol_distribution_overview"] = _distribution_overview(symbol_distribution)
    return totals


def _merge_distribution(target: dict[str, int], source: dict[str, int]) -> None:
    for key, count in source.items():
        target[key] = target.get(key, 0) + count


def _distribution_overview(distribution: dict[str, int], *, limit: int = 5) -> str:
    if not distribution:
        return "none"
    ordered_items = sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
    top_items = [f"{key}:{count}" for key, count in ordered_items[:limit]]
    remainder = len(ordered_items) - limit
    if remainder > 0:
        top_items.append(f"+{remainder} more")
    return ", ".join(top_items)


def _normalize_distribution(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, raw_count in value.items():
        key_string = _read_string(key)
        if key_string is None:
            continue
        count = _read_non_negative_int(raw_count)
        normalized[key_string] = count
    return normalized


def _normalize_mapping(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _normalize_source_specific(payload: dict) -> dict:
    normalized = _normalize_mapping(payload.get("source_specific"))
    if normalized:
        return normalized

    # Compatibility note: old summaries may still duplicate source-specific
    # fields at the top level. The integrated observer intentionally ignores
    # them so that new source additions do not create hidden dependencies.
    return {}


def _normalize_saved_paths(value: object, *, summary_path: Path) -> dict[str, str]:
    normalized: dict[str, str] = {"summary": str(summary_path)}
    if not isinstance(value, dict):
        return normalized
    for key, raw_path in value.items():
        key_string = _read_string(key)
        path_string = _read_string(raw_path)
        if key_string is None or path_string is None:
            continue
        normalized[key_string] = path_string
    return normalized


def _normalize_messages(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    messages: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            messages.append(item.strip())
    return messages


def _normalize_errors(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    errors: list[dict] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                errors.append({"message": stripped})
            continue
        if not isinstance(item, dict):
            continue
        error = dict(item)
        message = _read_string(error.get("message"))
        if message is not None:
            error["message"] = message
        errors.append(error)
    return errors


def _missing_required_fields(entry: dict) -> list[str]:
    return [field_name for field_name in REQUIRED_SUMMARY_FIELDS if not entry.get(field_name)]


def _read_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _read_non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _entry_sort_key(entry: dict) -> tuple[str, str, str, str]:
    started_at = entry["started_at"] or ""
    ended_at = entry["ended_at"] or ""
    return (started_at, ended_at, entry["run_id"], entry["source"])


def _sort_entries(entries: Iterable[dict]) -> list[dict]:
    return sorted(
        (dict(entry) for entry in entries),
        key=lambda entry: (entry["signal_type"], entry["source"], _entry_sort_key(entry)),
        reverse=True,
    )


__all__ = [
    "COMMON_DISTRIBUTION_FIELDS",
    "COUNT_FIELDS",
    "LEGACY_SOURCE_SPECIFIC_TOP_LEVEL_FIELDS",
    "REQUIRED_SUMMARY_FIELDS",
    "SUMMARY_ROOTS",
    "build_integrated_summary_report",
    "scan_saved_signal_summaries",
]
