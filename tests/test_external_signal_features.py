import pytest

from trade_simulator import simulation
from trade_simulator.external_signal_features import (
    DEFAULT_TIME_WEIGHT_PROFILE,
    DEFAULT_ADJUSTMENT_SCALAR,
    SOURCE_ADJUSTMENT_CONFIGS,
    SOURCE_BASE_TIME_WEIGHT_PROFILES,
    build_external_feature_signals,
    build_external_feature_timeline,
    prepare_external_signal_manual_case,
)


def test_build_external_feature_timeline_aligns_raw_and_weighted_matching_summaries_to_return_timestamps() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 2},
                "topic_distribution": {"policy": 1},
            },
            {
                "status": "completed",
                "ended_at": "2024-01-01T01:15:00Z",
                "signal_type": "news",
                "source": "sec_press_releases_rss",
                "symbol_distribution": {"ETHUSDT": 3},
                "topic_distribution": {"policy": 2},
            },
            {
                "status": "failed",
                "ended_at": "2024-01-01T01:30:00Z",
                "symbol_distribution": {"BTCUSDT": 5},
                "topic_distribution": {"policy": 5},
            },
            {
                "status": "completed",
                "ended_at": "2024-01-01T04:00:00Z",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            },
        ],
        symbol="BTC/USDT",
        topics=["policy"],
    )

    assert feature_timeline["selected_symbol"] == "BTCUSDT"
    assert feature_timeline["selected_topics"] == ["policy"]
    assert feature_timeline["series"]["symbol_signal_count"] == [2, 0, 0]
    assert feature_timeline["series"]["topic_signal_count"] == [1, 2, 0]
    assert feature_timeline["series"]["matching_signal_count"] == [3, 2, 0]
    assert feature_timeline["series"]["matching_run_count"] == [1, 1, 0]
    assert feature_timeline["series"]["weighted_symbol_signal_count"] == pytest.approx([2.0, 1.4, 0.8])
    assert feature_timeline["series"]["weighted_topic_signal_count"] == pytest.approx([1.0, 2.7, 1.8])
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([3.0, 4.1, 2.6])
    assert feature_timeline["series"]["weighted_matching_run_count"] == pytest.approx([1.0, 1.7, 1.1])
    assert feature_timeline["series"]["has_activity"] == [True, True, False]
    assert feature_timeline["series"]["has_weighted_activity"] == [True, True, True]
    assert feature_timeline["summary"] == {
        "aligned_summary_count": 2,
        "ignored_summary_count": 2,
    }
    assert feature_timeline["time_weight_profiles"]["default"] == list(DEFAULT_TIME_WEIGHT_PROFILE)
    assert feature_timeline["adjustments"]["default_scalar"] == DEFAULT_ADJUSTMENT_SCALAR


def test_build_external_feature_timeline_supports_delayed_peak_source_profile() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
            "2024-01-01T04:00:00Z",
            "2024-01-01T05:00:00Z",
            "2024-01-01T06:00:00Z",
        ],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "sns",
                "source": "youtube_channel_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == [1, 0, 0, 0, 0, 0]
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([0.1, 0.3, 0.8, 1.0, 0.8, 0.5])


def test_build_external_feature_timeline_sums_weighted_contributions_when_runs_overlap() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
            "2024-01-01T04:00:00Z",
        ],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            },
            {
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 2},
                "topic_distribution": {},
            },
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == [1, 2, 0, 0]
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.0, 2.7, 1.8, 1.0])
    assert feature_timeline["series"]["weighted_matching_run_count"] == pytest.approx([1.0, 1.7, 1.1, 0.6])


def test_build_external_feature_timeline_applies_run_adjustment_scalar_to_amplify_weighted_features() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "run_id": "run-news-1",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-news-1": {"attention_score": 1.0},
        },
    )

    assert feature_timeline["series"]["matching_signal_count"] == [1, 0, 0]
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.2, 0.84, 0.48])
    assert feature_timeline["adjustments"]["applied_runs"] == [
        {
            "run_id": "run-news-1",
            "source": "coindesk_rss",
            "signal_type": "news",
            "scalar": 1.2000000000000002,
        }
    ]


def test_build_external_feature_timeline_applies_run_adjustment_scalar_to_suppress_weighted_features() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "run_id": "run-youtube-1",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "sns",
                "source": "youtube_channel_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-youtube-1": {"attention_score": 0.0},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([0.06, 0.18, 0.48])


def test_build_external_feature_timeline_applies_independent_scalars_per_run_before_summing() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
            "2024-01-01T04:00:00Z",
        ],
        [
            {
                "run_id": "run-news-high",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            },
            {
                "run_id": "run-news-low",
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            },
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-news-high": {"attention_score": 1.0},
            "run-news-low": {"attention_score": 0.0},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.2, 1.64, 1.04, 0.56])


def test_build_external_feature_timeline_ignores_invalid_completed_summary_timestamp_boundary_case() -> None:
    feature_timeline = build_external_feature_timeline(
        ["2024-01-01T01:00:00Z"],
        [
            {
                "status": "completed",
                "ended_at": "not-a-timestamp",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == [0]
    assert feature_timeline["summary"] == {
        "aligned_summary_count": 0,
        "ignored_summary_count": 1,
    }


def test_build_external_feature_timeline_uses_safe_default_for_unknown_or_invalid_profiles(monkeypatch) -> None:
    monkeypatch.setitem(SOURCE_BASE_TIME_WEIGHT_PROFILES, "custom_empty_source", ())

    feature_timeline = build_external_feature_timeline(
        ["2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z"],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "source": "unknown_source",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            },
            {
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "source": "custom_empty_source",
                "symbol_distribution": {"BTCUSDT": 2},
                "topic_distribution": {},
            },
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == [1, 2]
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.0, 2.0])
    assert feature_timeline["series"]["weighted_matching_run_count"] == pytest.approx([1.0, 1.0])


def test_build_external_feature_timeline_keeps_stage_one_weighted_profile_when_adjustment_metrics_are_missing() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "run_id": "run-news-1",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.0, 0.7, 0.4])


def test_build_external_feature_timeline_clamps_adjustment_scalar_upper_bound() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
        ],
        [
            {
                "run_id": "run-youtube-max",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "sns",
                "source": "youtube_channel_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-youtube-max": {"attention_score": 99.0},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([0.2, 0.6])


def test_build_external_feature_timeline_clamps_adjustment_scalar_lower_bound(monkeypatch) -> None:
    monkeypatch.setitem(
        SOURCE_ADJUSTMENT_CONFIGS,
        "custom_low_source",
        {
            "metric_name": "attention_score",
            "base": 0.1,
            "alpha": 0.0,
            "min": 0.4,
            "max": 1.5,
        },
    )

    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
        ],
        [
            {
                "run_id": "run-custom-low",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "source": "custom_low_source",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-custom-low": {"attention_score": 0.0},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([0.4, 0.0])


def test_build_external_feature_timeline_falls_back_to_default_scalar_for_negative_metric() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "run_id": "run-news-negative",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-news-negative": {"attention_score": -1.0},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.0, 0.7, 0.4])


def test_build_external_feature_timeline_falls_back_to_default_scalar_for_invalid_metric_format() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "run_id": "run-news-invalid",
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
        run_metrics_by_run_id={
            "run-news-invalid": {"attention_score": "high"},
        },
    )

    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([1.0, 0.7, 0.4])


def test_build_external_feature_timeline_handles_empty_return_timestamps_boundary_case() -> None:
    feature_timeline = build_external_feature_timeline(
        [],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T00:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == []
    assert feature_timeline["series"]["weighted_matching_signal_count"] == []
    assert feature_timeline["summary"] == {
        "aligned_summary_count": 0,
        "ignored_summary_count": 1,
    }


def test_build_external_feature_timeline_never_applies_weight_before_first_available_period() -> None:
    feature_timeline = build_external_feature_timeline(
        [
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        [
            {
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "signal_type": "news",
                "source": "coindesk_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {},
            }
        ],
        symbol="BTC/USDT",
    )

    assert feature_timeline["series"]["matching_signal_count"] == [0, 1, 0]
    assert feature_timeline["series"]["weighted_matching_signal_count"] == pytest.approx([0.0, 1.0, 0.7])


def test_build_external_feature_signals_uses_weighted_activity_and_exits_after_quiet_periods() -> None:
    entry_signals, exit_signals = build_external_feature_signals(
        {
            "series": {
                "weighted_matching_signal_count": [0.0, 0.2, 0.8, 0.4, 0.0, 1.1, 0.0],
            }
        },
        entry_count_threshold=0.5,
        exit_after_inactive_periods=2,
    )

    assert entry_signals == [False, False, True, False, False, True, False]
    assert exit_signals == [False, False, False, False, True, False, False]


def test_prepare_external_signal_manual_case_uses_weighted_feature_series_for_manual_strategy() -> None:
    prepared_case = prepare_external_signal_manual_case(
        {
            "name": "external_signal_case",
            "simulation_name": "external_signal_case",
            "initial_cash": 1000,
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "returns": [0.01, 0.02, -0.01],
            "external_signal": {
                "topics": ["policy"],
                "entry_count_threshold": 0.5,
                "exit_after_inactive_periods": 1,
                "run_metrics_by_run_id": {
                    "run-youtube-1": {"attention_score": 1.0},
                },
            },
        },
        return_timestamps=[
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        symbol="BTC/USDT",
        summaries=[
            {
                "run_id": "run-youtube-1",
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "signal_type": "sns",
                "source": "youtube_channel_rss",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {"policy": 1},
            }
        ],
    )

    assert prepared_case["strategy"] == "manual"
    assert prepared_case["entry_signals"] == [False, False, True]
    assert prepared_case["exit_signals"] == [False, False, False]
    assert prepared_case["external_signal_features"]["series"]["matching_signal_count"] == [0, 2, 0]
    assert prepared_case["external_signal_features"]["series"]["weighted_matching_signal_count"] == pytest.approx([0.0, 0.28, 0.84])


def test_prepare_external_signal_manual_case_rejects_conflicting_non_manual_strategy() -> None:
    with pytest.raises(ValueError, match="external_signal cases must use manual strategy or omit strategy"):
        prepare_external_signal_manual_case(
            {
                "simulation_name": "invalid",
                "initial_cash": 1000,
                "returns": [0.01],
                "strategy": "threshold",
                "external_signal": {},
            },
            return_timestamps=["2024-01-01T01:00:00Z"],
            symbol="BTC/USDT",
            summaries=[],
        )


def test_prepare_external_signal_manual_case_keeps_simulate_boundary_outside_feature_layer() -> None:
    prepared_case = prepare_external_signal_manual_case(
        {
            "simulation_name": "boundary_check",
            "initial_cash": 1000,
            "returns": [0.01, 0.02, -0.01],
            "fee_rate": 0.0,
            "slippage_rate": 0.0,
            "external_signal": {},
        },
        return_timestamps=[
            "2024-01-01T01:00:00Z",
            "2024-01-01T02:00:00Z",
            "2024-01-01T03:00:00Z",
        ],
        symbol="BTC/USDT",
        summaries=[],
    )

    result = simulation.simulate(prepared_case)

    assert result["entry_signals"] == [False, False, False]
    assert result["exit_signals"] == [False, False, False]
