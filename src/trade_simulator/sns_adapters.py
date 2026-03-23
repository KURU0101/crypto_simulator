from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from trade_simulator.sns_signals import normalize_sns_signal_record


REDDIT_SUBREDDIT_NEW_JSON_URL = "https://www.reddit.com/r/CryptoCurrency/new.json"
YOUTUBE_CHANNEL_FEED_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
HACKER_NEWS_API_BASE_URL = "https://hacker-news.firebaseio.com/v0"
HACKER_NEWS_TOPSTORIES_URL = f"{HACKER_NEWS_API_BASE_URL}/topstories.json"
HACKER_NEWS_ITEM_URL_TEMPLATE = f"{HACKER_NEWS_API_BASE_URL}/item/{{item_id}}.json"

ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"
YOUTUBE_NAMESPACE = "{http://www.youtube.com/xml/schemas/2015}"

_POSITIVE_KEYWORDS = (
    "adoption",
    "approval",
    "bull",
    "breakout",
    "gain",
    "green",
    "high",
    "launch",
    "partnership",
    "rally",
    "surge",
    "up",
)
_NEGATIVE_KEYWORDS = (
    "ban",
    "bear",
    "crackdown",
    "crash",
    "down",
    "drop",
    "exploit",
    "hack",
    "lawsuit",
    "loss",
    "red",
)

_REDDIT_KEYWORD_RULES = (
    ("BTCUSDT", "bitcoin", ("bitcoin",), (" btc ",)),
    ("ETHUSDT", "ethereum", ("ethereum",), (" ether ", " eth ")),
    ("SOLUSDT", "solana", ("solana",), (" sol ",)),
    (None, "crypto macro", ("macro", "fed", "fomc"), ()),
    (None, "stablecoins", ("stablecoin",), ()),
    (None, "crypto regulation", ("regulation", "sec"), ()),
)
_YOUTUBE_KEYWORD_RULES = (
    ("BTCUSDT", "bitcoin", ("bitcoin",), (" btc ",)),
    ("ETHUSDT", "ethereum", ("ethereum",), (" ether ", " eth ")),
    ("SOLUSDT", "solana", ("solana",), (" sol ",)),
    (None, "artificial intelligence", ("artificial intelligence",), (" ai ",)),
    (None, "cloud infrastructure", ("cloud",), ()),
    (None, "crypto regulation", ("regulation", "policy"), ()),
)
_HACKER_NEWS_KEYWORD_RULES = (
    ("BTCUSDT", "bitcoin", ("bitcoin",), (" btc ",)),
    ("ETHUSDT", "ethereum", ("ethereum",), (" ether ", " eth ")),
    ("SOLUSDT", "solana", ("solana",), (" sol ",)),
    (None, "artificial intelligence", ("artificial intelligence",), (" ai ",)),
    (None, "cloud infrastructure", ("cloud",), ()),
    (None, "crypto regulation", ("regulation", "sec"), ()),
)


def _require_text(item: dict, field_name: str, *, prefix: str) -> str:
    value = item.get(field_name)
    if value is None or not str(value).strip():
        raise ValueError(f"{prefix} {field_name} is required")
    return str(value).strip()


def normalize_epoch_seconds_to_utc_z(value: object, *, prefix: str, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{prefix} {field_name} must be a number")
    if value < 0:
        raise ValueError(f"{prefix} {field_name} must be non-negative")
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def build_sns_dedup_key(
    *,
    source: str,
    timestamp: str,
    entity_key: str,
    source_id: str | None = None,
    post_id: str | None = None,
    permalink: str | None,
) -> str:
    locator_kind = "source_id"
    locator_value = (source_id or post_id or "").strip()
    if not locator_value:
        locator_kind = "permalink"
        locator_value = (permalink or "").strip().lower()
    seed = f"{source.lower()}|{timestamp}|{entity_key}|{locator_kind}|{locator_value}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{source.lower()}:{digest}"


def _score_text_sentiment(text: str) -> tuple[float, float, float]:
    lowered = f" {text.lower()} "
    positive_hits = sum(1 for keyword in _POSITIVE_KEYWORDS if keyword in lowered)
    negative_hits = sum(1 for keyword in _NEGATIVE_KEYWORDS if keyword in lowered)

    if positive_hits and not negative_hits:
        return (0.7, 0.1, 0.2)
    if negative_hits and not positive_hits:
        return (0.1, 0.7, 0.2)
    if positive_hits and negative_hits:
        return (0.4, 0.4, 0.2)
    return (0.2, 0.2, 0.6)


def _infer_symbol_topic_from_keyword_rules(
    text: str,
    *,
    fallback_topic: str,
    keyword_rules: tuple[tuple[str | None, str, tuple[str, ...], tuple[str, ...]], ...],
) -> dict:
    lowered = text.lower()
    padded = f" {lowered} "
    for symbol, topic, plain_keywords, padded_keywords in keyword_rules:
        if any(keyword in lowered for keyword in plain_keywords) or any(keyword in padded for keyword in padded_keywords):
            return {"symbol": symbol, "topic": topic}
    return {"symbol": None, "topic": fallback_topic}


def infer_reddit_symbol_topic(title: str, selftext: str, subreddit: str, link_flair_text: str | None) -> dict:
    text = " ".join(
        part for part in (title.lower(), selftext.lower(), subreddit.lower(), (link_flair_text or "").lower()) if part
    )
    normalized_subreddit = subreddit.replace("_", " ").strip().lower() or "crypto discussion"
    return _infer_symbol_topic_from_keyword_rules(text, fallback_topic=normalized_subreddit, keyword_rules=_REDDIT_KEYWORD_RULES)


def infer_youtube_symbol_topic(title: str, channel_label: str, group_label: str, group_theme: str, theme_tags: list[str]) -> dict:
    classifier_text = " ".join([title, channel_label, group_label, group_theme])
    fallback_topic = theme_tags[0] if theme_tags else group_theme
    return _infer_symbol_topic_from_keyword_rules(
        classifier_text,
        fallback_topic=fallback_topic,
        keyword_rules=_YOUTUBE_KEYWORD_RULES,
    )


def infer_hacker_news_symbol_topic(title: str, url: str | None, text: str | None, story_type: str) -> dict:
    classifier_text = " ".join(part for part in (title, url or "", text or "", story_type) if part)
    fallback_topic = "technology discussion"
    if story_type == "job":
        fallback_topic = "technology hiring"
    elif story_type == "poll":
        fallback_topic = "technology poll"
    return _infer_symbol_topic_from_keyword_rules(
        classifier_text,
        fallback_topic=fallback_topic,
        keyword_rules=_HACKER_NEWS_KEYWORD_RULES,
    )


def _score_reddit_activity(score: int, num_comments: int) -> float:
    activity = math.log1p(max(score, 0) + max(num_comments, 0)) / 6.0
    return min(1.0, max(0.0, activity))


def _score_reddit_anomaly(score: int, num_comments: int, upvote_ratio: float | None) -> float:
    skew = abs((upvote_ratio if upvote_ratio is not None else 0.5) - 0.5) * 2.0
    volume = math.log1p(max(abs(score), 0) + max(num_comments, 0)) / 10.0
    return min(1.0, max(0.0, skew + volume))


def adapt_reddit_post(item: dict, *, fetched_at: str, listing_url: str) -> dict:
    title = _require_text(item, "title", prefix="reddit item")
    subreddit = _require_text(item, "subreddit", prefix="reddit item")
    permalink = _require_text(item, "permalink", prefix="reddit item")
    timestamp = normalize_epoch_seconds_to_utc_z(item.get("created_utc"), prefix="reddit item", field_name="created_utc")
    selftext = str(item.get("selftext") or "").strip()
    link_flair_text = str(item.get("link_flair_text") or "").strip() or None

    num_comments_raw = item.get("num_comments")
    num_comments = int(num_comments_raw) if isinstance(num_comments_raw, int) and num_comments_raw >= 0 else 0
    score_raw = item.get("score")
    score = int(score_raw) if isinstance(score_raw, int) else 0
    upvote_ratio_raw = item.get("upvote_ratio")
    upvote_ratio = (
        float(upvote_ratio_raw)
        if isinstance(upvote_ratio_raw, (int, float)) and not isinstance(upvote_ratio_raw, bool)
        else None
    )

    classification = infer_reddit_symbol_topic(title, selftext, subreddit, link_flair_text)
    positive_score, negative_score, neutral_score = _score_text_sentiment(" ".join(part for part in (title, selftext) if part))
    entity_key = classification["symbol"] or classification["topic"]
    post_id = str(item.get("id") or "").strip() or None

    record = {
        "source": "reddit",
        "symbol": classification["symbol"],
        "topic": classification["topic"],
        "timestamp": timestamp,
        "mention_count": num_comments,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "neutral_score": neutral_score,
        "activity_score": _score_reddit_activity(score, num_comments),
        "anomaly_score": _score_reddit_anomaly(score, num_comments, upvote_ratio),
        "dedup_key": build_sns_dedup_key(
            source="reddit",
            timestamp=timestamp,
            entity_key=entity_key,
            source_id=post_id,
            permalink=permalink,
        ),
        "metadata": {
            "collector_source": "reddit_subreddit_new_json",
            "listing_url": listing_url,
            "fetched_at": fetched_at,
            "source_id": post_id,
            "permalink": permalink,
            "title": title,
            "subreddit": subreddit,
            "link_flair_text": link_flair_text,
            "score": score if score_raw is not None else None,
            "upvote_ratio": upvote_ratio,
            "author": str(item.get("author") or "").strip() or None,
            "mention_count_semantics": "reddit num_comments",
        },
    }
    return normalize_sns_signal_record(record, entry_name="reddit_subreddit_new_json_item")


def build_youtube_channel_feed_url(channel_id: str) -> str:
    normalized_channel_id = channel_id.strip()
    if not normalized_channel_id:
        raise ValueError("youtube channel_id must be a non-empty string")
    return YOUTUBE_CHANNEL_FEED_URL_TEMPLATE.format(channel_id=normalized_channel_id)


def build_hacker_news_item_url(item_id: int) -> str:
    return HACKER_NEWS_ITEM_URL_TEMPLATE.format(item_id=item_id)


def parse_youtube_feed_items(xml_text: str, *, max_items: int) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError("failed to parse YouTube RSS XML") from error

    items: list[dict] = []
    for entry in root.findall(f"{ATOM_NAMESPACE}entry")[:max_items]:
        link = entry.find(f"{ATOM_NAMESPACE}link")
        author = entry.find(f"{ATOM_NAMESPACE}author")
        items.append(
            {
                "video_id": entry.findtext(f"{YOUTUBE_NAMESPACE}videoId"),
                "channel_id": entry.findtext(f"{YOUTUBE_NAMESPACE}channelId"),
                "title": entry.findtext(f"{ATOM_NAMESPACE}title"),
                "published_at": entry.findtext(f"{ATOM_NAMESPACE}published"),
                "updated_at": entry.findtext(f"{ATOM_NAMESPACE}updated"),
                "video_url": link.get("href") if link is not None else None,
                "author_name": author.findtext(f"{ATOM_NAMESPACE}name") if author is not None else None,
            }
        )
    return items


def _youtube_activity_score(published_at: str, fetched_at: str) -> float:
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    age_hours = max(0.0, (fetched - published).total_seconds() / 3600.0)
    if age_hours <= 24:
        return 0.9
    if age_hours <= 72:
        return 0.75
    if age_hours <= 168:
        return 0.6
    return 0.4


def _youtube_anomaly_score(text: str, *, publisher_type: str, theme_tags: list[str], group_theme: str) -> float:
    base = 0.15
    if publisher_type in {"startup", "exchange", "government", "regulator"}:
        base += 0.15
    if theme_tags:
        base += min(0.2, 0.05 * len(theme_tags))
    if any(keyword in text.lower() for keyword in ("bitcoin", "ethereum", "ai", "policy", "regulation", "launch")):
        base += 0.2
    if "crypto" in group_theme.lower() or "financial" in group_theme.lower():
        base += 0.1
    return min(1.0, base)


def adapt_youtube_video(item: dict, *, fetched_at: str, channel_context: dict) -> dict:
    title = _require_text(item, "title", prefix="youtube feed item")
    video_id = _require_text(item, "video_id", prefix="youtube feed item")
    feed_channel_id = _require_text(item, "channel_id", prefix="youtube feed item")
    published_at = _require_text(item, "published_at", prefix="youtube feed item")
    video_url = _require_text(item, "video_url", prefix="youtube feed item")
    author_name = _require_text(item, "author_name", prefix="youtube feed item")

    configured_channel_id = channel_context["channel_id"]
    if feed_channel_id != configured_channel_id:
        raise ValueError("youtube feed item channel_id does not match configured channel_id")

    theme_tags = [str(tag).strip() for tag in channel_context.get("theme_tags", []) if str(tag).strip()]
    anomaly_text = " ".join([title, channel_context["channel_label"], channel_context["group_label"], channel_context["group_theme"], " ".join(theme_tags)])
    classification = infer_youtube_symbol_topic(
        title,
        channel_context["channel_label"],
        channel_context["group_label"],
        channel_context["group_theme"],
        theme_tags,
    )
    positive_score, negative_score, neutral_score = _score_text_sentiment(title)
    publisher_type = channel_context["publisher_type"]

    record = {
        "source": "youtube",
        "symbol": classification["symbol"],
        "topic": classification["topic"],
        "timestamp": published_at,
        "mention_count": 1,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "neutral_score": neutral_score,
        "activity_score": _youtube_activity_score(published_at, fetched_at),
        "anomaly_score": _youtube_anomaly_score(
            anomaly_text,
            publisher_type=publisher_type,
            theme_tags=theme_tags,
            group_theme=channel_context["group_theme"],
        ),
        "dedup_key": build_sns_dedup_key(
            source="youtube",
            timestamp=published_at,
            entity_key=classification["symbol"] or classification["topic"],
            source_id=video_id,
            permalink=video_url,
        ),
        "metadata": {
            "collector_source": "youtube_channel_rss",
            "fetched_at": fetched_at,
            "source_id": video_id,
            "permalink": video_url,
            "title": title,
            "author_name": author_name,
            "group_id": channel_context["group_id"],
            "group_label": channel_context["group_label"],
            "group_theme": channel_context["group_theme"],
            "group_publisher_type": channel_context["group_publisher_type"],
            "publisher_type": publisher_type,
            "channel_id": configured_channel_id,
            "channel_label": channel_context["channel_label"],
            "theme_tags": theme_tags,
            "feed_url": channel_context["feed_url"],
            "updated_at": item.get("updated_at"),
            "mention_count_semantics": "youtube upload count fixed at 1 per video",
        },
    }
    return normalize_sns_signal_record(record, entry_name="youtube_channel_rss_item")


def _hacker_news_activity_score(score: int, descendants: int) -> float:
    activity = math.log1p(max(score, 0) + max(descendants, 0)) / 7.0
    return min(1.0, max(0.0, activity))


def _hacker_news_anomaly_score(title: str, score: int, descendants: int, story_type: str) -> float:
    base = min(0.6, math.log1p(max(score, 0)) / 10.0 + math.log1p(max(descendants, 0)) / 10.0)
    if story_type in {"job", "poll"}:
        base += 0.1
    if any(keyword in title.lower() for keyword in ("launch", "release", "funding", "acquire", "regulation", "bitcoin", "ai")):
        base += 0.2
    return min(1.0, max(0.0, base))


def adapt_hacker_news_story(item: dict, *, fetched_at: str, list_name: str, item_url: str) -> dict:
    title = _require_text(item, "title", prefix="hacker news item")
    item_id_raw = item.get("id")
    if isinstance(item_id_raw, bool) or not isinstance(item_id_raw, int):
        raise TypeError("hacker news item id must be an int")
    story_type = _require_text(item, "type", prefix="hacker news item")
    timestamp = normalize_epoch_seconds_to_utc_z(item.get("time"), prefix="hacker news item", field_name="time")
    score_raw = item.get("score")
    score = int(score_raw) if isinstance(score_raw, int) else 0
    descendants_raw = item.get("descendants")
    descendants = int(descendants_raw) if isinstance(descendants_raw, int) else 0
    url = str(item.get("url") or "").strip() or None
    text = str(item.get("text") or "").strip() or None
    author = str(item.get("by") or "").strip() or None

    classification = infer_hacker_news_symbol_topic(title, url, text, story_type)
    positive_score, negative_score, neutral_score = _score_text_sentiment(" ".join(part for part in (title, text or "") if part))
    entity_key = classification["symbol"] or classification["topic"]

    record = {
        "source": "hacker_news",
        "symbol": classification["symbol"],
        "topic": classification["topic"],
        "timestamp": timestamp,
        "mention_count": descendants,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "neutral_score": neutral_score,
        "activity_score": _hacker_news_activity_score(score, descendants),
        "anomaly_score": _hacker_news_anomaly_score(title, score, descendants, story_type),
        "dedup_key": build_sns_dedup_key(
            source="hacker_news",
            timestamp=timestamp,
            entity_key=entity_key,
            source_id=str(item_id_raw),
            permalink=url or item_url,
        ),
        "metadata": {
            "collector_source": "hacker_news_public_api",
            "fetched_at": fetched_at,
            "source_id": str(item_id_raw),
            "permalink": url,
            "title": title,
            "author": author,
            "score": score if score_raw is not None else None,
            "descendants": descendants if descendants_raw is not None else None,
            "story_type": story_type,
            "list_name": list_name,
            "item_url": item_url,
            "url": url,
            "mention_count_semantics": "hacker news descendants comment count",
        },
    }
    return normalize_sns_signal_record(record, entry_name="hacker_news_public_api_item")


SNS_SOURCE_PROFILES = {
    "reddit_subreddit_new_json": {
        "kind": "reddit",
        "default_listing_url": REDDIT_SUBREDDIT_NEW_JSON_URL,
        "required_item_fields": ("id", "title", "subreddit", "permalink", "created_utc"),
        "tracked_optional_item_fields": ("num_comments", "score", "upvote_ratio", "link_flair_text"),
        "adapter": adapt_reddit_post,
    },
    "youtube_channel_rss": {
        "kind": "youtube",
        "required_item_fields": ("video_id", "channel_id", "title", "published_at", "video_url", "author_name"),
        "tracked_optional_item_fields": ("updated_at",),
        "adapter": adapt_youtube_video,
    },
    "hacker_news_public_api": {
        "kind": "hacker_news",
        "default_list_url": HACKER_NEWS_TOPSTORIES_URL,
        "default_item_url_template": HACKER_NEWS_ITEM_URL_TEMPLATE,
        "required_item_fields": ("id", "title", "type", "time"),
        "tracked_optional_item_fields": ("score", "descendants", "url", "by"),
        "adapter": adapt_hacker_news_story,
    },
}


__all__ = [
    "HACKER_NEWS_API_BASE_URL",
    "HACKER_NEWS_ITEM_URL_TEMPLATE",
    "HACKER_NEWS_TOPSTORIES_URL",
    "REDDIT_SUBREDDIT_NEW_JSON_URL",
    "SNS_SOURCE_PROFILES",
    "YOUTUBE_CHANNEL_FEED_URL_TEMPLATE",
    "adapt_hacker_news_story",
    "adapt_reddit_post",
    "adapt_youtube_video",
    "build_sns_dedup_key",
    "build_hacker_news_item_url",
    "build_youtube_channel_feed_url",
    "infer_hacker_news_symbol_topic",
    "infer_reddit_symbol_topic",
    "infer_youtube_symbol_topic",
    "normalize_epoch_seconds_to_utc_z",
    "parse_youtube_feed_items",
]
