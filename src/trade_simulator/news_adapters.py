from __future__ import annotations

import hashlib
from datetime import timezone
from email.utils import parsedate_to_datetime

from trade_simulator.news_signals import normalize_news_signal_record


COINDESK_RSS_FEED_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"
FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
SEC_PRESS_RELEASES_RSS_FEED_URL = "https://www.sec.gov/news/pressreleases.rss"


def _require_rss_text(item: dict, field_name: str) -> str:
    value = item.get(field_name)
    if value is None or not str(value).strip():
        raise ValueError(f"rss item {field_name} is required")
    return str(value).strip()


def normalize_rss_pub_date(pub_date: str) -> str:
    try:
        parsed = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError) as error:
        raise ValueError("rss item pub_date is invalid") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_news_dedup_seed(
    *,
    source: str,
    published_at: str,
    headline: str | None,
    source_id: str | None,
    url: str | None,
) -> str:
    normalized_headline = " ".join((headline or "").strip().lower().split())
    locator_kind = "source_id"
    locator_value = (source_id or "").strip()
    if not locator_value:
        locator_kind = "url"
        locator_value = (url or "").strip().lower()
    if not locator_value:
        locator_kind = "headline"
        locator_value = normalized_headline
    return f"{source.lower()}|{published_at}|{locator_kind}|{locator_value}|{normalized_headline}"


def build_news_dedup_key(
    *,
    source: str,
    published_at: str,
    headline: str | None,
    source_id: str | None,
    url: str | None,
) -> str:
    seed = _build_news_dedup_seed(
        source=source,
        published_at=published_at,
        headline=headline,
        source_id=source_id,
        url=url,
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{source.lower()}:{digest}"


def _classify_coindesk_item(title: str, categories: list[str]) -> dict:
    lowered_title = title.lower()
    lowered_categories = " ".join(category.lower() for category in categories)
    text = f"{lowered_title} {lowered_categories}".strip()

    if "bitcoin" in text or "btc" in text:
        return {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "topic": "bitcoin",
            "relevance_score": 0.9,
            "impact_score": 0.7,
        }
    if "ethereum" in text or "ether" in text or "eth" in text:
        return {
            "symbol": "ETHUSDT",
            "asset": "ETH",
            "topic": "ethereum",
            "relevance_score": 0.85,
            "impact_score": 0.65,
        }

    topic = categories[0].strip().lower() if categories else "crypto news"
    return {
        "symbol": None,
        "asset": None,
        "topic": topic,
        "relevance_score": 0.5,
        "impact_score": 0.4,
    }


def _classify_sec_press_release_item(title: str, description: str, categories: list[str]) -> dict:
    lowered_title = title.lower()
    lowered_description = description.lower()
    lowered_categories = " ".join(category.lower() for category in categories)
    text = f"{lowered_title} {lowered_description} {lowered_categories}".strip()

    if "bitcoin" in text or "btc" in text:
        return {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "topic": "bitcoin regulation",
            "relevance_score": 0.85,
            "impact_score": 0.85,
        }
    if "ethereum" in text or "ether" in text or "eth" in text:
        return {
            "symbol": "ETHUSDT",
            "asset": "ETH",
            "topic": "ethereum regulation",
            "relevance_score": 0.8,
            "impact_score": 0.8,
        }
    if any(keyword in text for keyword in ("crypto", "digital asset", "blockchain", "stablecoin", "token")):
        return {
            "symbol": None,
            "asset": None,
            "topic": "crypto regulation",
            "relevance_score": 0.75,
            "impact_score": 0.85,
        }

    category = categories[0].strip().lower() if categories else "press release"
    return {
        "symbol": None,
        "asset": None,
        "topic": f"sec {category}",
        "relevance_score": 0.3,
        "impact_score": 0.4,
    }


def _classify_federal_reserve_press_release_item(title: str, description: str, categories: list[str]) -> dict:
    lowered_title = title.lower()
    lowered_description = description.lower()
    lowered_categories = " ".join(category.lower() for category in categories)
    text = f"{lowered_title} {lowered_description} {lowered_categories}".strip()

    if "bitcoin" in text or "btc" in text:
        return {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "topic": "bitcoin macro policy",
            "relevance_score": 0.75,
            "impact_score": 0.8,
        }
    if "ethereum" in text or "ether" in text or "eth" in text:
        return {
            "symbol": "ETHUSDT",
            "asset": "ETH",
            "topic": "ethereum macro policy",
            "relevance_score": 0.7,
            "impact_score": 0.75,
        }
    if any(keyword in text for keyword in ("crypto", "digital asset", "stablecoin", "token", "blockchain")):
        return {
            "symbol": None,
            "asset": None,
            "topic": "crypto macro policy",
            "relevance_score": 0.65,
            "impact_score": 0.8,
        }

    category = categories[0].strip().lower() if categories else "press release"
    if "monetary" in category:
        topic = "monetary policy"
        relevance_score = 0.7
        impact_score = 0.9
    elif "bank" in category or "regulatory" in category:
        topic = "bank regulation"
        relevance_score = 0.55
        impact_score = 0.7
    elif "enforcement" in category:
        topic = "bank enforcement"
        relevance_score = 0.45
        impact_score = 0.65
    else:
        topic = f"federal reserve {category}"
        relevance_score = 0.3
        impact_score = 0.45

    return {
        "symbol": None,
        "asset": None,
        "topic": topic,
        "relevance_score": relevance_score,
        "impact_score": impact_score,
    }


def adapt_coindesk_rss_item(item: dict, *, fetched_at: str, feed_url: str) -> dict:
    title = _require_rss_text(item, "title")
    link = _require_rss_text(item, "link")
    pub_date = normalize_rss_pub_date(_require_rss_text(item, "pub_date"))
    categories = [str(category).strip() for category in item.get("categories", []) if str(category).strip()]
    classification = _classify_coindesk_item(title, categories)

    category = categories[0] if categories else "news"
    source_id = item.get("guid")
    record = {
        "source": "coindesk",
        "symbol": classification["symbol"],
        "asset": classification["asset"],
        "topic": classification["topic"],
        "published_at": pub_date,
        "headline": title,
        "url": link,
        "source_id": source_id,
        "dedup_key": build_news_dedup_key(
            source="coindesk",
            published_at=pub_date,
            headline=title,
            source_id=source_id,
            url=link,
        ),
        "relevance_score": classification["relevance_score"],
        "sentiment_score": 0.0,
        "impact_score": classification["impact_score"],
        "category": category,
        "metadata": {
            "collector_source": "coindesk_rss",
            "feed_url": feed_url,
            "fetched_at": fetched_at,
            "categories": categories,
            "description": item.get("description"),
        },
    }
    return normalize_news_signal_record(record, entry_name="coindesk_rss_item")


def adapt_sec_press_release_rss_item(item: dict, *, fetched_at: str, feed_url: str) -> dict:
    title = _require_rss_text(item, "title")
    link = _require_rss_text(item, "link")
    description = str(item.get("description") or "").strip()
    pub_date = normalize_rss_pub_date(_require_rss_text(item, "pub_date"))
    categories = [str(category).strip() for category in item.get("categories", []) if str(category).strip()]
    classification = _classify_sec_press_release_item(title, description, categories)

    category = categories[0] if categories else "press release"
    source_id = item.get("guid") or link.rstrip("/").rsplit("/", maxsplit=1)[-1]
    record = {
        "source": "sec",
        "symbol": classification["symbol"],
        "asset": classification["asset"],
        "topic": classification["topic"],
        "published_at": pub_date,
        "headline": title,
        "url": link,
        "source_id": source_id,
        "dedup_key": build_news_dedup_key(
            source="sec",
            published_at=pub_date,
            headline=title,
            source_id=source_id,
            url=link,
        ),
        "relevance_score": classification["relevance_score"],
        "sentiment_score": -0.1 if classification["topic"].endswith("regulation") else 0.0,
        "impact_score": classification["impact_score"],
        "category": category,
        "metadata": {
            "collector_source": "sec_press_releases_rss",
            "feed_url": feed_url,
            "fetched_at": fetched_at,
            "categories": categories,
            "description": description or None,
        },
    }
    return normalize_news_signal_record(record, entry_name="sec_press_releases_rss_item")


def adapt_federal_reserve_press_release_rss_item(item: dict, *, fetched_at: str, feed_url: str) -> dict:
    title = _require_rss_text(item, "title")
    link = _require_rss_text(item, "link")
    description = str(item.get("description") or "").strip()
    pub_date = normalize_rss_pub_date(_require_rss_text(item, "pub_date"))
    categories = [str(category).strip() for category in item.get("categories", []) if str(category).strip()]
    classification = _classify_federal_reserve_press_release_item(title, description, categories)

    category = categories[0] if categories else "press release"
    source_id = item.get("guid") or link.rstrip("/").rsplit("/", maxsplit=1)[-1]
    record = {
        "source": "federal_reserve",
        "symbol": classification["symbol"],
        "asset": classification["asset"],
        "topic": classification["topic"],
        "published_at": pub_date,
        "headline": title,
        "url": link,
        "source_id": source_id,
        "dedup_key": build_news_dedup_key(
            source="federal_reserve",
            published_at=pub_date,
            headline=title,
            source_id=source_id,
            url=link,
        ),
        "relevance_score": classification["relevance_score"],
        "sentiment_score": 0.0,
        "impact_score": classification["impact_score"],
        "category": category,
        "metadata": {
            "collector_source": "federal_reserve_press_releases_rss",
            "feed_url": feed_url,
            "fetched_at": fetched_at,
            "categories": categories,
            "description": description or None,
        },
    }
    return normalize_news_signal_record(record, entry_name="federal_reserve_press_releases_rss_item")


NEWS_SOURCE_PROFILES = {
    "coindesk_rss": {
        "default_feed_url": COINDESK_RSS_FEED_URL,
        "required_item_fields": ("title", "link", "pub_date"),
        "adapter": adapt_coindesk_rss_item,
    },
    "sec_press_releases_rss": {
        "default_feed_url": SEC_PRESS_RELEASES_RSS_FEED_URL,
        "required_item_fields": ("title", "link", "pub_date"),
        "adapter": adapt_sec_press_release_rss_item,
    },
    "federal_reserve_press_releases_rss": {
        "default_feed_url": FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL,
        "required_item_fields": ("title", "link", "pub_date"),
        "adapter": adapt_federal_reserve_press_release_rss_item,
    },
}


__all__ = [
    "COINDESK_RSS_FEED_URL",
    "FEDERAL_RESERVE_PRESS_RELEASES_RSS_FEED_URL",
    "NEWS_SOURCE_PROFILES",
    "SEC_PRESS_RELEASES_RSS_FEED_URL",
    "adapt_coindesk_rss_item",
    "adapt_federal_reserve_press_release_rss_item",
    "adapt_sec_press_release_rss_item",
    "build_news_dedup_key",
    "normalize_rss_pub_date",
]
