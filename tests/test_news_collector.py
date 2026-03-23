from __future__ import annotations

import json
from pathlib import Path

from trade_simulator.news_collector import (
    COINDESK_RSS_FEED_URL,
    NewsCollectorError,
    adapt_coindesk_rss_item,
    load_news_collector_config,
    parse_coindesk_rss_items,
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


def test_load_news_collector_config_defaults_feed_url() -> None:
    config = load_news_collector_config(
        {
            "collector": {
                "source": "coindesk_rss",
            },
            "output": {
                "output_dir": "var/news_signals",
            },
        }
    )

    assert config["collector"]["feed_url"] == COINDESK_RSS_FEED_URL
    assert config["collector"]["max_items"] == 50


def test_parse_coindesk_rss_items_respects_max_items() -> None:
    items = parse_coindesk_rss_items(RSS_TWO_ITEMS, max_items=1)

    assert len(items) == 1
    assert items[0]["title"] == "Bitcoin rises as ETF flows improve"


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
    assert record["metadata"]["collector_source"] == "coindesk_rss"


def test_run_news_collector_collects_normalized_records_and_saves_them(tmp_path: Path) -> None:
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
    assert observation["fetched_item_count"] == 2
    assert observation["normalized_success_count"] == 2
    assert observation["normalized_failure_count"] == 0
    assert observation["saved_record_count"] == 2
    assert observation["symbol_distribution"] == {"BTCUSDT": 1}
    assert observation["topic_distribution"]["bitcoin"] == 1
    assert observation["topic_distribution"]["policy"] == 1
    assert Path(observation["saved_paths"]["normalized"]).exists()
    assert Path(observation["saved_paths"]["summary"]).exists()

    saved_bundle = json.loads(Path(observation["saved_paths"]["normalized"]).read_text(encoding="utf-8"))
    assert saved_bundle["summary"]["record_count"] == 2


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


def test_run_news_collector_records_normalization_failures(tmp_path: Path) -> None:
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
    assert result["observation"]["normalized_failure_count"] == 1
    assert result["observation"]["missing_field_counts"]["link"] == 1


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
                    "source": "coindesk_rss",
                    "feed_url": COINDESK_RSS_FEED_URL,
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
                "source": "coindesk_rss",
                "fetched_item_count": 0,
                "normalized_success_count": 0,
                "normalized_failure_count": 0,
                "saved_record_count": 0,
                "errors": [],
                "saved_paths": {},
            },
        }

    monkeypatch.setattr("trade_simulator.news_collector_cli.run_news_collector", fake_run_news_collector)

    exit_code = news_collector_main(["--config", str(config_path)])
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["status"] == "completed"
    assert captured["source"] == "coindesk_rss"
