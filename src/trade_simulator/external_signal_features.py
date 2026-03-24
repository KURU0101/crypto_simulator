from __future__ import annotations

from bisect import bisect_left
from datetime import datetime
import math
from numbers import Real

from trade_simulator.data import normalize_symbol
from trade_simulator.integrated_observer import scan_saved_signal_summaries


DEFAULT_TIME_WEIGHT_PROFILE = (1.0,)

SIGNAL_TYPE_BASE_TIME_WEIGHT_PROFILES = {
    "news": (1.0, 0.7, 0.4, 0.2),
    "sns": (0.4, 1.0, 0.8, 0.4, 0.2),
}

SOURCE_BASE_TIME_WEIGHT_PROFILES = {
    "youtube_channel_rss": (0.1, 0.3, 0.8, 1.0, 0.8, 0.5, 0.2),
}

DEFAULT_ADJUSTMENT_SCALAR = 1.0

SIGNAL_TYPE_ADJUSTMENT_CONFIGS = {
    "news": {
        "metric_name": "attention_score",
        "base": 0.8,
        "alpha": 0.4,
        "min": 0.6,
        "max": 1.6,
    },
    "sns": {
        "metric_name": "attention_score",
        "base": 0.7,
        "alpha": 0.5,
        "min": 0.5,
        "max": 1.8,
    },
}

SOURCE_ADJUSTMENT_CONFIGS = {
    "youtube_channel_rss": {
        "metric_name": "attention_score",
        "base": 0.6,
        "alpha": 0.8,
        "min": 0.4,
        "max": 2.0,
    },
}

DEFAULT_FEATURE_OVERRIDE_CONFIG = {
    "time_weight_profiles": {
        "default": list(DEFAULT_TIME_WEIGHT_PROFILE),
        "signal_type": {
            key: list(value) for key, value in SIGNAL_TYPE_BASE_TIME_WEIGHT_PROFILES.items()
        },
        "source": {
            key: list(value) for key, value in SOURCE_BASE_TIME_WEIGHT_PROFILES.items()
        },
    },
    "adjustments": {
        "default_scalar": DEFAULT_ADJUSTMENT_SCALAR,
        "signal_type": {
            key: dict(value) for key, value in SIGNAL_TYPE_ADJUSTMENT_CONFIGS.items()
        },
        "source": {
            key: dict(value) for key, value in SOURCE_ADJUSTMENT_CONFIGS.items()
        },
    },
}


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


def _normalize_time_weight_profile(value: object) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        return DEFAULT_TIME_WEIGHT_PROFILE

    normalized_weights: list[float] = []
    for weight in value:
        if isinstance(weight, bool) or not isinstance(weight, Real):
            continue
        normalized_weight = float(weight)
        if normalized_weight <= 0:
            continue
        normalized_weights.append(normalized_weight)

    return tuple(normalized_weights) or DEFAULT_TIME_WEIGHT_PROFILE


def _read_finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None

    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def _build_feature_override_config(overrides: object = None) -> dict:
    config = {
        "time_weight_profiles": {
            "default": _normalize_time_weight_profile(DEFAULT_TIME_WEIGHT_PROFILE),
            "signal_type": {
                key: _normalize_time_weight_profile(value) for key, value in SIGNAL_TYPE_BASE_TIME_WEIGHT_PROFILES.items()
            },
            "source": {
                key: _normalize_time_weight_profile(value) for key, value in SOURCE_BASE_TIME_WEIGHT_PROFILES.items()
            },
        },
        "adjustments": {
            "default_scalar": DEFAULT_ADJUSTMENT_SCALAR,
            "signal_type": {
                key: dict(value) for key, value in SIGNAL_TYPE_ADJUSTMENT_CONFIGS.items()
            },
            "source": {
                key: dict(value) for key, value in SOURCE_ADJUSTMENT_CONFIGS.items()
            },
        },
    }
    if not isinstance(overrides, dict):
        return config

    profile_overrides = overrides.get("time_weight_profiles")
    if isinstance(profile_overrides, dict):
        default_profile = _normalize_time_weight_profile(profile_overrides.get("default"))
        if profile_overrides.get("default") is not None:
            config["time_weight_profiles"]["default"] = default_profile
        for scope_name in ("signal_type", "source"):
            scoped_overrides = profile_overrides.get(scope_name)
            if not isinstance(scoped_overrides, dict):
                continue
            for key, value in scoped_overrides.items():
                if not isinstance(key, str) or not key:
                    continue
                config["time_weight_profiles"][scope_name][key] = _normalize_time_weight_profile(value)

    adjustment_overrides = overrides.get("adjustments")
    if isinstance(adjustment_overrides, dict):
        default_scalar = _read_finite_number(adjustment_overrides.get("default_scalar"))
        if default_scalar is not None and default_scalar > 0:
            config["adjustments"]["default_scalar"] = float(default_scalar)
        for scope_name in ("signal_type", "source"):
            scoped_overrides = adjustment_overrides.get(scope_name)
            if not isinstance(scoped_overrides, dict):
                continue
            for key, value in scoped_overrides.items():
                if not isinstance(key, str) or not key or not isinstance(value, dict):
                    continue
                merged_config = dict(config["adjustments"][scope_name].get(key, {}))
                for field_name in ("metric_name", "base", "alpha", "min", "max"):
                    if field_name in value:
                        merged_config[field_name] = value[field_name]
                config["adjustments"][scope_name][key] = merged_config

    return config


def _serialize_feature_override_config(config: dict) -> dict:
    return {
        "time_weight_profiles": {
            "default": list(config["time_weight_profiles"]["default"]),
            "signal_type": {
                key: list(value) for key, value in config["time_weight_profiles"]["signal_type"].items()
            },
            "source": {
                key: list(value) for key, value in config["time_weight_profiles"]["source"].items()
            },
        },
        "adjustments": {
            "default_scalar": config["adjustments"]["default_scalar"],
            "signal_type": {
                key: dict(value) for key, value in config["adjustments"]["signal_type"].items()
            },
            "source": {
                key: dict(value) for key, value in config["adjustments"]["source"].items()
            },
        },
    }


def _resolve_base_time_weight_profile(summary: dict, resolved_config: dict) -> tuple[tuple[float, ...], str]:
    source = summary.get("source")
    source_profiles = resolved_config["time_weight_profiles"]["source"]
    if isinstance(source, str) and source in source_profiles:
        return tuple(source_profiles[source]), "source"

    signal_type = summary.get("signal_type")
    signal_type_profiles = resolved_config["time_weight_profiles"]["signal_type"]
    if isinstance(signal_type, str) and signal_type in signal_type_profiles:
        return tuple(signal_type_profiles[signal_type]), "signal_type"

    return tuple(resolved_config["time_weight_profiles"]["default"]), "default"


def _resolve_adjustment_config(summary: dict, resolved_config: dict) -> tuple[dict | None, str]:
    source = summary.get("source")
    source_configs = resolved_config["adjustments"]["source"]
    if isinstance(source, str) and source in source_configs:
        return dict(source_configs[source]), "source"

    signal_type = summary.get("signal_type")
    signal_type_configs = resolved_config["adjustments"]["signal_type"]
    if isinstance(signal_type, str) and signal_type in signal_type_configs:
        return dict(signal_type_configs[signal_type]), "signal_type"

    return None, "default"


def _resolve_run_metric(summary: dict, run_metrics_by_run_id: dict[str, dict], adjustment_config: dict | None) -> object:
    run_id = summary.get("run_id")
    if not isinstance(run_id, str) or run_id not in run_metrics_by_run_id:
        return None

    run_metrics = run_metrics_by_run_id[run_id]
    if not isinstance(run_metrics, dict):
        return None

    if not isinstance(adjustment_config, dict):
        return None

    metric_name = adjustment_config.get("metric_name")
    if not isinstance(metric_name, str) or not metric_name:
        return None
    return run_metrics.get(metric_name)


def _compute_run_adjustment_scalar(summary: dict, run_metrics_by_run_id: dict[str, dict], resolved_config: dict) -> tuple[float, str]:
    adjustment_config, resolution = _resolve_adjustment_config(summary, resolved_config)
    if not isinstance(adjustment_config, dict):
        return float(resolved_config["adjustments"]["default_scalar"]), resolution

    metric_value = _resolve_run_metric(summary, run_metrics_by_run_id, adjustment_config)
    normalized_metric = _read_finite_number(metric_value)
    if normalized_metric is None or normalized_metric < 0:
        return float(resolved_config["adjustments"]["default_scalar"]), resolution

    base = _read_finite_number(adjustment_config.get("base"))
    alpha = _read_finite_number(adjustment_config.get("alpha"))
    min_adjustment = _read_finite_number(adjustment_config.get("min"))
    max_adjustment = _read_finite_number(adjustment_config.get("max"))
    if None in (base, alpha, min_adjustment, max_adjustment):
        return float(resolved_config["adjustments"]["default_scalar"]), resolution
    if min_adjustment > max_adjustment:
        return float(resolved_config["adjustments"]["default_scalar"]), resolution

    scalar = base + alpha * normalized_metric
    return max(min_adjustment, min(max_adjustment, scalar)), resolution


def _apply_weighted_contribution(
    weighted_series: list[float],
    *,
    start_index: int,
    profile: tuple[float, ...],
    base_value: float,
) -> None:
    for offset, weight in enumerate(profile):
        target_index = start_index + offset
        if target_index >= len(weighted_series):
            break
        weighted_series[target_index] += base_value * weight


def build_external_feature_timeline(
    return_timestamps: object,
    summaries: object,
    *,
    symbol: object,
    topics: object = None,
    run_metrics_by_run_id: object = None,
    feature_overrides: object = None,
) -> dict:
    if not isinstance(return_timestamps, list):
        raise TypeError("return_timestamps must be a list")
    if not isinstance(summaries, list):
        raise TypeError("summaries must be a list")
    if run_metrics_by_run_id is None:
        resolved_run_metrics_by_run_id: dict[str, dict] = {}
    elif isinstance(run_metrics_by_run_id, dict):
        resolved_run_metrics_by_run_id = {
            run_id: metrics
            for run_id, metrics in run_metrics_by_run_id.items()
            if isinstance(run_id, str)
        }
    else:
        raise TypeError("run_metrics_by_run_id must be a dict")
    resolved_config = _build_feature_override_config(feature_overrides)

    parsed_return_timestamps = [
        _parse_iso_timestamp(timestamp, field_name=f"return_timestamps[{index}]")
        for index, timestamp in enumerate(return_timestamps)
    ]
    normalized_symbol = _normalize_feature_symbol(symbol)
    normalized_topics = _normalize_topics(topics)

    symbol_signal_count = [0] * len(parsed_return_timestamps)
    topic_signal_count = [0] * len(parsed_return_timestamps)
    matching_run_count = [0] * len(parsed_return_timestamps)
    weighted_symbol_signal_count = [0.0] * len(parsed_return_timestamps)
    weighted_topic_signal_count = [0.0] * len(parsed_return_timestamps)
    weighted_matching_run_count = [0.0] * len(parsed_return_timestamps)
    aligned_summary_count = 0
    ignored_summary_count = 0
    applied_adjustments = []

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

        profile, profile_resolution = _resolve_base_time_weight_profile(summary, resolved_config)
        adjustment_scalar, adjustment_resolution = _compute_run_adjustment_scalar(
            summary,
            resolved_run_metrics_by_run_id,
            resolved_config,
        )
        adjusted_profile = tuple(weight * adjustment_scalar for weight in profile)
        period_contributions = []
        for offset, adjusted_weight in enumerate(adjusted_profile):
            target_index = period_index + offset
            if target_index >= len(parsed_return_timestamps):
                break
            period_contributions.append(
                {
                    "period_index": target_index,
                    "timestamp": return_timestamps[target_index],
                    "weighted_symbol_signal_count": float(matched_symbol_count) * adjusted_weight,
                    "weighted_topic_signal_count": float(matched_topic_count) * adjusted_weight,
                    "weighted_matching_signal_count": float(matched_symbol_count + matched_topic_count) * adjusted_weight,
                    "weighted_matching_run_count": adjusted_weight,
                }
            )
        symbol_signal_count[period_index] += matched_symbol_count
        topic_signal_count[period_index] += matched_topic_count
        matching_run_count[period_index] += 1
        _apply_weighted_contribution(
            weighted_symbol_signal_count,
            start_index=period_index,
            profile=adjusted_profile,
            base_value=float(matched_symbol_count),
        )
        _apply_weighted_contribution(
            weighted_topic_signal_count,
            start_index=period_index,
            profile=adjusted_profile,
            base_value=float(matched_topic_count),
        )
        _apply_weighted_contribution(
            weighted_matching_run_count,
            start_index=period_index,
            profile=adjusted_profile,
            base_value=1.0,
        )
        applied_adjustments.append(
            {
                "run_id": summary.get("run_id"),
                "source": summary.get("source"),
                "signal_type": summary.get("signal_type"),
                "base_profile": list(profile),
                "scalar": adjustment_scalar,
                "adjusted_profile": list(adjusted_profile),
                "profile_resolution": profile_resolution,
                "scalar_resolution": adjustment_resolution,
                "contribution_start_index": period_index,
                "contribution_start_timestamp": return_timestamps[period_index],
                "raw_contribution": {
                    "symbol_signal_count": matched_symbol_count,
                    "topic_signal_count": matched_topic_count,
                    "matching_signal_count": matched_symbol_count + matched_topic_count,
                    "matching_run_count": 1,
                },
                "period_contributions": period_contributions,
            }
        )
        aligned_summary_count += 1

    matching_signal_count = [
        symbol_count + topic_count
        for symbol_count, topic_count in zip(symbol_signal_count, topic_signal_count)
    ]
    weighted_matching_signal_count = [
        symbol_count + topic_count
        for symbol_count, topic_count in zip(weighted_symbol_signal_count, weighted_topic_signal_count)
    ]
    has_activity = [count > 0 for count in matching_signal_count]
    has_weighted_activity = [count > 0.0 for count in weighted_matching_signal_count]

    return {
        "return_timestamps": list(return_timestamps),
        "selected_symbol": normalized_symbol,
        "selected_topics": normalized_topics,
        "time_weight_profiles": _serialize_feature_override_config(resolved_config)["time_weight_profiles"],
        "adjustments": {
            **_serialize_feature_override_config(resolved_config)["adjustments"],
            "applied_runs": applied_adjustments,
        },
        "series": {
            "symbol_signal_count": symbol_signal_count,
            "topic_signal_count": topic_signal_count,
            "matching_signal_count": matching_signal_count,
            "matching_run_count": matching_run_count,
            "weighted_symbol_signal_count": weighted_symbol_signal_count,
            "weighted_topic_signal_count": weighted_topic_signal_count,
            "weighted_matching_signal_count": weighted_matching_signal_count,
            "weighted_matching_run_count": weighted_matching_run_count,
            "has_activity": has_activity,
            "has_weighted_activity": has_weighted_activity,
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
    if isinstance(entry_count_threshold, bool) or not isinstance(entry_count_threshold, Real) or entry_count_threshold <= 0:
        raise ValueError("entry_count_threshold must be a positive number")
    if not isinstance(exit_after_inactive_periods, int) or exit_after_inactive_periods <= 0:
        raise ValueError("exit_after_inactive_periods must be a positive int")

    series = feature_timeline.get("series")
    if not isinstance(series, dict):
        raise ValueError("feature_timeline must include a series dict")

    matching_signal_count = series.get("weighted_matching_signal_count")
    if not isinstance(matching_signal_count, list):
        raise ValueError("feature_timeline series must include weighted_matching_signal_count")

    entry_signals = [False] * len(matching_signal_count)
    exit_signals = [False] * len(matching_signal_count)
    is_in_position = False
    inactive_streak = 0

    for index, count in enumerate(matching_signal_count):
        if isinstance(count, bool) or not isinstance(count, Real) or count < 0:
            raise ValueError(f"weighted_matching_signal_count[{index}] must be a non-negative number")

        is_active = float(count) >= float(entry_count_threshold)

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
        run_metrics_by_run_id=external_signal.get("run_metrics_by_run_id"),
        feature_overrides=external_signal.get("feature_overrides"),
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
