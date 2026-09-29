"""Automated NIFTY 5-minute intraday candle backfill via DhanHQ.

Backfills data/intraday/ partitions for a date range (weekdays only, weekends skipped,
holidays surface as MissingDataError and are counted). Rate-limited by DhanFeed.

Usage:
    python download_intraday.py --start 2026-09-01 --end 2026-09-26
    python download_intraday.py --start 2026-09-25 --workers 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from core.feeds.intraday import MissingDataError, download_intraday_candles, get_partition_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill NIFTY 5-minute intraday candles")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent workers (Dhan rate limits: keep low)")
    return parser.parse_args()


def weekday_range(start_s: str, end_s: str) -> list:
    start = datetime.strptime(start_s, "%Y-%m-%d").date()
    end = datetime.strptime(end_s, "%Y-%m-%d").date()
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    args = parse_args()
    days = weekday_range(args.start, args.end)
    pending = [d for d in days if not get_partition_path(d).exists()]
    print(f"Weekdays in range: {len(days)} | already cached: {len(days) - len(pending)} | pending: {len(pending)}")
    if not pending:
        print("All sessions already cached.")
        return 0

    ok = missing = corrupt = 0
    with Progress(
        SpinnerColumn(), TextColumn("[bold blue]{task.description}"), BarColumn(bar_width=40),
        MofNCompleteColumn(), TimeElapsedColumn(), TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Downloading 5-min candles...", total=len(pending))
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(download_intraday_candles, d): d for d in pending}
            for fut in as_completed(futures):
                try:
                    fut.result()
                    ok += 1
                except MissingDataError:
                    missing += 1
                except Exception:
                    corrupt += 1
                progress.advance(task)

    print(f"Done. Downloaded: {ok} | holidays/missing: {missing} | errors: {corrupt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
