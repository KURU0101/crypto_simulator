from __future__ import annotations

import argparse
import json

from trade_simulator.integrated_observer import build_integrated_summary_report, scan_saved_signal_summaries


def build_integrated_observer_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read saved News and SNS summary.json files and print an integrated observation report."
    )
    parser.add_argument("--root-dir", default="var", help="Base directory that contains news_signals/ and sns_signals/.")
    parser.add_argument("--signal-type", choices=("all", "news", "sns"), default="all", help="Limit runs by signal type.")
    parser.add_argument("--source", help="Limit runs to one collector source.")
    parser.add_argument(
        "--group-by",
        choices=("overall", "signal_type", "source"),
        default="overall",
        help="How to group the integrated observation output.",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Show only the latest run for each signal_type/source pair after filtering.",
    )
    parser.add_argument(
        "--format",
        choices=("condensed", "verbose", "json"),
        default="condensed",
        help="Output format for the observation report.",
    )
    return parser


def format_integrated_summary_report(report: dict, *, output_format: str = "condensed") -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if output_format not in {"condensed", "verbose"}:
        raise ValueError(f"unsupported output format: {output_format}")

    verbose = output_format == "verbose"
    lines = [
        "Integrated External Signal Observation",
        _format_totals_line("totals", report["totals"]),
    ]

    if not report["runs"]:
        lines.append("runs: none")
        return "\n".join(lines)

    for group in report["groups"]:
        lines.append("")
        lines.append(f"[group] {group['key']}")
        lines.append(_format_totals_line("group_totals", group["totals"]))
        for entry in group["runs"]:
            lines.extend(_format_run_lines(entry, verbose=verbose))

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_integrated_observer_parser()
    args = parser.parse_args(argv)

    entries = scan_saved_signal_summaries(args.root_dir)
    report = build_integrated_summary_report(
        entries,
        signal_type=args.signal_type,
        source=args.source,
        latest_only=args.latest_only,
        group_by=args.group_by,
    )
    print(format_integrated_summary_report(report, output_format=args.format))
    return 0


def _format_totals_line(label: str, totals: dict) -> str:
    return (
        f"{label}: runs={totals['run_count']} completed={totals['completed_count']} failed={totals['failed_count']} "
        f"invalid={totals['invalid_run_count']} warning_runs={totals['warning_run_count']} "
        f"error_runs={totals['error_run_count']} fetched={totals['fetched_item_count']} "
        f"normalized={totals['normalized_success_count']} validation_failures={totals['validation_failure_count']} "
        f"saved={totals['saved_record_count']} duplicates={totals['duplicate_count']} "
        f"latest_started_at={totals['latest_started_at'] or '-'} latest_ended_at={totals['latest_ended_at'] or '-'} "
        f"symbols={totals['symbol_distribution_overview']} topics={totals['topic_distribution_overview']}"
    )


def _format_run_lines(entry: dict, *, verbose: bool) -> list[str]:
    paths = _format_mapping(entry["saved_paths"])
    lines = [
        (
            f"- {entry['signal_type']}/{entry['source']}/{entry['run_id']} "
            f"status={entry['status']} started_at={entry['started_at'] or '-'} ended_at={entry['ended_at'] or '-'} "
            f"fetched={entry['fetched_item_count']} normalized={entry['normalized_success_count']} "
            f"validation_failures={entry['validation_failure_count']} saved={entry['saved_record_count']} "
            f"duplicates={entry['duplicate_count']} warnings={entry['warning_count']} errors={entry['error_count']} "
            f"source_specific={'yes' if entry['has_source_specific'] else 'no'}"
        ),
        f"  saved_paths={paths}",
        f"  symbols={entry['symbol_distribution_overview']}",
        f"  topics={entry['topic_distribution_overview']}",
    ]

    if entry["missing_required_fields"]:
        lines.append(f"  missing_required_fields={','.join(entry['missing_required_fields'])}")
    if entry["warnings"]:
        lines.append(f"  warnings={'; '.join(entry['warnings'])}")
    if entry["errors"]:
        lines.append(f"  errors={'; '.join(_format_error_messages(entry['errors']))}")
    if verbose:
        lines.append(f"  source_specific={json.dumps(entry['source_specific'], ensure_ascii=False, sort_keys=True)}")
        lines.append(f"  symbol_distribution={json.dumps(entry['symbol_distribution'], ensure_ascii=False, sort_keys=True)}")
        lines.append(f"  topic_distribution={json.dumps(entry['topic_distribution'], ensure_ascii=False, sort_keys=True)}")

    return lines


def _format_mapping(mapping: dict[str, str]) -> str:
    if not mapping:
        return "none"
    return ",".join(f"{key}={value}" for key, value in sorted(mapping.items()))


def _format_error_messages(errors: list[dict]) -> list[str]:
    messages: list[str] = []
    for error in errors:
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(message.strip())
        else:
            messages.append(json.dumps(error, ensure_ascii=False, sort_keys=True))
    return messages


__all__ = [
    "build_integrated_observer_parser",
    "format_integrated_summary_report",
    "main",
]
