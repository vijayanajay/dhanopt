"""Rich Multi-Panel Terminal UI for Quantitative Nifty Options Engine.

Renders institutional-grade terminal reports with zero fluff:
- Panel 1: Telemetry & Microstructure Diagnostics (Spot, VWAP, ORB, VIX, Walls, KER)
- Panel 2: Mandatory 3-Strategy Comparative Audit Table (Pass/Fail reasons for each)
- Panel 3: Recommended Zerodha Basket Order Sheet OR Standby/Preservation Directives
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import config
from core.execution.basket_builder import KiteBasket
from core.signals import MarketSignals
from core.strategies.audit_engine import AuditReport


def render_terminal_dashboard(
    signals: MarketSignals,
    report: AuditReport,
    basket: Optional[KiteBasket] = None,
    weekday_window_status: str = "OPTIMAL",
    is_optimal_window: bool = True,
    console: Optional[Console] = None,
) -> Console:
    """Renders the complete 3-panel institutional dashboard to console."""
    c = console or Console()

    # --- Header Information ---
    run_dt = signals.timestamp if isinstance(signals.timestamp, datetime) else datetime.now()
    time_str = run_dt.strftime("%I:%M %p")
    ts_str = run_dt.strftime("%Y-%m-%d %H:%M:%S")
    day_name = run_dt.strftime("%A")
    status_str = "ACTIVE TRADE CONFIRMED" if report.is_trade_approved else "STAND BY / CAPITAL PRESERVATION"
    status_style = "bold green" if report.is_trade_approved else "bold yellow"

    header_text = Text()
    header_text.append(f"QUANTITATIVE NIFTY OPTIONS ON-DEMAND ENGINE | {time_str} IST\n", style="bold cyan")
    header_text.append("Execution Broker: Zerodha Kite | Data Feed: DhanHQ API + 5-Yr Walk-Forward\n", style="dim")
    header_text.append(f"Run Timestamp: {ts_str} IST ({day_name}) | Status: ", style="white")
    header_text.append(f"{status_str}\n", style=status_style)

    # Underlying & Volatility metrics
    spot = signals.spot_price
    vwap_val = signals.vwap.vwap
    vix = signals.vix_iv.vix
    dvix = signals.vix_iv.delta_vix
    dvix_color = "red" if dvix > 0 else "green"

    header_text.append("Underlying: ", style="dim")
    header_text.append(f"NIFTY 50 Spot: {spot:,.2f} ", style="bold white")
    header_text.append(f"| VWAP: {vwap_val:,.2f} ", style="bold white")
    header_text.append(f"| India VIX: {vix:.2f} (", style="bold white")
    header_text.append(f"{dvix:+.2f}%", style=dvix_color)
    header_text.append(")\n", style="bold white")

    window_badge = "OPTIMAL" if is_optimal_window else "OFF-WINDOW"
    window_badge_style = "green" if is_optimal_window else "yellow"
    header_text.append("Weekday Window Status: ", style="dim")
    header_text.append(f"{window_badge} ", style=f"bold {window_badge_style}")
    header_text.append(f"({weekday_window_status})", style="white")

    c.print(Panel(header_text, box=box.HEAVY, border_style="cyan"))

    # --- PANEL 1: Market Microstructure Diagnostics ---
    p1_text = Text()
    
    # ORB line
    orb_desc = f"ORH: {signals.orb.orh:.1f} | ORL: {signals.orb.orl:.1f} | Range Width: {signals.orb.width:.1f} pts"
    if signals.orb.is_compressed:
        orb_desc += " [COMPRESSION DETECTED]"
    p1_text.append(f"• Opening Range (09:15-09:45): {orb_desc}\n", style="white")

    # ORB Status
    orb_color = "green" if signals.orb.is_breakout else ("cyan" if signals.orb.is_compressed else "yellow")
    p1_text.append(f"• ORB Status: ", style="white")
    p1_text.append(f"{signals.orb.status} (Vol Ratio: {signals.orb.volume_ratio:.2f}x)\n", style=orb_color)

    # VWAP Trend
    vwap_diff = spot - vwap_val
    vwap_sign = "+" if vwap_diff >= 0 else ""
    p1_text.append(f"• VWAP Trend: Price {'above' if vwap_diff >= 0 else 'below'} VWAP ({vwap_sign}{vwap_diff:.1f} pts) | ", style="white")
    p1_text.append(f"15-min Slope: {signals.vwap.slope_15m:+.3f}% ({signals.vwap.regime})\n", style="bold cyan")

    # KER
    ker_status = "Clean directional trend" if signals.ker.is_trending else ("High noise / chop" if signals.ker.is_noisy else "Neutral path")
    p1_text.append(f"• Momentum Efficiency (KER): {signals.ker.ker:.3f} ({ker_status})\n", style="white")

    # Volatility
    p1_text.append(f"• Volatility State: India VIX {signals.vix_iv.vix:.1f} | ATM IV: {signals.vix_iv.atm_iv:.1f} | ", style="white")
    p1_text.append(f"Parkinson Vol: {signals.vix_iv.parkinson_vol:.1f} | IV Spread: {signals.vix_iv.iv_spread:+.2f} pts\n", style="white")

    # OI Walls
    p1_text.append(f"• Dealer Positioning: Call Wall at {signals.oi.call_wall:.0f} | Put Wall at {signals.oi.put_wall:.0f} | ", style="white")
    p1_text.append(f"PCR OI: {signals.oi.pcr_oi:.2f} (Delta PCR: {signals.oi.delta_pcr:+.2f})\n", style="white")

    c.print(Panel(p1_text, title="[bold]PANEL 1: MARKET MICROSTRUCTURE DIAGNOSTICS[/bold]", border_style="blue", box=box.ROUNDED))

    # --- PANEL 2: Mandatory 3-Strategy Comparative Audit ---
    audit_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta", expand=True)
    audit_table.add_column("Strategy", style="bold white", width=16, no_wrap=True)
    audit_table.add_column("Status", width=10, no_wrap=True)
    audit_table.add_column("Win Rate", justify="right", width=9, no_wrap=True)
    audit_table.add_column("EV Score", justify="right", width=11, no_wrap=True)
    audit_table.add_column("Gate Evaluation / Invalidation Reason", style="dim", ratio=1)

    for entry in report.entries:
        if entry.status == "SELECTED":
            status_t = Text("SELECTED", style="bold green")
        elif entry.status == "QUALIFIED":
            status_t = Text("QUALIFIED", style="bold cyan")
        else:
            status_t = Text("REJECTED", style="bold red")

        win_rate_str = f"{entry.proposal.win_rate * 100:.1f}%" if entry.proposal else "—"
        ev_str = f"+₹{entry.ev_score:,.2f}" if entry.ev_score > 0 else (f"-₹{abs(entry.ev_score):,.2f}" if entry.ev_score < 0 else "₹0.00")
        ev_color = "green" if entry.ev_score > 0 else ("red" if entry.ev_score < 0 else "dim")
        ev_t = Text(ev_str, style=ev_color)

        audit_table.add_row(
            entry.strategy_name,
            status_t,
            win_rate_str,
            ev_t,
            entry.reason,
        )

    verdict_style = "bold green" if report.is_trade_approved else "bold yellow"
    verdict_text = Text(f"\n{report.verdict}", style=verdict_style)
    p2_content = Group(audit_table, verdict_text)
    c.print(Panel(p2_content, title="[bold]PANEL 2: MANDATORY 3-STRATEGY COMPARATIVE AUDIT[/bold]", border_style="magenta", box=box.ROUNDED))

    # --- PANEL 3: Order Sheet or Standby Directives ---
    if report.is_trade_approved and report.selected_proposal:
        prop = report.selected_proposal
        p3_text = Text()

        # Strategy & Sizing
        lots = prop.legs[0].lots if prop.legs else 1
        qty = lots * config.NIFTY_LOT_SIZE
        expiry_val = prop.expiry
        p3_text.append(f"Strategy: {prop.strategy_name.upper()} | Expiry: {expiry_val}\n", style="bold cyan")
        p3_text.append(f"Sizing: {lots} Lot ({qty} Qty) | Total Capital Outlay: ₹{abs(prop.net_debit_or_credit) * qty:,.2f}\n\n", style="white")

        p3_text.append("Basket Order Execution Sequence:\n", style="bold yellow")
        for idx, leg in enumerate(prop.legs, 1):
            action_tag = f"[{leg.action.upper()}]"
            action_color = "bold green" if leg.is_buy else "bold red"
            sym = leg.symbol or f"NIFTY {int(leg.strike)} {leg.option_type}"
            p3_text.append(f"{idx}. ", style="dim")
            p3_text.append(f"{action_tag:6s} ", style=action_color)
            p3_text.append(f"{sym:<18s} | Entry: ₹{leg.entry_price:.2f} | Upfront SL: ₹{leg.stop_price:.2f} | Target: ₹{leg.target_price:.2f}\n", style="white")

        p3_text.append("*(CRITICAL: Buy/Hedge legs executed first to secure Zerodha upfront margin relief)*\n\n", style="italic dim")

        # Risk & Return Metrics
        p3_text.append("Risk & Return Metrics:\n", style="bold white")
        prem_label = "Net Credit Received" if prop.is_credit else "Net Debit Paid"
        p3_text.append(f"• {prem_label}: ₹{abs(prop.net_debit_or_credit):.2f}/sh (₹{abs(prop.net_debit_or_credit) * qty:,.2f} total)\n", style="white")
        p3_text.append(f"• Net Portfolio Stop-Loss: -₹{prop.max_loss:,.2f} MTM (Strict risk ceiling)\n", style="bold red")
        p3_text.append(f"• Net Profit Target: +₹{prop.target_profit:,.2f} MTM (Payoff Ratio: {prop.payoff_ratio:.2f})\n", style="bold green")
        p3_text.append(f"• Round-Trip Zerodha Friction: ₹{prop.friction.total_rupees:.2f} (~{prop.friction.points_equivalent:.2f} Nifty pts)\n", style="dim")
        p3_text.append(f"• Expected Net EV: +₹{prop.net_ev:,.2f} per session\n", style="bold cyan")

        sq_off_time = config.get_square_off_time(run_dt).strftime("%I:%M %p")
        p3_text.append(f"• Hard Exit Timestamp: {sq_off_time} IST (Strict Intraday - Zero Overnight Carry)\n", style="bold yellow")

        if basket and basket.publisher_url:
            p3_text.append(f"\nOne-Click Zerodha Mobile Deep Link:\n{basket.publisher_url}\n", style="underline blue")

        c.print(Panel(p3_text, title="[bold]PANEL 3: RECOMMENDED ZERODHA BASKET ORDER SHEET[/bold]", border_style="green", box=box.ROUNDED))
    else:
        # STAND BY Panel
        p3_text = Text()
        p3_text.append("CAPITAL PRESERVATION DIRECTIVE ACTIVE: NO ORDERS GENERATED\n\n", style="bold yellow")
        p3_text.append("Diagnostics & Triggers Under Watch:\n", style="bold white")
        p3_text.append(f"• Current ORB Bounds: High {signals.orb.orh:.1f} | Low {signals.orb.orl:.1f} (Awaiting confirmed breakout)\n", style="white")
        p3_text.append(f"• KER Directional Hurdle: {signals.ker.ker:.3f} (Required > 0.55 for trend spreads, < 0.35 for chop condor)\n", style="white")
        p3_text.append(f"• Economic Edge Hurdle: Minimum Expected Net EV must exceed 2.0x friction (₹380.00)\n", style="white")
        p3_text.append("• Active Capital Vehicle: 100% Cash / Overnight Collateral Yield (~₹10,600/yr / ₹885/mo gross)\n", style="bold green")
        p3_text.append("• Empirical Audit Status: All option strategies vetted in e001-e032 stand down under economic hurdle\n\n", style="dim")

        sched = config.get_schedule_for_date(run_dt)
        if sched:
            p3_text.append(f"Weekday Schedule for {sched.day_name}:\n", style="bold cyan")
            p3_text.append(f"• Primary Window: {sched.primary_window.start.strftime('%H:%M')} - {sched.primary_window.end.strftime('%H:%M')} IST\n", style="white")
            if sched.secondary_window:
                p3_text.append(f"• Secondary Window: {sched.secondary_window.start.strftime('%H:%M')} - {sched.secondary_window.end.strftime('%H:%M')} IST\n", style="white")
            p3_text.append(f"• Description: {sched.description}\n", style="dim")

        p3_text.append("\nBankroll: ₹2,00,000.00 intact | Capital Deployed: ₹0.00 | Capital Preservation 100%\n", style="bold green")

        c.print(Panel(p3_text, title="[bold]PANEL 3: CAPITAL PRESERVATION & STAND BY STATUS[/bold]", border_style="yellow", box=box.ROUNDED))

    return c


def render_dashboard_to_string(
    signals: MarketSignals,
    report: AuditReport,
    basket: Optional[KiteBasket] = None,
    weekday_window_status: str = "OPTIMAL",
    is_optimal_window: bool = True,
) -> str:
    """Helper to render terminal dashboard into a plain/ANSI string for logging or testing."""
    string_io = io.StringIO()
    c = Console(file=string_io, force_terminal=True, width=100)
    render_terminal_dashboard(
        signals=signals,
        report=report,
        basket=basket,
        weekday_window_status=weekday_window_status,
        is_optimal_window=is_optimal_window,
        console=c,
    )
    return string_io.getvalue()
