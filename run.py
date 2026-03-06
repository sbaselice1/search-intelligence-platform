#!/usr/bin/env python3
"""CLI entry point for the AI Overview Monitor.

Usage:
    # Run a daily check with default config
    python run.py

    # Run with a custom config file
    python run.py --config path/to/config.yaml

    # Run for a specific date (re-run / backfill)
    python run.py --date 2026-03-01

    # Export results for a date to CSV
    python run.py --export-csv 2026-03-01

    # Show help
    python run.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI Overview Monitor — daily Google SERP monitoring workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                          Run daily check with default config
  python run.py --config my_config.yaml  Use custom config
  python run.py --date 2026-03-01        Run for a specific date
  python run.py --export-csv 2026-03-01  Export CSV for a date
        """,
    )
    parser.add_argument(
        "--config",
        default="aio_monitor/config/config.yaml",
        help="Path to YAML configuration file (default: aio_monitor/config/config.yaml)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Override run date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--export-csv",
        metavar="DATE",
        default=None,
        help="Export results for a date to CSV and exit.",
    )

    args = parser.parse_args()

    # CSV export mode
    if args.export_csv:
        return _export_csv(args.config, args.export_csv)

    # Normal daily run
    from aio_monitor.orchestrator import run_daily_check

    try:
        summary = asyncio.run(run_daily_check(
            config_path=args.config,
            date_override=args.date,
        ))
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Exit code based on results
    if summary.failed_count > 0 and summary.failed_count == summary.total_keywords:
        return 2  # All failed
    return 0


def _export_csv(config_path: str, date_str: str) -> int:
    """Export results for a given date to CSV."""
    import yaml
    from aio_monitor.storage.sqlite_store import SQLiteStore

    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    output_config = config.get("output", {})
    base_dir = Path(output_config.get("base_dir", "output"))
    db_path = base_dir / output_config.get("db_name", "aio_monitor.db")

    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    store = SQLiteStore(db_path)
    store.initialize()

    csv_path = str(base_dir / "reports" / f"export_{date_str}.csv")
    store.export_csv(csv_path, date_str)
    store.close()

    print(f"CSV exported to: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
