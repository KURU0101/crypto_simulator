from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from trade_simulator.sns_signals import normalize_sns_signal_record


REDDIT_SUBREDDIT_NEW_JSON_URL = "https://www.reddit.com/r/CryptoCurrency/new.json"

_POSITIVE_KEYWORDS = (
    "bull",
    "breakout",
    "gain",
    "green",
    "high",
    "rally",
    "surge",
    "up",
)
_NEGATIVE_KEYWORDS = (
    "ban",
    "bear",
    "crash",
    "down",
    "drop",
    "exploit",
    "hack",
    "lawsuit",
    "loss",
    "red",
)


def _require_reddit_text(item: dict, field_name: str) -> str:
    value = item.get(field_name)
    if value is None or not str(value).strip():
        raise ValueError(f"reddit item {field_name} is required")
    return str(value).strip()


def normalize_reddit_created_utc(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("reddit item created_utc must be a number")
    if value < 0:
        raise ValueError("reddit item created_utc must be non-negative")
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def build_sns_dedup_key(
    *,
    source: str,
    timestamp: str,
    entity_key: str,
    post_id: str | None,
    permalink: str | None,
) -> str:
    locator_kind = "source_id"
    locator_value = (post_id or "").strip()
    if not locator_value:
        locator_kind = "permalink"
        locator_value = (permalink or "").strip().lower()
    seed = f"{source.lower()}|{timestamp}|{entity_key}|{locator_kind}|{locator_value}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{source.lower()}:{digest}"


def _classify_reddit_post(title: str, selftext: str, subreddit: str, link_flair_text: str | None) -> dict:
    text = " ".join(part for part in (title.lower(), selftext.lower(), subreddit.lower(), (link_flair_text or "").lower()) if part)
    padded_text = f" {text} "

    if "bitcoin" in text or " btc " in padded_text:
        return {"symbol": "BTCUSDT", "topic": "bitcoin"}
    if "ethereum" in text or " ether " in padded_text or " eth " in padded_text:
        return {"symbol": "ETHUSDT", "topic": "ethereum"}
    if "etf" in text:
        return {"symbol": None, "topic": "crypto etf"}
    if "regulation" in text or "sec" in text:
        return {"symbol": None, "topic": "crypto regulation"}
    if "stablecoin" in text:
        return {"symbol": None, "topic": "stablecoins"}
    if "macro" in text or "fed" in text or "fomc" in text:
        return {"symbol": None, "topic": "crypto macro"}

    normalized_subreddit = subreddit.replace("_", " ").strip().lower()
    return {"symbol": None, "topic": normalized_subreddit or "crypto discussion"}


def _score_reddit_sentiment(text: str) -> tuple[float, float, float]:
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


def _score_reddit_activity(score: int, num_comments: int) -> float:
    activity = math.log1p(max(score, 0) + max(num_comments, 0)) / 6.0
    return min(1.0, max(0.0, activity))


def _score_reddit_anomaly(score: int, num_comments: int, upvote_ratio: float | None) -> float:
    skew = abs((upvote_ratio if upvote_ratio is not None else 0.5) - 0.5) * 2.0
    volume = math.log1p(max(abs(score), 0) + max(num_comments, 0)) / 10.0
    return min(1.0, max(0.0, skew + volume))


def adapt_reddit_post(item: dict, *, fetched_at: str, listing_url: str) -> dict:
    title = _require_reddit_text(item, "title")
    subreddit = _require_reddit_text(item, "subreddit")
    permalink = _require_reddit_text(item, "permalink")
    timestamp = normalize_reddit_created_utc(item.get("created_utc"))
    selftext = str(item.get("selftext") or "").strip()
    link_flair_text = str(item.get("link_flair_text") or "").strip() or None

    num_comments_raw = item.get("num_comments")
    num_comments = int(num_comments_raw) if isinstance(num_comments_raw, int) and num_comments_raw >= 0 else 0
    score_raw = item.get("score")
    score = int(score_raw) if isinstance(score_raw, int) else 0
    upvote_ratio_raw = item.get("upvote_ratio")
    upvote_ratio = float(upvote_ratio_raw) if isinstance(upvote_ratio_raw, (int, float)) and not isinstance(upvote_ratio_raw, bool) else None

    classification = _classify_reddit_post(title, selftext, subreddit, link_flair_text)
    positive_score, negative_score, neutral_score = _score_reddit_sentiment(" ".join(part for part in (title, selftext) if part))
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
            post_id=post_id,
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
        },
    }
    return normalize_sns_signal_record(record, entry_name="reddit_subreddit_new_json_item")


SNS_SOURCE_PROFILES = {
    "reddit_subreddit_new_json": {
        "default_listing_url": REDDIT_SUBREDDIT_NEW_JSON_URL,
        "required_item_fields": ("id", "title", "subreddit", "permalink", "created_utc"),
        "tracked_optional_item_fields": ("num_comments", "score", "upvote_ratio", "link_flair_text"),
        "adapter": adapt_reddit_post,
    },
}


__all__ = [
    "REDDIT_SUBREDDIT_NEW_JSON_URL",
    "SNS_SOURCE_PROFILES",
    "adapt_reddit_post",
    "build_sns_dedup_key",
    "normalize_reddit_created_utc",
]
