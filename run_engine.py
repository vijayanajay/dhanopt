"""Dynamic On-Demand Runner for Quantitative Nifty Options Engine.

Can be executed on-demand at any time during market hours (09:30 AM to 02:30 PM IST).
Pipeline:
1. Ingestion: Aggregates 5-min candles from 09:15 AM up to T_now and snapshots live option chain.
2. Microstructure Signals: Computes VWAP slope, ORB-30, VIX dynamics, OI walls, and KER.
3. 3-Strategy Comparative Audit: Simultaneously evaluates Debit Spread, Credit Spread, and Iron Condor.
4. Gatekeeper Validation: Sub-microsecond deterministic risk, capital, and economic hurdle vetos.
5. Delivery: Renders 3-panel Rich terminal UI, exports Zerodha Kite basket JSON, and sends Telegram alert.

Usage:
    python run_engine.py --mock --timestamp "10:15"
    python run_engine.py --mock --timestamp "11:30" --trend "chop"
    python run_engine.py --live
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from core.execution.basket_builder import build_kite_basket
from core.feeds.dhan import DhanFeed, generate_mock_candles, generate_mock_option_chain
from core.signals import generate_market_signals
from core.strategies.audit_engine import ComparativeAuditEngine
from core.ui.telegram_push import push_trade_alert
from core.ui.terminal_rich import render_terminal_dashboard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quantitative Nifty Options Decision & Execution Engine"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=None,
        help="Execute in offline mock mode using synthetic data",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live execution with DhanHQ API feeds",
    )
    parser.add_argument(
        "--timestamp",
        type=str,
        default=None,
        help="Point-in-time timestamp (e.g. '10:15', '13:30', or '2026-09-30 10:15:00')",
    )
    parser.add_argument(
        "--trend",
        type=str,
        choices=["bullish", "bearish", "chop"],
        default="bullish",
        help="Simulated market regime for mock execution (bullish, bearish, chop)",
    )
    parser.add_argument(
        "--lots",
        type=int,
        default=1,
        help="Number of lots to execute (default: 1 lot / 75 quantity)",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress terminal UI rendering (for background cron jobs)",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Force Telegram alert push even in mock mode",
    )
    return parser.parse_args()


def resolve_run_datetime(timestamp_arg: Optional[str]) -> datetime:
    """Resolves target execution datetime from CLI argument or current system time."""
    now = datetime.now()
    if not timestamp_arg:
        return now

    arg = timestamp_arg.strip()
    # Check if full date string
    if " " in arg or "-" in arg:
        try:
            return datetime.fromisoformat(arg)
        except ValueError:
            pass

    # Treat as HH:MM or HH:MM:SS
    parts = arg.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    s = int(parts[2]) if len(parts) > 2 else 0

    return datetime(now.year, now.month, now.day, h, m, s)


def run_pipeline(
    mock_mode: bool = False,
    run_dt: Optional[datetime] = None,
    trend: str = "bullish",
    lots: int = 1,
    silent: bool = False,
    push_telegram: bool = False,
) -> int:
    """Executes the master quant decision pipeline."""
    target_dt = run_dt or datetime.now()
    time_str = target_dt.strftime("%H:%M")

    # 1. Evaluate Weekday Optimal Window
    is_optimal, window_name = config.is_optimal_window(target_dt)

    # 2. Ingestion & Feed Aggregation
    if mock_mode:
        base_spot = 25200.0 if trend != "bearish" else 25100.0
        candles = generate_mock_candles(
            symbol="NIFTY",
            trade_date=target_dt.date(),
            from_time="09:15",
            to_time=time_str,
            interval=5,
            base_price=base_spot,
            trend=trend,
        )
        spot_price = float(candles.iloc[-1]["close"])
        vix = 13.2 if trend != "chop" else 15.8
        prev_vix = 13.5
        chain = generate_mock_option_chain(
            spot_price=spot_price,
            expiry=target_dt.strftime("%Y-%m-%d"),
            snap_time=target_dt,
        )
    else:
        feed = DhanFeed()
        candles = feed.fetch_intraday_candles("NIFTY", from_time="09:15", to_time=time_str, interval=5)
        spot_price = feed.fetch_spot_price("NIFTY")
        chain = feed.fetch_option_chain("NIFTY")
        vix = feed.fetch_vix()
        prev_vix = vix

    if candles.empty:
        if not silent:
            print(f"[!] No intraday candles available for {time_str}. Market may be closed.")
        return 1

    # 3. Compute Microstructure Signals
    signals = generate_market_signals(
        candles=candles,
        chain=chain,
        vix=vix,
        prev_vix=prev_vix,
    )

    # 4. Mandatory 3-Strategy Comparative Audit Engine
    audit_engine = ComparativeAuditEngine()
    audit_report = audit_engine.run_audit(
        signals=signals,
        chain=chain,
        lots=lots,
        is_optimal_window=is_optimal,
    )

    # 5. One-Click Execution Basket
    basket = None
    if audit_report.is_trade_approved and audit_report.selected_proposal:
        basket = build_kite_basket(audit_report.selected_proposal)
        # Export basket JSON file for Kite Web
        basket.export_to_file()

    # 6. Render Terminal Report
    if not silent:
        render_terminal_dashboard(
            signals=signals,
            report=audit_report,
            basket=basket,
            weekday_window_status=window_name,
            is_optimal_window=is_optimal,
        )

    # 7. Telegram Alert
    if push_telegram or (not mock_mode and config.TELEGRAM_BOT_TOKEN):
        push_trade_alert(signals=signals, report=audit_report, basket=basket)

    return 0


def main() -> None:
    args = parse_args()
    
    # Resolve mock mode: explicit flag overrides .env
    if args.live:
        mock_mode = False
    elif args.mock is not None:
        mock_mode = args.mock
    else:
        mock_mode = config.MOCK_MODE

    run_dt = resolve_run_datetime(args.timestamp)
    exit_code = run_pipeline(
        mock_mode=mock_mode,
        run_dt=run_dt,
        trend=args.trend,
        lots=args.lots,
        silent=args.silent,
        push_telegram=args.telegram,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
