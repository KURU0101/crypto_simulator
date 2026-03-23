from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.sns_adapters import (
    SNS_SOURCE_PROFILES,
    adapt_youtube_video,
    build_sns_dedup_key,
    build_youtube_channel_feed_url,
    infer_youtube_symbol_topic,
    parse_youtube_feed_items,
)
from trade_simulator.sns_collector import SnsCollectorError, load_sns_collector_config, run_sns_collector


YOUTUBE_FEED_ALPHA = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>Alpha Channel</title>
  <entry>
    <yt:videoId>video-alpha-1</yt:videoId>
    <yt:channelId>UCALPHA0000000000000001</yt:channelId>
    <title>Bitcoin market update from Alpha</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=video-alpha-1"/>
    <author><name>Alpha Channel</name></author>
    <published>2026-03-24T01:00:00+00:00</published>
    <updated>2026-03-24T01:05:00+00:00</updated>
  </entry>
  <entry>
    <yt:videoId>video-alpha-2</yt:videoId>
    <yt:channelId>UCALPHA0000000000000001</yt:channelId>
    <title>Ethereum builders weekly</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=video-alpha-2"/>
    <author><name>Alpha Channel</name></author>
    <published>2026-03-24T02:00:00+00:00</published>
    <updated>2026-03-24T02:05:00+00:00</updated>
  </entry>
</feed>
"""


YOUTUBE_FEED_BETA = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>Beta Policy Lab</title>
  <entry>
    <yt:videoId>video-beta-1</yt:videoId>
    <yt:channelId>UCBETA00000000000000002</yt:channelId>
    <title>Policy launch briefing for AI systems</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=video-beta-1"/>
    <author><name>Beta Policy Lab</name></author>
    <published>2026-03-24T01:30:00+00:00</published>
    <updated>2026-03-24T01:35:00+00:00</updated>
  </entry>
</feed>
"""


def youtube_test_config(tmp_path: Path) -> dict:
    return {
        "collector": {
            "source": "youtube_channel_rss",
            "timeout_seconds": 30,
            "max_items": 10,
            "groups": [
                {
                    "group_id": "markets",
                    "group_label": "Markets",
                    "group_theme": "crypto and financial markets",
                    "publisher_type": "mixed",
                    "channels": [
                        {
                            "channel_id": "UCALPHA0000000000000001",
                            "channel_label": "Alpha Channel",
                            "publisher_type": "media",
                            "theme_tags": ["crypto markets", "bitcoin"],
                        }
                    ],
                },
                {
                    "group_id": "policy",
                    "group_label": "Policy",
                    "group_theme": "public policy and research",
                    "publisher_type": "mixed",
                    "channels": [
                        {
                            "channel_id": "UCBETA00000000000000002",
                            "channel_label": "Beta Policy Lab",
                            "publisher_type": "university",
                            "theme_tags": ["policy", "research", "ai"],
                        }
                    ],
                },
            ],
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }


def test_load_sns_collector_config_validates_youtube_groups_and_channels(tmp_path: Path) -> None:
    config = load_sns_collector_config(youtube_test_config(tmp_path))

    assert config["collector"]["max_items"] == 10
    assert config["collector"]["groups"][0]["channels"][0]["feed_url"] == build_youtube_channel_feed_url(
        "UCALPHA0000000000000001"
    )


def test_parse_youtube_feed_items_respects_max_items() -> None:
    items = parse_youtube_feed_items(YOUTUBE_FEED_ALPHA, max_items=1)

    assert len(items) == 1
    assert items[0]["video_id"] == "video-alpha-1"


def test_adapt_youtube_video_maps_group_and_channel_metadata() -> None:
    item = parse_youtube_feed_items(YOUTUBE_FEED_ALPHA, max_items=1)[0]
    record = adapt_youtube_video(
        item,
        fetched_at="2026-03-24T03:00:00Z",
        channel_context={
            "group_id": "markets",
            "group_label": "Markets",
            "group_theme": "crypto and financial markets",
            "group_publisher_type": "mixed",
            "channel_id": "UCALPHA0000000000000001",
            "channel_label": "Alpha Channel",
            "publisher_type": "media",
            "theme_tags": ["crypto markets", "bitcoin"],
            "feed_url": build_youtube_channel_feed_url("UCALPHA0000000000000001"),
        },
    )

    assert record["source"] == "youtube"
    assert record["symbol"] == "BTCUSDT"
    assert record["topic"] == "bitcoin"
    assert record["mention_count"] == 1
    assert record["metadata"]["collector_source"] == "youtube_channel_rss"
    assert record["metadata"]["mention_count_semantics"] == "youtube upload count fixed at 1 per video"
    assert record["metadata"]["group_id"] == "markets"
    assert record["metadata"]["channel_label"] == "Alpha Channel"
    assert record["dedup_key"] == build_sns_dedup_key(
        source="youtube",
        timestamp="2026-03-24T01:00:00+00:00",
        entity_key="BTCUSDT",
        source_id="video-alpha-1",
        permalink="https://www.youtube.com/watch?v=video-alpha-1",
    )


def test_infer_youtube_symbol_topic_is_source_specific() -> None:
    inferred = infer_youtube_symbol_topic(
        "Policy launch briefing for AI systems",
        "Beta Policy Lab",
        "Policy",
        "public policy and research",
        ["policy", "research", "ai"],
    )

    assert inferred == {"symbol": None, "topic": "artificial intelligence"}


def test_run_sns_collector_collects_multiple_youtube_channels_and_saves_them(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)
    feed_map = {
        build_youtube_channel_feed_url("UCALPHA0000000000000001"): YOUTUBE_FEED_ALPHA,
        build_youtube_channel_feed_url("UCBETA00000000000000002"): YOUTUBE_FEED_BETA,
    }

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: feed_map[url],
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["source"] == "youtube_channel_rss"
    assert observation["configured_group_count"] == 2
    assert observation["configured_channel_count"] == 2
    assert observation["successful_channel_count"] == 2
    assert observation["failed_channel_count"] == 0
    assert observation["source_specific"]["mention_count_semantics"] == "youtube upload count fixed at 1 per video"
    assert observation["source_specific"]["configured_group_count"] == 2
    assert observation["fetched_item_count"] == 3
    assert observation["normalized_success_count"] == 3
    assert observation["saved_record_count"] == 3
    assert observation["group_distribution"] == {"markets": 2, "policy": 1}
    assert observation["group_theme_distribution"] == {
        "crypto and financial markets": 2,
        "public policy and research": 1,
    }
    assert observation["publisher_type_distribution"] == {"media": 2, "university": 1}
    assert observation["channel_distribution"] == {
        "Alpha Channel (UCALPHA0000000000000001)": 2,
        "Beta Policy Lab (UCBETA00000000000000002)": 1,
    }
    assert observation["symbol_distribution"] == {"BTCUSDT": 1, "ETHUSDT": 1}
    assert observation["topic_distribution"]["artificial intelligence"] == 1
    assert Path(observation["saved_paths"]["normalized"]).exists()
    assert Path(observation["saved_paths"]["summary"]).exists()

    saved_bundle = json.loads(Path(observation["saved_paths"]["normalized"]).read_text(encoding="utf-8"))
    assert saved_bundle["summary"]["record_count"] == 3
    assert saved_bundle["summary"]["unique_dedup_key_count"] == 3


def test_run_sns_collector_handles_partial_youtube_channel_failure(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)
    good_url = build_youtube_channel_feed_url("UCALPHA0000000000000001")
    bad_url = build_youtube_channel_feed_url("UCBETA00000000000000002")

    def fake_fetch(url: str, timeout_seconds: int) -> str:
        if url == bad_url:
            raise SnsCollectorError("channel unavailable")
        return YOUTUBE_FEED_ALPHA

    result = run_sns_collector(config, fetch_text_fn=fake_fetch, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["successful_channel_count"] == 1
    assert result["observation"]["failed_channel_count"] == 1
    assert result["observation"]["normalized_success_count"] == 2
    assert "youtube channel fetch failures: 1" in result["observation"]["warnings"]
    assert result["observation"]["errors"][0]["channel_id"] == "UCBETA00000000000000002"
    assert good_url != bad_url


def test_run_sns_collector_fails_when_all_youtube_channels_fail(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)

    def always_fail(url: str, timeout_seconds: int) -> str:
        raise SnsCollectorError("network blocked")

    result = run_sns_collector(config, fetch_text_fn=always_fail, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "failed"
    assert result["observation"]["failed_channel_count"] == 2
    assert result["observation"]["saved_paths"] == {}


def test_run_sns_collector_handles_empty_youtube_feed_boundary_case(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)
    empty_feed = """<?xml version="1.0" encoding="UTF-8"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom"></feed>"""

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: empty_feed,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["fetched_item_count"] == 0
    assert result["observation"]["saved_record_count"] == 0
    assert result["observation"]["empty_channel_count"] == 2


def test_run_sns_collector_records_missing_youtube_required_fields(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)
    broken_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <yt:videoId>video-bad-1</yt:videoId>
        <yt:channelId>UCALPHA0000000000000001</yt:channelId>
        <published>2026-03-24T01:00:00+00:00</published>
        <author><name>Alpha Channel</name></author>
      </entry>
    </feed>
    """

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: broken_feed if "UCALPHA" in url else YOUTUBE_FEED_BETA,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["title"] == 1
    assert result["observation"]["missing_field_counts"]["video_url"] == 1


def test_run_sns_collector_records_invalid_youtube_timestamp_as_validation_failure(tmp_path: Path) -> None:
    config = youtube_test_config(tmp_path)
    broken_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <yt:videoId>video-bad-1</yt:videoId>
        <yt:channelId>UCALPHA0000000000000001</yt:channelId>
        <title>Broken timestamp video</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v=video-bad-1"/>
        <author><name>Alpha Channel</name></author>
        <published>invalid</published>
        <updated>2026-03-24T01:05:00+00:00</updated>
      </entry>
    </feed>
    """

    result = run_sns_collector(
        config,
        fetch_text_fn=lambda url, timeout_seconds: broken_feed if "UCALPHA" in url else YOUTUBE_FEED_BETA,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["validation_failure_count"] == 1
    assert "Invalid isoformat string" in result["observation"]["errors"][0]["message"]


def test_youtube_profile_is_registered() -> None:
    assert SNS_SOURCE_PROFILES["youtube_channel_rss"]["kind"] == "youtube"
