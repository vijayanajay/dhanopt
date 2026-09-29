"""Backtest & Walk-Forward Analysis Engine (Time-of-Entry & Real Historical Validation).

Usage:
    python backtest.py
    python backtest.py --time "10:15"

Provides:
1. Real Historical FO Bhavcopy Backtest (Downloaded Parquet Partitions from NSE).
2. Walk-Forward Performance Breakdown by Time of Entry Window.
3. 16-Fold Rolling Out-of-Sample (OOS) Validation Table (2021-2026).
4. Parameter Calibration & Edge Hurdle Verification (P_win >= 55%, PF >= 1.40).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from backtest.engine import WalkForwardEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-Forward & Time-of-Entry Backtest Analysis")
    parser.add_argument(
        "--time",
        type=str,
        default=None,
        help="Optional entry time filter (e.g. '10:00', '10:15', '13:15')",
    )
    return parser.parse_args()


def run_backtest_cli(time_filter: Optional[str] = None) -> int:
    console = Console()
    engine = WalkForwardEngine()

    summary = engine.run_backtest(16)

    # --- Header Banner ---
    header_text = Text()
    header_text.append("QUANTITATIVE NIFTY OPTIONS WALK-FORWARD BACKTEST & REAL HISTORICAL ANALYSIS\n", style="bold cyan")
    header_text.append("Data Source: Real NSE FO Bhavcopy Parquet Partitions | Execution: Zerodha Post-Oct 2024 Fees\n", style="dim")
    header_text.append("Bankroll: ₹2,00,000 | Max Daily Loss: ₹2,500 | Minimum Edge Hurdle: Win Rate >= 55.0%", style="bold white")
    console.print(Panel(header_text, box=box.HEAVY, border_style="cyan"))

    # --- PART 1: Real Historical FO Bhavcopy Results ---
    if summary.real_trades:
        real_wins = [t for t in summary.real_trades if t.get("win")]
        real_losses = [t for t in summary.real_trades if not t.get("win")]
        real_wr = len(real_wins) / len(summary.real_trades) if summary.real_trades else 0.0
        real_pnl = sum(t["net_pnl"] for t in summary.real_trades)
        real_gross = sum(t["gross_pnl"] for t in summary.real_trades)
        real_fric = sum(t["friction"] for t in summary.real_trades)
        real_pf = (
            sum(t["net_pnl"] for t in real_wins) / abs(sum(t["net_pnl"] for t in real_losses))
            if real_losses and abs(sum(t["net_pnl"] for t in real_losses)) > 0
            else 0.0
        )

        real_panel = Text()
        real_panel.append(f"REAL HISTORICAL SESSIONS EVALUATED: {len(summary.real_trades)} Trading Days\n\n", style="bold white")
        real_panel.append(f"• Real Win Rate: {real_wr * 100:.1f}% (Winning Trades: {len(real_wins)} / Losing: {len(real_losses)})\n", style="bold green" if real_wr >= 0.55 else "bold red")
        real_panel.append(f"• Real Profit Factor: {real_pf:.2f} (Gross Profit / Gross Loss)\n", style="bold green" if real_pf >= 1.40 else "bold red")
        real_panel.append(f"• Total Real Net PnL: +₹{real_pnl:,.2f} (Post Zerodha Frictions: -₹{real_fric:,.2f})\n", style="bold cyan")
        real_panel.append(f"• Average Real Net PnL per Trade: +₹{real_pnl / len(summary.real_trades):,.2f}\n\n", style="white")

        # Breakdown by strategy
        strategies = {}
        for t in summary.real_trades:
            st = t["strategy"]
            if st not in strategies:
                strategies[st] = {"count": 0, "wins": 0, "pnl": 0.0}
            strategies[st]["count"] += 1
            if t.get("win"):
                strategies[st]["wins"] += 1
            strategies[st]["pnl"] += t["net_pnl"]

        real_panel.append("Real Strategy Breakdown from NSE Market Fills:\n", style="bold yellow")
        for st_name, st_data in strategies.items():
            st_wr = (st_data["wins"] / st_data["count"]) * 100
            pnl_sign = "+" if st_data["pnl"] >= 0 else "-"
            real_panel.append(f"  • {st_name:<18s}: {st_data['count']} trades | Win Rate: {st_wr:.1f}% | Net PnL: {pnl_sign}₹{abs(st_data['pnl']):,.2f}\n", style="white")

        console.print(Panel(real_panel, title="[bold green]PART 1: REAL HISTORICAL FO BHAVCOPY RESULTS (NSE DATA)[/bold green]", border_style="green", box=box.ROUNDED))

        # Recent 10 Real Trades Table
        t_recent = Table(
            title="[bold green]SAMPLE RECENT REAL HISTORICAL TRADES (NSE FO BHAVCOPY)[/bold green]",
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold green",
            expand=True,
        )
        t_recent.add_column("Trade Date", width=14)
        t_recent.add_column("Strategy", width=20)
        t_recent.add_column("Gross PnL", justify="right", width=14)
        t_recent.add_column("Zerodha Friction", justify="right", width=16)
        t_recent.add_column("Net PnL", justify="right", width=16)
        t_recent.add_column("Outcome", justify="center", width=12)

        for tr in summary.real_trades[-12:]:
            gross_str = f"+₹{tr['gross_pnl']:,.2f}" if tr['gross_pnl'] >= 0 else f"-₹{abs(tr['gross_pnl']):,.2f}"
            net_str = f"+₹{tr['net_pnl']:,.2f}" if tr['net_pnl'] >= 0 else f"-₹{abs(tr['net_pnl']):,.2f}"
            outcome_t = Text("WIN", style="bold green") if tr['win'] else Text("LOSS", style="bold red")
            pnl_t = Text(net_str, style="bold green" if tr['win'] else "bold red")
            t_recent.add_row(
                tr["date"],
                tr["strategy"],
                gross_str,
                f"₹{tr['friction']:.2f}",
                pnl_t,
                outcome_t,
            )
        console.print(t_recent)

    # --- PART 2: Time of Entry Breakdown ---
    t1 = Table(
        title="[bold yellow]PART 2: PERFORMANCE BREAKDOWN BY TIME OF ENTRY WINDOW[/bold yellow]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    t1.add_column("Entry Window", style="bold white", width=15)
    t1.add_column("Market Dynamic / Profile", style="dim", width=28)
    t1.add_column("Optimal Days", width=18)
    t1.add_column("Trades", justify="right", width=8)
    t1.add_column("Win Rate", justify="right", width=10)
    t1.add_column("Profit Factor", justify="right", width=12)
    t1.add_column("Net EV / Trade", justify="right", width=14)
    t1.add_column("Verdict", width=14)

    for item in summary.time_of_entry_results:
        if time_filter and time_filter not in item.time_window:
            continue

        if item.status == "OPTIMAL":
            verdict = Text("OPTIMAL", style="bold green")
            wr_style = "bold green"
            pf_style = "bold green"
            ev_style = "bold green"
        elif item.status == "SECONDARY":
            verdict = Text("SECONDARY", style="bold cyan")
            wr_style = "cyan"
            pf_style = "cyan"
            ev_style = "cyan"
        elif item.status == "UNMEASURED":
            verdict = Text("UNMEASURED", style="bold yellow")
            wr_style = "yellow"
            pf_style = "yellow"
            ev_style = "yellow"
        else:
            verdict = Text("AVOID", style="bold red")
            wr_style = "bold red"
            pf_style = "bold red"
            ev_style = "bold red"

        wr_str = f"{item.win_rate * 100:.1f}%" if item.win_rate is not None else "N/A"
        pf_str = f"{item.profit_factor:.2f}" if item.profit_factor is not None else "N/A"
        if item.avg_net_ev is not None:
            ev_str = f"+₹{item.avg_net_ev:,.2f}" if item.avg_net_ev > 0 else f"-₹{abs(item.avg_net_ev):,.2f}"
        else:
            ev_str = "N/A"

        t1.add_row(
            item.time_window,
            item.regime_name,
            item.optimal_days,
            str(item.trades),
            Text(wr_str, style=wr_style),
            Text(pf_str, style=pf_style),
            Text(ev_str, style=ev_style),
            verdict,
        )

    console.print(t1)

    # --- PART 3: 16-Fold Walk-Forward Validation Table ---
    t2 = Table(
        title="[bold yellow]PART 3: 16-FOLD ROLLING WALK-FORWARD OUT-OF-SAMPLE (OOS) VALIDATION[/bold yellow]",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    t2.add_column("Fold #", justify="center", width=8)
    t2.add_column("In-Sample (12M Train)", width=24)
    t2.add_column("Out-of-Sample (3M Test)", width=24)
    t2.add_column("OOS Trades", justify="right", width=12)
    t2.add_column("OOS Win Rate", justify="right", width=14)
    t2.add_column("OOS Profit Factor", justify="right", width=16)
    t2.add_column("OOS Net PnL", justify="right", width=16)

    for f in summary.folds:
        wr_t = Text(f"{f.oos_win_rate * 100:.1f}%", style="green" if f.oos_win_rate >= 0.55 else "red")
        pf_t = Text(f"{f.oos_profit_factor:.2f}", style="green" if f.oos_profit_factor >= 1.40 else "red")
        pnl_t = Text(f"+₹{f.oos_net_pnl:,.2f}", style="bold green" if f.oos_net_pnl > 0 else "bold red")
        t2.add_row(
            f"Fold {f.fold_index:02d}",
            f"{f.train_start} to {f.train_end}",
            f"{f.test_start} to {f.test_end}",
            str(f.oos_trades),
            wr_t,
            pf_t,
            pnl_t,
        )

    console.print(t2)

    # --- Summary Card ---
    wr_passed = summary.overall_win_rate >= 0.55
    pf_passed = summary.overall_profit_factor >= 1.40
    dd_passed = summary.overall_max_drawdown_pct <= 5.5
    edge_confirmed = wr_passed and pf_passed and dd_passed

    sum_text = Text()
    sum_text.append("AGGREGATE OUT-OF-SAMPLE VALIDATION METRICS (2021–2026):\n\n", style="bold white")
    sum_text.append(f"• Total Out-of-Sample Trades: {summary.total_oos_trades}\n", style="white")
    sum_text.append(
        f"• Overall OOS Win Rate: {summary.overall_win_rate * 100:.1f}% (Hurdle >= 55.0%: {'PASSED' if wr_passed else 'FAILED'})\n",
        style="bold green" if wr_passed else "bold red",
    )
    sum_text.append(
        f"• Overall Profit Factor: {summary.overall_profit_factor:.2f} (Hurdle >= 1.40: {'PASSED' if pf_passed else 'FAILED'})\n",
        style="bold green" if pf_passed else "bold red",
    )
    sum_text.append(
        f"• Maximum Strategy Drawdown: {summary.overall_max_drawdown_pct:.1f}% (Cap <= 5.5%: {'PASSED' if dd_passed else 'FAILED'})\n",
        style="bold green" if dd_passed else "bold red",
    )
    ev_color = "bold cyan" if summary.overall_net_ev > 0 else "bold red"
    ev_sign = "+" if summary.overall_net_ev >= 0 else "-"
    sum_text.append(f"• Net Expectancy per Trade: {ev_sign}₹{abs(summary.overall_net_ev):,.2f} (Post Zerodha Friction & Slippage)\n\n", style=ev_color)
    sum_text.append(f"Calibrated parameters written to: {engine.params_path}\n", style="dim italic")

    verdict_title = "[bold green]WALK-FORWARD VERDICT: MATHEMATICAL EDGE CONFIRMED[/bold green]" if edge_confirmed else "[bold red]WALK-FORWARD VERDICT: HURDLE NOT MET[/bold red]"
    verdict_border = "green" if edge_confirmed else "red"
    console.print(Panel(sum_text, title=verdict_title, border_style=verdict_border, box=box.ROUNDED))
    return 0


def main() -> None:
    args = parse_args()
    sys.exit(run_backtest_cli(time_filter=args.time))


if __name__ == "__main__":
    main()
