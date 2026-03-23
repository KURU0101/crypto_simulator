from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.sns_adapters import (
    HACKER_NEWS_ITEM_URL_TEMPLATE,
    HACKER_NEWS_TOPSTORIES_URL,
    SNS_SOURCE_PROFILES,
    adapt_hacker_news_story,
    build_hacker_news_item_url,
    build_sns_dedup_key,
    infer_hacker_news_symbol_topic,
)
from trade_simulator.sns_collector import SnsCollectorError, load_sns_collector_config, run_sns_collector


def hacker_news_test_config(tmp_path: Path) -> dict:
    return {
        "collector": {
            "source": "hacker_news_public_api",
            "story_list": "topstories",
            "list_url": HACKER_NEWS_TOPSTORIES_URL,
            "item_url_template": HACKER_NEWS_ITEM_URL_TEMPLATE,
            "timeout_seconds": 30,
            "max_items": 3,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }


HN_ITEM_BTC = {
    "id": 1001,
    "type": "story",
    "title": "Bitcoin infrastructure startup raises funding",
    "time": 1_774_027_600,
    "by": "alice",
    "score": 120,
    "descendants": 45,
    "url": "https://example.com/bitcoin-startup",
}

HN_ITEM_AI = {
    "id": 1002,
    "type": "story",
    "title": "New AI compiler paper released",
    "time": 1_774_031_200,
    "by": "bob",
    "score": 90,
    "descendants": 12,
    "url": "https://example.com/ai-compiler",
}

HN_ITEM_ASK = {
    "id": 1003,
    "type": "ask",
    "title": "Ask HN: How are you deploying cloud infrastructure now?",
    "time": 1_774_034_800,
    "by": "carol",
    "score": 0,
    "descendants": 0,
}


def test_load_sns_collector_config_validates_hacker_news_defaults(tmp_path: Path) -> None:
    config = load_sns_collector_config(
        {
            "collector": {
                "source": "hacker_news_public_api",
            },
            "output": {
                "output_dir": str(tmp_path / "var"),
            },
        }
    )

    assert config["collector"]["story_list"] == "topstories"
    assert config["collector"]["list_url"] == HACKER_NEWS_TOPSTORIES_URL


def test_adapt_hacker_news_story_maps_metadata_and_scores() -> None:
    record = adapt_hacker_news_story(
        HN_ITEM_BTC,
        fetched_at="2026-03-24T03:00:00Z",
        list_name="topstories",
        item_url=build_hacker_news_item_url(1001),
    )

    assert record["source"] == "hacker_news"
    assert record["symbol"] == "BTCUSDT"
    assert record["topic"] == "bitcoin"
    assert record["mention_count"] == 45
    assert record["metadata"]["collector_source"] == "hacker_news_public_api"
    assert record["metadata"]["mention_count_semantics"] == "hacker news descendants comment count"
    assert record["metadata"]["story_type"] == "story"
    assert record["dedup_key"] == build_sns_dedup_key(
        source="hacker_news",
        timestamp="2026-03-20T17:26:40Z",
        entity_key="BTCUSDT",
        source_id="1001",
        permalink="https://example.com/bitcoin-startup",
    )


def test_infer_hacker_news_symbol_topic_is_source_specific() -> None:
    inferred = infer_hacker_news_symbol_topic(
        "New AI compiler paper released",
        "https://example.com/ai-compiler",
        None,
        "story",
    )

    assert inferred == {"symbol": None, "topic": "artificial intelligence"}


def test_run_sns_collector_collects_hacker_news_records_and_saves_them(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)
    payloads = {
        HACKER_NEWS_TOPSTORIES_URL: json.dumps([1001, 1002, 1003]),
        build_hacker_news_item_url(1001): json.dumps(HN_ITEM_BTC),
        build_hacker_news_item_url(1002): json.dumps(HN_ITEM_AI),
        build_hacker_news_item_url(1003): json.dumps(HN_ITEM_ASK),
    }

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: payloads[url],
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["source"] == "hacker_news_public_api"
    assert observation["story_list"] == "topstories"
    assert observation["source_specific"]["mention_count_semantics"] == "hacker news descendants comment count"
    assert observation["source_specific"]["story_list"] == "topstories"
    assert observation["fetched_item_count"] == 3
    assert observation["normalized_success_count"] == 3
    assert observation["saved_record_count"] == 3
    assert observation["duplicate_count"] == 0
    assert observation["source_distribution"] == {"hacker_news": 3}
    assert observation["symbol_distribution"] == {"BTCUSDT": 1}
    assert observation["topic_distribution"]["artificial intelligence"] == 1
    assert observation["topic_distribution"]["cloud infrastructure"] == 1
    assert observation["score_summary"] == {"min": 0, "max": 120, "average": 70.0, "total": 210}
    assert observation["comment_count_summary"] == {"min": 0, "max": 45, "average": 19.0, "total": 57}
    assert observation["story_type_distribution"] == {"story": 2, "ask": 1}
    assert Path(observation["saved_paths"]["normalized"]).exists()
    assert Path(observation["saved_paths"]["summary"]).exists()


def test_run_sns_collector_handles_hacker_news_list_fetch_failure(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)

    def fail(url: str, timeout_seconds: int) -> str:
        raise SnsCollectorError("network blocked")

    result = run_sns_collector(config, fetch_text_fn=fail, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "failed"
    assert result["observation"]["errors"] == [{"message": "network blocked"}]


def test_run_sns_collector_handles_hacker_news_item_fetch_failure(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)

    def fake_fetch(url: str, timeout_seconds: int) -> str:
        if url == HACKER_NEWS_TOPSTORIES_URL:
            return json.dumps([1001, 1002])
        if url == build_hacker_news_item_url(1001):
            return json.dumps(HN_ITEM_BTC)
        raise SnsCollectorError("item blocked")

    result = run_sns_collector(config, fetch_text_fn=fake_fetch, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["normalized_success_count"] == 1
    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["errors"][0]["story_id"] == 1002


def test_run_sns_collector_handles_empty_hacker_news_list_boundary_case(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: "[]",
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["fetched_item_count"] == 0
    assert result["observation"]["warnings"] == ["Hacker News story list returned no ids"]


def test_run_sns_collector_records_missing_hacker_news_required_fields(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)
    broken_item = {"id": 1001, "type": "story", "time": 1_774_027_600}
    payloads = {
        HACKER_NEWS_TOPSTORIES_URL: json.dumps([1001]),
        build_hacker_news_item_url(1001): json.dumps(broken_item),
    }

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: payloads[url],
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["title"] == 1


def test_run_sns_collector_records_invalid_hacker_news_timestamp(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)
    broken_item = {"id": 1001, "type": "story", "title": "Broken time", "time": "bad"}
    payloads = {
        HACKER_NEWS_TOPSTORIES_URL: json.dumps([1001]),
        build_hacker_news_item_url(1001): json.dumps(broken_item),
    }

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: payloads[url],
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["errors"][0]["message"] == "hacker news item time must be a number"


def test_run_sns_collector_accepts_hacker_news_zero_score_and_zero_descendants_boundary_case(tmp_path: Path) -> None:
    config = hacker_news_test_config(tmp_path)
    payloads = {
        HACKER_NEWS_TOPSTORIES_URL: json.dumps([1003]),
        build_hacker_news_item_url(1003): json.dumps(HN_ITEM_ASK),
    }

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: payloads[url],
        now_fn=lambda: 1_774_000_000.0,
    )

    record = result["bundle"]["records"][0]
    assert record["mention_count"] == 0
    assert record["metadata"]["score"] == 0
    assert record["metadata"]["descendants"] == 0


def test_hacker_news_profile_is_registered() -> None:
    assert SNS_SOURCE_PROFILES["hacker_news_public_api"]["kind"] == "hacker_news"
