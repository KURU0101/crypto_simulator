from __future__ import annotations

import json
from pathlib import Path

from trade_simulator.integrated_observer import (
    COMMON_DISTRIBUTION_FIELDS,
    COUNT_FIELDS,
    LEGACY_SOURCE_SPECIFIC_TOP_LEVEL_FIELDS,
    REQUIRED_SUMMARY_FIELDS,
    build_integrated_summary_report,
    scan_saved_signal_summaries,
)
from trade_simulator.integrated_observer_cli import format_integrated_summary_report, main as integrated_observer_main


def test_scan_saved_signal_summaries_reads_news_and_sns_runs(tmp_path: Path) -> None:
    news_summary = _build_summary(
        signal_type="news",
        source="coindesk_rss",
        run_id="20260324T010000Z",
        started_at="2026-03-24T01:00:00Z",
        ended_at="2026-03-24T01:00:05Z",
        fetched_item_count=2,
        normalized_success_count=2,
        saved_record_count=2,
        source_specific={"feed_url": "https://example.invalid/feed.xml"},
        symbol_distribution={"BTCUSDT": 1},
        topic_distribution={"bitcoin": 1, "policy": 1},
    )
    sns_summary = _build_summary(
        signal_type="sns",
        source="reddit_subreddit_new_json",
        run_id="20260324T020000Z",
        started_at="2026-03-24T02:00:00Z",
        ended_at="2026-03-24T02:00:06Z",
        status="failed",
        fetched_item_count=3,
        normalized_success_count=1,
        validation_failure_count=1,
        saved_record_count=1,
        warnings=["partial failure"],
        errors=[{"message": "adapter failed"}],
        source_specific={"listing_url": "https://example.invalid/listing.json"},
        symbol_distribution={},
        topic_distribution={"crypto macro": 1},
    )

    _write_summary(tmp_path, "news", "coindesk_rss", "20260324T010000Z", news_summary)
    _write_summary(tmp_path, "sns", "reddit_subreddit_new_json", "20260324T020000Z", sns_summary)

    entries = scan_saved_signal_summaries(tmp_path)

    assert len(entries) == 2
    news_entry = next(entry for entry in entries if entry["signal_type"] == "news")
    sns_entry = next(entry for entry in entries if entry["signal_type"] == "sns")

    assert news_entry["status"] == "completed"
    assert news_entry["symbol_distribution_overview"] == "BTCUSDT:1"
    assert news_entry["topic_distribution_overview"] == "bitcoin:1, policy:1"
    assert news_entry["warning_count"] == 0
    assert news_entry["error_count"] == 0
    assert news_entry["has_source_specific"] is True

    assert sns_entry["status"] == "failed"
    assert sns_entry["warning_count"] == 1
    assert sns_entry["error_count"] == 1
    assert sns_entry["has_source_specific"] is True
    assert sns_entry["source_specific"]["listing_url"] == "https://example.invalid/listing.json"


def test_scan_saved_signal_summaries_marks_missing_broken_and_incomplete_runs(tmp_path: Path) -> None:
    missing_run_dir = tmp_path / "news_signals" / "sec_press_releases_rss" / "20260324T030000Z"
    missing_run_dir.mkdir(parents=True)

    broken_run_dir = tmp_path / "sns_signals" / "youtube_channel_rss" / "20260324T040000Z"
    broken_run_dir.mkdir(parents=True)
    (broken_run_dir / "summary.json").write_text("{broken", encoding="utf-8")

    incomplete_summary = {
        "signal_type": "news",
        "source": "federal_reserve_press_releases_rss",
        "status": "completed",
        "saved_paths": {"normalized": "/tmp/normalized.json"},
    }
    _write_summary(
        tmp_path,
        "news",
        "federal_reserve_press_releases_rss",
        "20260324T050000Z",
        incomplete_summary,
    )

    entries = scan_saved_signal_summaries(tmp_path)

    missing_entry = next(entry for entry in entries if entry["run_id"] == "20260324T030000Z")
    broken_entry = next(entry for entry in entries if entry["run_id"] == "20260324T040000Z")
    incomplete_entry = next(entry for entry in entries if entry["run_id"] == "20260324T050000Z")

    assert missing_entry["status"] == "missing_summary"
    assert missing_entry["error_count"] == 1

    assert broken_entry["status"] == "invalid_summary"
    assert broken_entry["error_count"] == 1

    assert incomplete_entry["status"] == "completed"
    assert incomplete_entry["missing_required_fields"] == ["started_at", "ended_at"]
    assert incomplete_entry["has_source_specific"] is False
    assert incomplete_entry["topic_distribution"] == {}
    assert incomplete_entry["symbol_distribution"] == {}


def test_scan_saved_signal_summaries_reads_only_common_fields_when_legacy_top_level_source_fields_exist(tmp_path: Path) -> None:
    legacy_only_summary = _build_summary(
        signal_type="news",
        source="coindesk_rss",
        run_id="20260324T060000Z",
        started_at="2026-03-24T06:00:00Z",
        ended_at="2026-03-24T06:00:05Z",
        topic_distribution={"bitcoin": 1},
    )
    legacy_only_summary.pop("source_specific")
    legacy_only_summary["feed_url"] = "https://example.invalid/feed.xml"

    _write_summary(tmp_path, "news", "coindesk_rss", "20260324T060000Z", legacy_only_summary)

    entries = scan_saved_signal_summaries(tmp_path)
    entry = next(item for item in entries if item["run_id"] == "20260324T060000Z")

    assert entry["status"] == "completed"
    assert entry["has_source_specific"] is False
    assert entry["source_specific"] == {}
    assert entry["topic_distribution"] == {"bitcoin": 1}


def test_integrated_observer_exports_common_summary_schema_constants() -> None:
    assert REQUIRED_SUMMARY_FIELDS == ("signal_type", "source", "run_id", "started_at", "ended_at", "status")
    assert COMMON_DISTRIBUTION_FIELDS == ("topic_distribution", "symbol_distribution")
    assert COUNT_FIELDS == (
        "fetched_item_count",
        "normalized_success_count",
        "validation_failure_count",
        "saved_record_count",
        "duplicate_count",
    )
    assert "feed_url" in LEGACY_SOURCE_SPECIFIC_TOP_LEVEL_FIELDS
    assert "listing_url" in LEGACY_SOURCE_SPECIFIC_TOP_LEVEL_FIELDS


def test_build_integrated_summary_report_supports_latest_only_and_grouping(tmp_path: Path) -> None:
    _write_summary(
        tmp_path,
        "news",
        "coindesk_rss",
        "20260324T010000Z",
        _build_summary(
            signal_type="news",
            source="coindesk_rss",
            run_id="20260324T010000Z",
            started_at="2026-03-24T01:00:00Z",
            ended_at="2026-03-24T01:00:05Z",
            topic_distribution={"bitcoin": 1},
        ),
    )
    _write_summary(
        tmp_path,
        "news",
        "coindesk_rss",
        "20260324T020000Z",
        _build_summary(
            signal_type="news",
            source="coindesk_rss",
            run_id="20260324T020000Z",
            started_at="2026-03-24T02:00:00Z",
            ended_at="2026-03-24T02:00:05Z",
            topic_distribution={"policy": 1},
        ),
    )
    _write_summary(
        tmp_path,
        "sns",
        "reddit_subreddit_new_json",
        "20260324T021500Z",
        _build_summary(
            signal_type="sns",
            source="reddit_subreddit_new_json",
            run_id="20260324T021500Z",
            started_at="2026-03-24T02:15:00Z",
            ended_at="2026-03-24T02:15:04Z",
            warnings=["warning only"],
        ),
    )

    entries = scan_saved_signal_summaries(tmp_path)
    report = build_integrated_summary_report(entries, latest_only=True, group_by="source")

    assert report["totals"]["run_count"] == 2
    assert [group["key"] for group in report["groups"]] == ["news:coindesk_rss", "sns:reddit_subreddit_new_json"]
    latest_news = next(run for run in report["runs"] if run["signal_type"] == "news")
    assert latest_news["run_id"] == "20260324T020000Z"


def test_build_integrated_summary_report_handles_zero_entries_boundary_case() -> None:
    report = build_integrated_summary_report([], group_by="overall")

    assert report["totals"]["run_count"] == 0
    assert report["groups"] == [{"key": "all", "totals": report["totals"], "runs": []}]
    assert format_integrated_summary_report(report, output_format="condensed").endswith("runs: none")


def test_integrated_observer_main_prints_json_report_for_filtered_latest_runs(
    tmp_path: Path,
    capsys,
) -> None:
    _write_summary(
        tmp_path,
        "sns",
        "hacker_news_public_api",
        "20260324T010000Z",
        _build_summary(
            signal_type="sns",
            source="hacker_news_public_api",
            run_id="20260324T010000Z",
            started_at="2026-03-24T01:00:00Z",
            ended_at="2026-03-24T01:00:03Z",
            warnings=["warning only"],
        ),
    )

    exit_code = integrated_observer_main(
        [
            "--root-dir",
            str(tmp_path),
            "--signal-type",
            "sns",
            "--group-by",
            "signal_type",
            "--latest-only",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["filters"]["signal_type"] == "sns"
    assert payload["filters"]["latest_only"] is True
    assert payload["totals"]["run_count"] == 1
    assert payload["groups"][0]["key"] == "sns"
    assert payload["groups"][0]["runs"][0]["warnings"] == ["warning only"]


def _write_summary(root_dir: Path, signal_type: str, source: str, run_id: str, payload: dict) -> None:
    summary_path = root_dir / f"{signal_type}_signals" / source / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_summary(
    *,
    signal_type: str,
    source: str,
    run_id: str,
    started_at: str,
    ended_at: str,
    status: str = "completed",
    fetched_item_count: int = 0,
    normalized_success_count: int = 0,
    validation_failure_count: int = 0,
    saved_record_count: int = 0,
    duplicate_count: int = 0,
    warnings: list[str] | None = None,
    errors: list[dict] | None = None,
    source_specific: dict | None = None,
    symbol_distribution: dict[str, int] | None = None,
    topic_distribution: dict[str, int] | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "signal_type": signal_type,
        "source": source,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "fetched_item_count": fetched_item_count,
        "normalized_success_count": normalized_success_count,
        "validation_failure_count": validation_failure_count,
        "saved_record_count": saved_record_count,
        "duplicate_count": duplicate_count,
        "warnings": warnings or [],
        "errors": errors or [],
        "saved_paths": {
            "normalized": f"/tmp/{signal_type}/{source}/{run_id}/normalized.json",
            "summary": f"/tmp/{signal_type}/{source}/{run_id}/summary.json",
        },
        "source_specific": source_specific or {},
        "symbol_distribution": symbol_distribution or {},
        "topic_distribution": topic_distribution or {},
    }
