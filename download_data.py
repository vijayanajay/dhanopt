"""Automated 5-Year Historical NSE FO Bhavcopy Downloader.

Usage:
    python download_data.py
    python download_data.py --start-year 2021 --end-year 2026 --workers 4

Downloads, normalizes, and partitions official NSE FO Bhavcopy data into compact
Parquet files under data/historical/ for walk-forward backtesting.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import List

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

import config
from core.feeds.bhavcopy import download_fo_bhavcopy, get_partition_path

logging.basicConfig(level=logging.ERROR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download 5-Year Historical NSE FO Bhavcopy Data")
    parser.add_argument("--start-year", type=int, default=2021, help="Start year (default: 2021)")
    parser.add_argument("--end-year", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent worker threads (default: 4)")
    return parser.parse_args()


def generate_weekday_dates(start_date: date, end_date: date) -> List[date]:
    """Generates all Monday-Friday trading calendar dates between start and end."""
    dates: List[date] = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # Monday to Friday
            dates.append(curr)
        curr += timedelta(days=1)
    return dates


def download_historical_archive(
    start_year: int = 2021,
    end_year: int = 2026,
    workers: int = 4,
) -> None:
    console = Console()
    start_d = date(start_year, 1, 1)
    # Don't exceed today
    end_d = min(date(end_year, 12, 31), date.today())

    all_weekdays = generate_weekday_dates(start_d, end_d)
    
    # Filter out files that already exist on disk
    pending_dates = [d for d in all_weekdays if not get_partition_path(d).exists()]
    existing_count = len(all_weekdays) - len(pending_dates)

    header = f"NSE FO 5-YEAR HISTORICAL DATA DOWNLOADER ({start_year} - {end_d.year})\n"
    header += f"Total Weekday Dates: {len(all_weekdays)} | Already Cached: {existing_count} | Pending: {len(pending_dates)}\n"
    header += f"Target Directory: {config.HISTORICAL_DATA_DIR}"
    console.print(Panel(header, box=box.HEAVY, border_style="cyan"))

    if not pending_dates:
        console.print("[bold green]All historical dates are already downloaded and cached locally![/bold green]")
        return

    success_count = 0
    holiday_count = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    def fetch_date(d: date) -> tuple[date, bool]:
        try:
            download_fo_bhavcopy(d, skip_if_present=True)
            return d, True
        except Exception:
            return d, False

    with progress:
        task = progress.add_task("Downloading NSE Bhavcopy...", total=len(pending_dates))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_date = {executor.submit(fetch_date, d): d for d in pending_dates}

            for future in as_completed(future_to_date):
                d, ok = future.result()
                if ok:
                    success_count += 1
                else:
                    holiday_count += 1
                progress.advance(task)

    console.print(
        f"\n[bold green]Download Complete![/bold green] "
        f"Downloaded: {success_count} trading sessions. Holidays/Weekends skipped: {holiday_count}. "
        f"Total available on disk: {existing_count + success_count} files."
    )


def main() -> None:
    args = parse_args()
    download_historical_archive(
        start_year=args.start_year,
        end_year=args.end_year,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
