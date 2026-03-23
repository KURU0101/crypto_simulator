from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_simulator.news_adapters import build_news_dedup_key
from trade_simulator.news_collector import (
    COINDESK_RSS_FEED_URL,
    FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL,
    NEWS_SOURCE_PROFILES,
    NewsCollectorError,
    SEC_PRESS_RELEASES_RSS_FEED_URL,
    adapt_coindesk_rss_item,
    adapt_federal_reserve_press_release_rss_item,
    adapt_sec_press_release_rss_item,
    load_news_collector_config,
    parse_coindesk_rss_items,
    parse_rss_items,
    run_news_collector,
)
from trade_simulator.news_collector_cli import main as news_collector_main


RSS_TWO_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CoinDesk</title>
    <item>
      <title>Bitcoin rises as ETF flows improve</title>
      <link>https://www.coindesk.com/markets/bitcoin-rises</link>
      <guid>btc-1</guid>
      <description>Example</description>
      <pubDate>Tue, 24 Mar 2026 01:00:00 GMT</pubDate>
      <category>Markets</category>
    </item>
    <item>
      <title>Policy update affects stablecoin issuers</title>
      <link>https://www.coindesk.com/policy/stablecoin-update</link>
      <guid>policy-1</guid>
      <description>Example</description>
      <pubDate>Tue, 24 Mar 2026 02:00:00 GMT</pubDate>
      <category>Policy</category>
    </item>
  </channel>
</rss>
"""


SEC_RSS_TWO_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>SEC Press Releases</title>
    <item>
      <title>SEC Announces Digital Asset Enforcement Results</title>
      <link>https://www.sec.gov/news/press-release/2026-50</link>
      <guid>2026-50</guid>
      <description>Statement on crypto and digital asset market oversight.</description>
      <pubDate>Tue, 24 Mar 2026 03:00:00 GMT</pubDate>
      <category>Enforcement</category>
    </item>
    <item>
      <title>SEC Adopts Disclosure Rule Update</title>
      <link>https://www.sec.gov/news/press-release/2026-51</link>
      <guid>2026-51</guid>
      <description>Update for public company disclosures.</description>
      <pubDate>Tue, 24 Mar 2026 03:00:00 GMT</pubDate>
      <category>Rulemaking</category>
    </item>
  </channel>
</rss>
"""


FEDERAL_RESERVE_RSS_TWO_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve Press Releases</title>
    <item>
      <title>Federal Reserve issues policy statement on reserve balances</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260324a.htm</link>
      <guid>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260324a.htm</guid>
      <description>Policy statement on reserve balances.</description>
      <pubDate>Tue, 24 Mar 2026 04:00:00 GMT</pubDate>
      <category>Monetary Policy</category>
    </item>
    <item>
      <title>Federal Reserve announces supervisory guidance update</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260324a.htm</link>
      <guid>https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260324a.htm</guid>
      <description>Supervisory guidance update for banks.</description>
      <pubDate>Tue, 24 Mar 2026 04:30:00 GMT</pubDate>
      <category>Banking and Consumer Regulatory Policy</category>
    </item>
  </channel>
</rss>
"""


def test_load_news_collector_config_defaults_feed_url_for_each_supported_source() -> None:
    for source, profile in NEWS_SOURCE_PROFILES.items():
        config = load_news_collector_config(
            {
                "collector": {
                    "source": source,
                },
                "output": {
                    "output_dir": "var/news_signals",
                },
            }
        )

        assert config["collector"]["feed_url"] == profile["default_feed_url"]
        assert config["collector"]["max_items"] == 50


def test_load_news_collector_config_rejects_unsupported_source() -> None:
    with pytest.raises(ValueError, match="collector.source must be one of"):
        load_news_collector_config(
            {
                "collector": {
                    "source": "unknown_rss",
                },
                "output": {
                    "output_dir": "var/news_signals",
                },
            }
        )


def test_parse_coindesk_rss_items_respects_max_items() -> None:
    items = parse_coindesk_rss_items(RSS_TWO_ITEMS, max_items=1)

    assert len(items) == 1
    assert items[0]["title"] == "Bitcoin rises as ETF flows improve"


def test_parse_rss_items_accepts_same_timestamp_boundary_case() -> None:
    items = parse_rss_items(SEC_RSS_TWO_ITEMS, max_items=2)

    assert len(items) == 2
    assert items[0]["pub_date"] == items[1]["pub_date"]


def test_adapt_coindesk_rss_item_maps_symbol_and_metadata() -> None:
    record = adapt_coindesk_rss_item(
        {
            "title": "Bitcoin rises as ETF flows improve",
            "link": "https://www.coindesk.com/markets/bitcoin-rises",
            "guid": "btc-1",
            "description": "Example",
            "pub_date": "Tue, 24 Mar 2026 01:00:00 GMT",
            "categories": ["Markets"],
        },
        fetched_at="2026-03-24T03:00:00Z",
        feed_url=COINDESK_RSS_FEED_URL,
    )

    assert record["source"] == "coindesk"
    assert record["symbol"] == "BTCUSDT"
    assert record["asset"] == "BTC"
    assert record["topic"] == "bitcoin"
    assert record["published_at"] == "2026-03-24T01:00:00Z"
    assert record["dedup_key"] == build_news_dedup_key(
        source="coindesk",
        published_at="2026-03-24T01:00:00Z",
        headline="Bitcoin rises as ETF flows improve",
        source_id="btc-1",
        url="https://www.coindesk.com/markets/bitcoin-rises",
    )
    assert record["metadata"]["collector_source"] == "coindesk_rss"


def test_adapt_sec_press_release_rss_item_maps_topic_and_metadata() -> None:
    record = adapt_sec_press_release_rss_item(
        {
            "title": "SEC Announces Digital Asset Enforcement Results",
            "link": "https://www.sec.gov/news/press-release/2026-50",
            "guid": "2026-50",
            "description": "Statement on crypto and digital asset market oversight.",
            "pub_date": "Tue, 24 Mar 2026 03:00:00 GMT",
            "categories": ["Enforcement"],
        },
        fetched_at="2026-03-24T03:10:00Z",
        feed_url=SEC_PRESS_RELEASES_RSS_FEED_URL,
    )

    assert record["source"] == "sec"
    assert record["symbol"] is None
    assert record["asset"] is None
    assert record["topic"] == "crypto regulation"
    assert record["published_at"] == "2026-03-24T03:00:00Z"
    assert record["source_id"] == "2026-50"
    assert record["dedup_key"] == build_news_dedup_key(
        source="sec",
        published_at="2026-03-24T03:00:00Z",
        headline="SEC Announces Digital Asset Enforcement Results",
        source_id="2026-50",
        url="https://www.sec.gov/news/press-release/2026-50",
    )
    assert record["metadata"]["collector_source"] == "sec_press_releases_rss"


def test_adapt_federal_reserve_press_release_rss_item_maps_topic_and_metadata() -> None:
    record = adapt_federal_reserve_press_release_rss_item(
        {
            "title": "Federal Reserve issues policy statement on reserve balances",
            "link": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260324a.htm",
            "guid": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260324a.htm",
            "description": "Policy statement on reserve balances.",
            "pub_date": "Tue, 24 Mar 2026 04:00:00 GMT",
            "categories": ["Monetary Policy"],
        },
        fetched_at="2026-03-24T04:10:00Z",
        feed_url=FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL,
    )

    assert record["source"] == "federal_reserve"
    assert record["symbol"] is None
    assert record["asset"] is None
    assert record["topic"] == "monetary policy"
    assert record["published_at"] == "2026-03-24T04:00:00Z"
    assert record["category"] == "monetary policy"
    assert record["metadata"]["collector_source"] == "federal_reserve_press_releases_rss"


def test_build_news_dedup_key_falls_back_from_source_id_to_url_to_headline() -> None:
    with_source_id = build_news_dedup_key(
        source="sec",
        published_at="2026-03-24T03:00:00Z",
        headline="Headline",
        source_id="2026-50",
        url="https://example.com/item",
    )
    with_url = build_news_dedup_key(
        source="sec",
        published_at="2026-03-24T03:00:00Z",
        headline="Headline",
        source_id=None,
        url="https://example.com/item",
    )
    with_headline = build_news_dedup_key(
        source="sec",
        published_at="2026-03-24T03:00:00Z",
        headline="Headline",
        source_id=None,
        url=None,
    )

    assert with_source_id.startswith("sec:")
    assert with_url.startswith("sec:")
    assert with_headline.startswith("sec:")
    assert len({with_source_id, with_url, with_headline}) == 3


def test_run_news_collector_collects_coindesk_records_and_saves_them(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "coindesk_rss",
            "feed_url": COINDESK_RSS_FEED_URL,
            "timeout_seconds": 30,
            "max_items": 10,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: RSS_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["signal_type"] == "news"
    assert observation["source"] == "coindesk_rss"
    assert observation["run_id"] == "20260320T094640Z"
    assert observation["fetched_item_count"] == 2
    assert observation["normalized_success_count"] == 2
    assert observation["validation_failure_count"] == 0
    assert observation["saved_record_count"] == 2
    assert observation["duplicate_count"] == 0
    assert observation["symbol_distribution"] == {"BTCUSDT": 1}
    assert observation["asset_distribution"] == {"BTC": 1}
    assert observation["topic_distribution"]["bitcoin"] == 1
    assert observation["topic_distribution"]["policy"] == 1
    assert observation["category_distribution"] == {"markets": 1, "policy": 1}
    assert observation["source_distribution"] == {"coindesk": 2}
    assert observation["source_specific"] == {"feed_url": COINDESK_RSS_FEED_URL}
    assert Path(observation["saved_paths"]["normalized"]).exists()
    assert Path(observation["saved_paths"]["summary"]).exists()

    saved_bundle = json.loads(Path(observation["saved_paths"]["normalized"]).read_text(encoding="utf-8"))
    assert saved_bundle["summary"]["record_count"] == 2
    assert saved_bundle["summary"]["categories"] == ["markets", "policy"]
    assert saved_bundle["summary"]["unique_dedup_key_count"] == 2
    assert saved_bundle["summary"]["duplicate_count"] == 0
    assert "dedup_key" in saved_bundle["records"][0]
    saved_summary = json.loads(Path(observation["saved_paths"]["summary"]).read_text(encoding="utf-8"))
    assert saved_summary == observation


def test_run_news_collector_collects_sec_records_and_tracks_source_specific_summary(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "sec_press_releases_rss",
            "feed_url": SEC_PRESS_RELEASES_RSS_FEED_URL,
            "timeout_seconds": 30,
            "max_items": 10,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: SEC_RSS_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["signal_type"] == "news"
    assert observation["source"] == "sec_press_releases_rss"
    assert observation["fetched_item_count"] == 2
    assert observation["normalized_success_count"] == 2
    assert observation["normalized_failure_count"] == 0
    assert observation["saved_record_count"] == 2
    assert observation["duplicate_count"] == 0
    assert observation["source_distribution"] == {"sec": 2}
    assert observation["symbol_distribution"] == {}
    assert observation["asset_distribution"] == {}
    assert observation["topic_distribution"]["crypto regulation"] == 1
    assert observation["topic_distribution"]["sec rulemaking"] == 1
    assert observation["category_distribution"] == {"enforcement": 1, "rulemaking": 1}
    assert observation["source_specific"] == {"feed_url": SEC_PRESS_RELEASES_RSS_FEED_URL}
    assert observation["published_at_by_hour_utc"] == {"2026-03-24T03:00:00Z": 2}
    assert Path(observation["saved_paths"]["summary"]).exists()

    saved_bundle = json.loads(Path(observation["saved_paths"]["normalized"]).read_text(encoding="utf-8"))
    assert saved_bundle["summary"]["sources"] == ["sec"]
    assert saved_bundle["summary"]["unique_dedup_key_count"] == 2
    saved_summary = json.loads(Path(observation["saved_paths"]["summary"]).read_text(encoding="utf-8"))
    assert saved_summary["signal_type"] == "news"
    assert saved_summary["source_specific"] == {"feed_url": SEC_PRESS_RELEASES_RSS_FEED_URL}


def test_run_news_collector_skips_summary_file_when_disabled_boundary_case(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "coindesk_rss",
            "feed_url": COINDESK_RSS_FEED_URL,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": False,
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: RSS_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert "summary" not in observation["saved_paths"]
    assert Path(observation["saved_paths"]["normalized"]).exists()


def test_run_news_collector_collects_federal_reserve_records_and_saves_them(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "federal_reserve_press_releases_rss",
            "feed_url": FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL,
            "timeout_seconds": 30,
            "max_items": 10,
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
            "save_run_summary": True,
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: FEDERAL_RESERVE_RSS_TWO_ITEMS,
        now_fn=lambda: 1_774_000_000.0,
    )

    observation = result["observation"]
    assert observation["status"] == "completed"
    assert observation["signal_type"] == "news"
    assert observation["source"] == "federal_reserve_press_releases_rss"
    assert observation["fetched_item_count"] == 2
    assert observation["normalized_success_count"] == 2
    assert observation["saved_record_count"] == 2
    assert observation["duplicate_count"] == 0
    assert observation["source_distribution"] == {"federal_reserve": 2}
    assert observation["topic_distribution"] == {"bank regulation": 1, "monetary policy": 1}
    assert observation["category_distribution"] == {
        "banking and consumer regulatory policy": 1,
        "monetary policy": 1,
    }
    assert observation["source_specific"] == {"feed_url": FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL}
    assert observation["published_at_by_hour_utc"] == {"2026-03-24T04:00:00Z": 2}

    saved_bundle = json.loads(Path(observation["saved_paths"]["normalized"]).read_text(encoding="utf-8"))
    assert saved_bundle["summary"]["sources"] == ["federal_reserve"]
    assert saved_bundle["summary"]["duplicate_count"] == 0


def test_run_news_collector_handles_empty_feed_boundary_case(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "coindesk_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: "<?xml version='1.0'?><rss><channel></channel></rss>",
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["status"] == "completed"
    assert result["observation"]["fetched_item_count"] == 0
    assert result["observation"]["saved_record_count"] == 0
    assert result["observation"]["duplicate_count"] == 0
    assert result["observation"]["warnings"] == ["rss feed returned no items"]
    assert result["observation"]["category_distribution"] == {}


def test_run_news_collector_records_normalization_failures_for_missing_required_fields(tmp_path: Path) -> None:
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Missing link item</title>
          <guid>bad-1</guid>
          <pubDate>Tue, 24 Mar 2026 01:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    config = {
        "collector": {
            "source": "coindesk_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: xml_text,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["normalized_success_count"] == 0
    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["link"] == 1


def test_run_news_collector_records_invalid_published_at_as_validation_failure(tmp_path: Path) -> None:
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Federal Reserve issues policy statement on reserve balances</title>
          <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260324a.htm</link>
          <guid>fed-1</guid>
          <description>Policy statement on reserve balances.</description>
          <pubDate>invalid date</pubDate>
          <category>Monetary Policy</category>
        </item>
      </channel>
    </rss>
    """
    config = {
        "collector": {
            "source": "federal_reserve_press_releases_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: xml_text,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["normalized_success_count"] == 0
    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["errors"][0]["message"] == "rss item pub_date is invalid"


def test_run_news_collector_records_missing_title_for_sec_source(tmp_path: Path) -> None:
    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <link>https://www.sec.gov/news/press-release/2026-50</link>
          <guid>2026-50</guid>
          <description>Statement on crypto and digital asset market oversight.</description>
          <pubDate>Tue, 24 Mar 2026 03:00:00 GMT</pubDate>
          <category>Enforcement</category>
        </item>
      </channel>
    </rss>
    """
    config = {
        "collector": {
            "source": "sec_press_releases_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: xml_text,
        now_fn=lambda: 1_774_000_000.0,
    )

    assert result["observation"]["validation_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["title"] == 1


def test_run_news_collector_preserves_duplicate_dedup_key_boundary_case(tmp_path: Path) -> None:
    duplicate_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Bitcoin rises as ETF flows improve</title>
          <link>https://www.coindesk.com/markets/bitcoin-rises</link>
          <guid>btc-1</guid>
          <description>Example</description>
          <pubDate>Tue, 24 Mar 2026 01:00:00 GMT</pubDate>
          <category>Markets</category>
        </item>
        <item>
          <title>Bitcoin rises as ETF flows improve</title>
          <link>https://www.coindesk.com/markets/bitcoin-rises</link>
          <guid>btc-1</guid>
          <description>Example</description>
          <pubDate>Tue, 24 Mar 2026 01:00:00 GMT</pubDate>
          <category>Markets</category>
        </item>
      </channel>
    </rss>
    """
    config = {
        "collector": {
            "source": "coindesk_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    result = run_news_collector(
        config,
        fetch_feed_fn=lambda feed_url, timeout_seconds: duplicate_xml,
        now_fn=lambda: 1_774_000_000.0,
    )

    dedup_keys = [record["dedup_key"] for record in result["bundle"]["records"]]
    assert result["observation"]["normalized_success_count"] == 2
    assert result["observation"]["duplicate_count"] == 1
    assert result["bundle"]["summary"]["duplicate_count"] == 1
    assert len(set(dedup_keys)) == 1


def test_run_news_collector_handles_fetch_failure(tmp_path: Path) -> None:
    config = {
        "collector": {
            "source": "coindesk_rss",
        },
        "output": {
            "output_dir": str(tmp_path / "var"),
        },
    }

    def raise_error(feed_url: str, timeout_seconds: int) -> str:
        raise NewsCollectorError("network blocked")

    result = run_news_collector(config, fetch_feed_fn=raise_error, now_fn=lambda: 1_774_000_000.0)

    assert result["observation"]["status"] == "failed"
    assert result["observation"]["errors"] == [{"message": "network blocked"}]


def test_news_collector_cli_prints_observation_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "collector.json"
    config_path.write_text(
        json.dumps(
            {
                "collector": {
                    "source": "federal_reserve_press_releases_rss",
                    "feed_url": FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL,
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

    def fake_run_news_collector(config: dict) -> dict:
        return {
            "bundle": {"records": []},
            "observation": {
                "status": "completed",
                "source": "federal_reserve_press_releases_rss",
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

    monkeypatch.setattr("trade_simulator.news_collector_cli.run_news_collector", fake_run_news_collector)

    exit_code = news_collector_main(["--config", str(config_path)])
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["status"] == "completed"
    assert captured["source"] == "federal_reserve_press_releases_rss"
