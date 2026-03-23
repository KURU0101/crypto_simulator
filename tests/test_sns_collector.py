from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.external_signal_test_helpers import (
    assert_saved_summary_matches_observation,
    assert_summary_not_saved,
    load_saved_json,
)
from trade_simulator.sns_adapters import (
    REDDIT_SUBREDDIT_NEW_JSON_URL,
    adapt_reddit_post,
    build_sns_dedup_key,
    infer_reddit_symbol_topic,
)
from trade_simulator.sns_collector import (
    SNS_SOURCE_PROFILES,
    SnsCollectorError,
    load_sns_collector_config,
    parse_reddit_listing_items,
    run_sns_collector,
)
from trade_simulator.sns_collector_cli import main as sns_collector_main


REDDIT_TWO_ITEMS = json.dumps(
    {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "btc1",
                        "title": "Bitcoin rally as ETF demand stays high",
                        "selftext": "",
                        "subreddit": "CryptoCurrency",
                        "permalink": "/r/CryptoCurrency/comments/btc1/bitcoin_rally/",
                        "created_utc": 1_774_027_600,
                        "num_comments": 12,
                        "score": 85,
                        "upvote_ratio": 0.93,
                        "link_flair_text": "Markets",
                        "author": "alice",
                    }
                },
                {
                    "data": {
                        "id": "macro1",
                        "title": "Fed macro thread for crypto this week",
                        "selftext": "Discussion only",
                        "subreddit": "CryptoMarkets",
                        "permalink": "/r/CryptoMarkets/comments/macro1/fed_macro_thread/",
                        "created_utc": 1_774_031_200,
                        "num_comments": 0,
                        "score": 4,
                        "upvote_ratio": 0.51,
                        "link_flair_text": None,
                        "author": "bob",
                    }
                },
            ]
        }
    }
)


def test_load_sns_collector_config_defaults_listing_url_for_supported_source() -> None:
    config = load_sns_collector_config(
        {
            "collector": {
                "source": "reddit_subreddit_new_json",
            },
            "output": {
                "output_dir": "var/sns_signals",
            },
        }
    )

    assert config["collector"]["listing_url"] == SNS_SOURCE_PROFILES["reddit_subreddit_new_json"]["default_listing_url"]
    assert config["collector"]["max_items"] == 50


def test_load_sns_collector_config_rejects_unsupported_source() -> None:
    with pytest.raises(ValueError, match="collector.source must be one of"):
        load_sns_collector_config(
            {
                "collector": {
                    "source": "unknown_sns",
                },
                "output": {
                    "output_dir": "var/sns_signals",
                },
            }
        )


def test_parse_reddit_listing_items_respects_max_items() -> None:
    items = parse_reddit_listing_items(REDDIT_TWO_ITEMS, max_items=1)

    assert len(items) == 1
    assert items[0]["id"] == "btc1"


def test_adapt_reddit_post_maps_symbol_scores_and_metadata() -> None:
    record = adapt_reddit_post(
        {
            "id": "btc1",
            "title": "Bitcoin rally as ETF demand stays high",
            "selftext": "",
            "subreddit": "CryptoCurrency",
            "permalink": "/r/CryptoCurrency/comments/btc1/bitcoin_rally/",
            "created_utc": 1_774_027_600,
            "num_comments": 12,
            "score": 85,
            "upvote_ratio": 0.93,
            "link_flair_text": "Markets",
            "author": "alice",
        },
        fetched_at="2026-03-24T03:00:00Z",
        listing_url=REDDIT_SUBREDDIT_NEW_JSON_URL,
    )

    assert record["source"] == "reddit"
    assert record["symbol"] == "BTCUSDT"
    assert record["topic"] == "bitcoin"
    assert record["timestamp"] == "2026-03-20T17:26:40Z"
    assert record["mention_count"] == 12
    assert record["positive_score"] == 0.7
    assert record["metadata"]["collector_source"] == "reddit_subreddit_new_json"
    assert record["metadata"]["mention_count_semantics"] == "reddit num_comments"
    assert record["dedup_key"] == build_sns_dedup_key(
        source="reddit",
        timestamp="2026-03-20T17:26:40Z",
        entity_key="BTCUSDT",
        post_id="btc1",
        permalink="/r/CryptoCurrency/comments/btc1/bitcoin_rally/",
    )


def test_infer_reddit_symbol_topic_is_source_specific() -> None:
    inferred = infer_reddit_symbol_topic("Fed macro thread for crypto this week", "", "CryptoMarkets", None)

    assert inferred == {"symbol": None, "topic": "crypto macro"}


def test_run_sns_collector_collects_reddit_records_and_saves_them(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
            "listing_url": REDDIT_SUBREDDIT_NEW_JSON_URL,
            "timeout_seconds": 30,
            "max_items": 10,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: REDDIT_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["signal_type"] == "sns"
    assert observation["source"] == "reddit_subreddit_new_json"
    assert observation["run_id"] == "20260320T094640Z"
    assert observation["fetched_item_count"] == 2
    assert observation["normalized_success_count"] == 2
    assert observation["validation_failure_count"] == 0
    assert observation["saved_record_count"] == 2
    assert observation["duplicate_count"] == 0
    assert observation["symbol_distribution"] == {"BTCUSDT": 1}
    assert observation["topic_distribution"]["bitcoin"] == 1
    assert observation["topic_distribution"]["crypto macro"] == 1
    assert observation["mention_count_summary"] == {"min": 0, "max": 12, "average": 6.0, "total": 12}
    assert observation["source_specific"]["mention_count_semantics"] == "reddit num_comments"
    assert observation["source_specific"]["listing_url"] == REDDIT_SUBREDDIT_NEW_JSON_URL
    assert observation["timestamp_by_hour_utc"] == {
        "2026-03-20T17:00:00Z": 1,
        "2026-03-20T18:00:00Z": 1,
    }
    assert_saved_summary_matches_observation(observation)

    saved_bundle = load_saved_json(observation["saved_paths"]["normalized"])
    assert saved_bundle["summary"]["record_count"] == 2
    assert saved_bundle["summary"]["total_mentions"] == 12
    assert saved_bundle["summary"]["unique_dedup_key_count"] == 2
    assert saved_bundle["summary"]["duplicate_count"] == 0


def test_run_sns_collector_skips_reddit_summary_file_when_disabled_boundary_case(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": False,
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: REDDIT_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["status"] == "completed"
    assert_summary_not_saved(result["observation"])


def test_run_sns_collector_handles_empty_listing_boundary_case(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: json.dumps({"data": {"children": []}}),
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["fetched_item_count"] == 0
    assert result["observation"]["saved_record_count"] == 0
    assert result["observation"]["warnings"] == ["SNS listing returned no items"]


def test_run_sns_collector_records_missing_required_fields(tmp_path: Path) -> None:
    listing = json.dumps(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "bad-1",
                            "title": "Missing permalink",
                            "subreddit": "CryptoCurrency",
                            "created_utc": 1_774_027_600,
                        }
                    }
                ]
            }
        }
    )
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: listing,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["normalized_success_count"] == 0
    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["permalink"] == 1


def test_run_sns_collector_records_invalid_timestamp_as_validation_failure(tmp_path: Path) -> None:
    listing = json.dumps(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "bad-ts",
                            "title": "Broken timestamp item",
                            "subreddit": "CryptoCurrency",
                            "permalink": "/r/CryptoCurrency/comments/badts/broken/",
                            "created_utc": "not-a-number",
                        }
                    }
                ]
            }
        }
    )
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: listing,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["normalized_success_count"] == 0
    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["errors"][0]["message"] == "reddit item created_utc must be a number"


def test_run_sns_collector_defaults_missing_score_fields_to_zero_boundary_case(tmp_path: Path) -> None:
    listing = json.dumps(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "topic-1",
                            "title": "Stablecoin discussion",
                            "subreddit": "CryptoCurrency",
                            "permalink": "/r/CryptoCurrency/comments/topic1/stablecoin_discussion/",
                            "created_utc": 1_774_027_600,
                            "num_comments": 0,
                        }
                    }
                ]
            }
        }
    )
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: listing,
        now_fn=lambda: 1_774_000_000.0,
    )

    record = result["bundle"]["records"][0]
    assert record["symbol"] is None
    assert record["topic"] == "stablecoins"
    assert record["mention_count"] == 0
    assert record["metadata"]["score"] is None
    assert result["observation"]["missing_field_counts"]["score"] == 1
    assert result["observation"]["missing_field_counts"]["upvote_ratio"] == 1


def test_run_sns_collector_preserves_duplicate_dedup_key_boundary_case(tmp_path: Path) -> None:
    listing = json.dumps(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "btc1",
                            "title": "Bitcoin rally as ETF demand stays high",
                            "subreddit": "CryptoCurrency",
                            "permalink": "/r/CryptoCurrency/comments/btc1/bitcoin_rally/",
                            "created_utc": 1_774_027_600,
                            "num_comments": 12,
                            "score": 85,
                            "upvote_ratio": 0.93,
                        }
                    },
                    {
                        "data": {
                            "id": "btc1",
                            "title": "Bitcoin rally as ETF demand stays high",
                            "subreddit": "CryptoCurrency",
                            "permalink": "/r/CryptoCurrency/comments/btc1/bitcoin_rally/",
                            "created_utc": 1_774_027_600,
                            "num_comments": 12,
                            "score": 85,
                            "upvote_ratio": 0.93,
                        }
                    },
                ]
            }
        }
    )
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_sns_collector(
        config,
        fetch_listing_fn=lambda listing_url, timeout_seconds: listing,
        now_fn=lambda: 1_774_000_000.0,
    )

    dedup_keys = [record["dedup_key"] for record in result["bundle"]["records"]]
    assert result["observation"]["normalized_success_count"] == 2
    assert result["observation"]["duplicate_count"] == 1
    assert result["bundle"]["summary"]["duplicate_count"] == 1
    assert len(set(dedup_keys)) == 1


def test_run_sns_collector_handles_fetch_failure(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "reddit_subreddit_new_json",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    def raise_error(listing_url: str, timeout_seconds: int) -> str:
        raise SnsCollectorError("network blocked")

    result = run_sns_collector(config, fetch_listing_fn=raise_error, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "failed"
    assert result["observation"]["errors"] == [{"message": "network blocked"}]


def test_sns_collector_cli_prints_observation_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "collector.json"
    config_path.write_text(
        json.dumps(
            {
                "collector": {
                    "source": "reddit_subreddit_new_json",
                    "listing_url": REDDIT_SUBREDDIT_NEW_JSON_URL,
                    "timeout_seconds": 30,
                    "max_items": 10,
                },
                "output": {
                    "output_dir": str(tmp_path / "var"),
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_sns_collector(config: dict) -> dict:
        return {
            "bundle": {"records": []},
            "observation": {
                "status": "completed",
                "signal_type": "sns",
                "source": "reddit_subreddit_new_json",
                "fetched_item_count": 0,
                "normalized_success_count": 0,
                "normalized_failure_count": 0,
                "validation_failure_count": 0,
                "saved_record_count": 0,
                "duplicate_count": 0,
                "warnings": [],
                "errors": [],
                "saved_paths": {},
            },
        }

    monkeypatch.setattr("trade_simulator.sns_collector_cli.run_sns_collector", fake_run_sns_collector)

    exit_code = sns_collector_main(["--config", str(config_path)])
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["status"] == "completed"
    assert captured["source"] == "reddit_subreddit_new_json"
