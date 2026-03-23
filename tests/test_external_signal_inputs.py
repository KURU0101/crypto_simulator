from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.news_signal_cli import main as news_signal_main
from trade_simulator.news_signals import build_news_signal_bundle, normalize_news_signal_record
from trade_simulator.sns_signal_cli import main as sns_signal_main
from trade_simulator.sns_signals import build_sns_signal_bundle, normalize_sns_signal_record


def test_normalize_sns_signal_record_normalizes_symbol_topic_and_timestamp() -> None:
    normalized = normalize_sns_signal_record(
        {
            "source": "X",
            "symbol": "btc/usdt",
            "topic": "Bitcoin   ETF",
            "timestamp": "2026-03-24T10:00:00+09:00",
            "mention_count": 3,
            "positive_score": 0.7,
            "negative_score": 0.1,
            "neutral_score": 0.2,
            "activity_score": 0.8,
            "anomaly_score": 0.4,
            "metadata": {"window_minutes": 15},
        }
    )

    assert normalized["source"] == "x"
    assert normalized["symbol"] == "BTCUSDT"
    assert normalized["topic"] == "bitcoin etf"
    assert normalized["timestamp"] == "2026-03-24T01:00:00Z"
    assert normalized["entity_kind"] == "symbol"


def test_normalize_sns_signal_record_accepts_topic_only_boundary_case() -> None:
    normalized = normalize_sns_signal_record(
        {
            "source": "reddit",
            "topic": "layer 2",
            "timestamp": "2026-03-24T01:00:00Z",
            "mention_count": 0,
            "positive_score": 0.0,
            "negative_score": 0.0,
            "neutral_score": 1.0,
            "activity_score": 0.0,
            "anomaly_score": 0.0,
        }
    )

    assert normalized["symbol"] is None
    assert normalized["topic"] == "layer 2"
    assert normalized["entity_kind"] == "topic"


def test_normalize_sns_signal_record_rejects_missing_entity() -> None:
    with pytest.raises(ValueError, match="must include symbol or topic"):
        normalize_sns_signal_record(
            {
                "source": "x",
                "timestamp": "2026-03-24T01:00:00Z",
                "mention_count": 1,
                "positive_score": 0.1,
                "negative_score": 0.2,
                "neutral_score": 0.7,
                "activity_score": 0.3,
                "anomaly_score": 0.2,
            }
        )


def test_build_sns_signal_bundle_groups_by_symbol_and_topic() -> None:
    bundle = build_sns_signal_bundle(
        [
            {
                "source": "x",
                "symbol": "BTCUSDT",
                "topic": "bitcoin",
                "timestamp": "2026-03-24T01:00:00Z",
                "mention_count": 10,
                "positive_score": 0.5,
                "negative_score": 0.2,
                "neutral_score": 0.3,
                "activity_score": 0.6,
                "anomaly_score": 0.1,
            },
            {
                "source": "reddit",
                "topic": "macro",
                "timestamp": "2026-03-24T01:05:00Z",
                "mention_count": 5,
                "positive_score": 0.2,
                "negative_score": 0.2,
                "neutral_score": 0.6,
                "activity_score": 0.4,
                "anomaly_score": 0.3,
            },
        ]
    )

    assert bundle["summary"]["record_count"] == 2
    assert bundle["summary"]["total_mentions"] == 15
    assert list(bundle["by_symbol"]) == ["BTCUSDT"]
    assert sorted(bundle["by_topic"]) == ["bitcoin", "macro"]


def test_sns_signal_cli_prints_summary_for_sample_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "sns.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "source": "x",
                    "symbol": "BTCUSDT",
                    "timestamp": "2026-03-24T01:00:00Z",
                    "mention_count": 1,
                    "positive_score": 0.5,
                    "negative_score": 0.2,
                    "neutral_score": 0.3,
                    "activity_score": 0.4,
                    "anomaly_score": 0.1,
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = sns_signal_main(["--input", str(input_path)])
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["signal_type"] == "sns"
    assert captured["summary"]["record_count"] == 1
    assert captured["by_symbol_keys"] == ["BTCUSDT"]


def test_normalize_news_signal_record_normalizes_fields() -> None:
    normalized = normalize_news_signal_record(
        {
            "source": "CoinDesk",
            "symbol": "btc-usdt",
            "topic": "ETF flows",
            "published_at": "2026-03-24T10:15:00+09:00",
            "headline": "ETF flows remain positive",
            "url": "https://example.com/item",
            "relevance_score": 0.8,
            "sentiment_score": 0.2,
            "impact_score": 0.6,
            "category": "Markets",
        }
    )

    assert normalized["source"] == "coindesk"
    assert normalized["symbol"] == "BTCUSDT"
    assert normalized["topic"] == "etf flows"
    assert normalized["published_at"] == "2026-03-24T01:15:00Z"
    assert normalized["category"] == "markets"


def test_normalize_news_signal_record_accepts_asset_only_boundary_case() -> None:
    normalized = normalize_news_signal_record(
        {
            "source": "sec",
            "asset": "eth",
            "published_at": "2026-03-24T01:00:00Z",
            "headline": "Notice",
            "source_id": "notice-1",
            "relevance_score": 0.0,
            "sentiment_score": -1.0,
            "impact_score": 0.0,
            "category": "regulation",
        }
    )

    assert normalized["asset"] == "ETH"
    assert normalized["symbol"] is None
    assert normalized["entity_kind"] == "asset"


def test_normalize_news_signal_record_rejects_missing_locator() -> None:
    with pytest.raises(ValueError, match="must include url or source_id"):
        normalize_news_signal_record(
            {
                "source": "sec",
                "topic": "crypto regulation",
                "published_at": "2026-03-24T01:00:00Z",
                "headline": "Notice",
                "relevance_score": 0.4,
                "sentiment_score": 0.0,
                "impact_score": 0.5,
                "category": "regulation",
            }
        )


def test_build_news_signal_bundle_groups_entities() -> None:
    bundle = build_news_signal_bundle(
        [
            {
                "source": "coindesk",
                "symbol": "BTCUSDT",
                "published_at": "2026-03-24T01:00:00Z",
                "headline": "BTC headline",
                "url": "https://example.com/btc",
                "relevance_score": 0.7,
                "sentiment_score": 0.2,
                "impact_score": 0.8,
                "category": "markets",
            },
            {
                "source": "sec",
                "topic": "crypto regulation",
                "published_at": "2026-03-24T01:05:00Z",
                "headline": "Policy headline",
                "source_id": "policy-1",
                "relevance_score": 0.9,
                "sentiment_score": -0.2,
                "impact_score": 0.6,
                "category": "regulation",
            },
        ]
    )

    assert bundle["summary"]["record_count"] == 2
    assert list(bundle["by_symbol"]) == ["BTCUSDT"]
    assert list(bundle["by_topic"]) == ["crypto regulation"]


def test_news_signal_cli_prints_summary_for_sample_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "news.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "source": "coindesk",
                    "symbol": "BTCUSDT",
                    "published_at": "2026-03-24T01:00:00Z",
                    "headline": "BTC headline",
                    "url": "https://example.com/btc",
                    "relevance_score": 0.7,
                    "sentiment_score": 0.2,
                    "impact_score": 0.8,
                    "category": "markets",
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = news_signal_main(["--input", str(input_path)])
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["signal_type"] == "news"
    assert captured["summary"]["record_count"] == 1
    assert captured["by_symbol_keys"] == ["BTCUSDT"]
