import pytest

from trade_simulator.external_signal_features import (
    build_external_feature_signals,
    build_external_feature_timeline,
    prepare_external_signal_manual_case,
)


def test_build_external_feature_timeline_aligns_matching_summaries_to_return_timestamps() -> None:
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
                "symbol_distribution": {"BTCUSDT": 2},
                "topic_distribution": {"policy": 1},
            },
            {
                "status": "completed",
                "ended_at": "2024-01-01T01:15:00Z",
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
    assert feature_timeline["series"]["has_activity"] == [True, True, False]
    assert feature_timeline["summary"] == {
        "aligned_summary_count": 2,
        "ignored_summary_count": 2,
    }


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


def test_build_external_feature_signals_enters_on_activity_and_exits_after_quiet_periods() -> None:
    entry_signals, exit_signals = build_external_feature_signals(
        {
            "series": {
                "matching_signal_count": [0, 2, 2, 0, 0, 1, 0],
            }
        },
        entry_count_threshold=1,
        exit_after_inactive_periods=2,
    )

    assert entry_signals == [False, True, False, False, False, True, False]
    assert exit_signals == [False, False, False, False, True, False, False]


def test_prepare_external_signal_manual_case_converts_external_signal_case_to_manual_strategy() -> None:
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
                "entry_count_threshold": 2,
                "exit_after_inactive_periods": 1,
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
                "status": "completed",
                "ended_at": "2024-01-01T01:30:00Z",
                "symbol_distribution": {"BTCUSDT": 1},
                "topic_distribution": {"policy": 1},
            }
        ],
    )

    assert prepared_case["strategy"] == "manual"
    assert prepared_case["entry_signals"] == [False, True, False]
    assert prepared_case["exit_signals"] == [False, False, True]
    assert prepared_case["external_signal_features"]["series"]["matching_signal_count"] == [0, 2, 0]


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
