from __future__ import annotations

from bisect import bisect_left
from datetime import datetime

from trade_simulator.data import normalize_symbol
from trade_simulator.integrated_observer import scan_saved_signal_summaries


def _parse_iso_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty ISO 8601 string")

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from error


def _normalize_feature_symbol(symbol: object) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise TypeError("symbol must be a non-empty string")
    return normalize_symbol(symbol).upper()


def _normalize_topics(topics: object) -> list[str]:
    if topics is None:
        return []
    if not isinstance(topics, list):
        raise TypeError("topics must be a list")

    normalized_topics: list[str] = []
    for index, topic in enumerate(topics):
        if not isinstance(topic, str) or not topic.strip():
            raise TypeError(f"topics[{index}] must be a non-empty string")
        normalized = " ".join(topic.split()).lower()
        if normalized not in normalized_topics:
            normalized_topics.append(normalized)
    return normalized_topics


def _normalize_distribution(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not isinstance(count, int) or count <= 0:
            continue
        normalized[key] = count
    return normalized


def build_external_feature_timeline(
    return_timestamps: object,
    summaries: object,
    *,
    symbol: object,
    topics: object = None,
) -> dict:
    if not isinstance(return_timestamps, list):
        raise TypeError("return_timestamps must be a list")
    if not isinstance(summaries, list):
        raise TypeError("summaries must be a list")

    parsed_return_timestamps = [
        _parse_iso_timestamp(timestamp, field_name=f"return_timestamps[{index}]")
        for index, timestamp in enumerate(return_timestamps)
    ]
    normalized_symbol = _normalize_feature_symbol(symbol)
    normalized_topics = _normalize_topics(topics)

    symbol_signal_count = [0] * len(parsed_return_timestamps)
    topic_signal_count = [0] * len(parsed_return_timestamps)
    matching_run_count = [0] * len(parsed_return_timestamps)
    aligned_summary_count = 0
    ignored_summary_count = 0

    for index, summary in enumerate(summaries):
        if not isinstance(summary, dict):
            raise TypeError(f"summaries[{index}] must be a dict")
        if summary.get("status") != "completed":
            ignored_summary_count += 1
            continue

        event_timestamp = summary.get("ended_at") or summary.get("started_at")
        if event_timestamp is None:
            ignored_summary_count += 1
            continue

        try:
            event_time = _parse_iso_timestamp(event_timestamp, field_name=f"summaries[{index}].ended_at")
        except (TypeError, ValueError):
            ignored_summary_count += 1
            continue

        period_index = bisect_left(parsed_return_timestamps, event_time)
        if period_index >= len(parsed_return_timestamps):
            ignored_summary_count += 1
            continue

        symbol_distribution = _normalize_distribution(summary.get("symbol_distribution"))
        topic_distribution = _normalize_distribution(summary.get("topic_distribution"))
        matched_symbol_count = symbol_distribution.get(normalized_symbol, 0)
        matched_topic_count = sum(topic_distribution.get(topic, 0) for topic in normalized_topics)

        if matched_symbol_count <= 0 and matched_topic_count <= 0:
            ignored_summary_count += 1
            continue

        symbol_signal_count[period_index] += matched_symbol_count
        topic_signal_count[period_index] += matched_topic_count
        matching_run_count[period_index] += 1
        aligned_summary_count += 1

    matching_signal_count = [
        symbol_count + topic_count
        for symbol_count, topic_count in zip(symbol_signal_count, topic_signal_count)
    ]
    has_activity = [count > 0 for count in matching_signal_count]

    return {
        "return_timestamps": list(return_timestamps),
        "selected_symbol": normalized_symbol,
        "selected_topics": normalized_topics,
        "series": {
            "symbol_signal_count": symbol_signal_count,
            "topic_signal_count": topic_signal_count,
            "matching_signal_count": matching_signal_count,
            "matching_run_count": matching_run_count,
            "has_activity": has_activity,
        },
        "summary": {
            "aligned_summary_count": aligned_summary_count,
            "ignored_summary_count": ignored_summary_count,
        },
    }


def build_external_feature_signals(
    feature_timeline: object,
    *,
    entry_count_threshold: object = 1,
    exit_after_inactive_periods: object = 1,
) -> tuple[list[bool], list[bool]]:
    if not isinstance(feature_timeline, dict):
        raise TypeError("feature_timeline must be a dict")
    if not isinstance(entry_count_threshold, int) or entry_count_threshold <= 0:
        raise ValueError("entry_count_threshold must be a positive int")
    if not isinstance(exit_after_inactive_periods, int) or exit_after_inactive_periods <= 0:
        raise ValueError("exit_after_inactive_periods must be a positive int")

    series = feature_timeline.get("series")
    if not isinstance(series, dict):
        raise ValueError("feature_timeline must include a series dict")

    matching_signal_count = series.get("matching_signal_count")
    if not isinstance(matching_signal_count, list):
        raise ValueError("feature_timeline series must include matching_signal_count")

    entry_signals = [False] * len(matching_signal_count)
    exit_signals = [False] * len(matching_signal_count)
    is_in_position = False
    inactive_streak = 0

    for index, count in enumerate(matching_signal_count):
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"matching_signal_count[{index}] must be a non-negative int")

        is_active = count >= entry_count_threshold

        if not is_in_position and is_active:
            entry_signals[index] = True
            is_in_position = True
            inactive_streak = 0
            continue

        if not is_in_position:
            continue

        if is_active:
            inactive_streak = 0
            continue

        inactive_streak += 1
        if inactive_streak >= exit_after_inactive_periods:
            exit_signals[index] = True
            is_in_position = False
            inactive_streak = 0

    return entry_signals, exit_signals


def prepare_external_signal_manual_case(
    case: object,
    *,
    return_timestamps: object,
    symbol: object,
    summaries: object | None = None,
) -> dict:
    if not isinstance(case, dict):
        raise TypeError("case must be a dict")

    external_signal = case.get("external_signal")
    if not isinstance(external_signal, dict):
        raise ValueError("case external_signal must be a dict")

    existing_strategy = case.get("strategy")
    if existing_strategy not in (None, "manual"):
        raise ValueError("external_signal cases must use manual strategy or omit strategy")
    if "entry_signals" in case or "exit_signals" in case:
        raise ValueError("external_signal cases must not include entry_signals or exit_signals")

    if summaries is None:
        summaries = scan_saved_signal_summaries(external_signal.get("summary_root_dir", "var"))

    feature_timeline = build_external_feature_timeline(
        return_timestamps,
        summaries,
        symbol=symbol,
        topics=external_signal.get("topics"),
    )
    entry_signals, exit_signals = build_external_feature_signals(
        feature_timeline,
        entry_count_threshold=external_signal.get("entry_count_threshold", 1),
        exit_after_inactive_periods=external_signal.get("exit_after_inactive_periods", 1),
    )

    prepared_case = dict(case)
    prepared_case["strategy"] = "manual"
    prepared_case["entry_signals"] = entry_signals
    prepared_case["exit_signals"] = exit_signals
    prepared_case["external_signal_features"] = feature_timeline
    return prepared_case


__all__ = [
    "build_external_feature_signals",
    "build_external_feature_timeline",
    "prepare_external_signal_manual_case",
]
