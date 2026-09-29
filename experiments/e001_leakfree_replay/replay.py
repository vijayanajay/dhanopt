"""E001: Leak-free daily replay of the 3 strategy archetypes on FO bhavcopy.

Fixes the three measurement bugs in backtest/engine.py's simulate_session_from_parquet:
1. Look-ahead: the old replay branches on day-t's open->close return, then enters at open.
   Here the DECISION uses only day t-1 information (prior-day body return), and entry is
   at day-t open, exit at day-t close. Every day is replayed through ALL 3 archetypes
   (the old engine picked one strategy per day, destroying the ML label set).
2. Lot size: the old replay hardcoded 75 for all years. Here era-correct lots are used
   (25 -> 75 on 2024-11-20 -> 65 on 2025-12-30, per NSE FAOP67372 / FAOP70616).
3. One strategy per day: here bull spread, bear spread, and iron condor are each
   simulated every day, producing the label table ML needs.

Sandbox rule (brd.md 9A): imports core.*, never modifies anything outside experiments/.

Usage:
    python -m experiments.e001_leakfree_replay.replay          # full run, writes artifacts
    python -m experiments.e001_leakfree_replay.replay --limit 50
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.feeds.bhavcopy import parse_date
from core.friction.zerodha import OptionLeg, calculate_friction
from experiments.common.lots import lot_for_date

HERE = Path(__file__).resolve().parent
ARTIFACTS_DIR = HERE / "artifacts"

SPREAD_OFFSET = 150          # short leg 150 pts OTM (matches core replay convention)
CONDOR_WING_OFFSET = 150     # hedge leg 150 pts beyond the wall strikes
BASE_LOT_ERA_FALLBACK = 25   # eras themselves live in experiments/common/lots.py

BULL, BEAR, CONDOR = "Bull Call Spread", "Bear Put Spread", "Iron Condor"
ARCHETYPES = (BULL, BEAR, CONDOR)

# Decision rule threshold (prior-day body return, in %). Deliberately simple: it is the
# honest baseline the ML models must beat, not a tuned strategy.
TREND_THRESHOLD_PCT = 0.25


def _parse_trade_date(raw: Any) -> Optional[date]:
    for candidate in (raw, str(raw).strip()):
        try:
            return parse_date(candidate)
        except Exception:
            continue
    return None


def _nearest_expiry(options: pd.DataFrame) -> Optional[str]:
    expiries: List[tuple[date, str]] = []
    for e in options["expiry"].unique():
        d = _parse_trade_date(e)
        if d is not None:
            expiries.append((d, str(e).strip()))
    if not expiries:
        return None
    expiries.sort()
    return expiries[0][1]


def _ohlc_at(chain: pd.DataFrame, strike: float, option_type: str) -> Optional[tuple[float, float]]:
    row = chain[(chain["option_type"] == option_type) & (chain["strike"] == strike)]
    if row.empty:
        return None
    o, c = float(row.iloc[0]["open"]), float(row.iloc[0]["close"])
    if o <= 0 or c <= 0:
        return None
    return o, c


def _spread_pnl(chain: pd.DataFrame, atm: float, offset: float, is_call: bool, qty: int) -> Optional[Dict[str, Any]]:
    otype = "CE" if is_call else "PE"
    long_px = _ohlc_at(chain, atm, otype)
    # Bull call spread shorts the call ABOVE atm; bear put spread shorts the put BELOW atm.
    short_strike = atm + offset if is_call else atm - offset
    short_px = _ohlc_at(chain, short_strike, otype)
    if long_px is None or short_px is None:
        return None
    l_open, l_close = long_px
    s_open, s_close = short_px
    if not (l_open > s_open > 0):
        return None  # inverted/unusable spread quotes
    entry_debit = l_open - s_open
    exit_value = l_close - s_close
    gross = (exit_value - entry_debit) * qty
    legs = [
        OptionLeg(strike=atm, option_type=otype, action="BUY", entry_price=l_open, lot_size=qty),
        OptionLeg(strike=short_strike, option_type=otype, action="SELL", entry_price=s_open, lot_size=qty),
    ]
    fric = calculate_friction(legs)
    return {"gross_pnl": round(gross, 2), "friction": fric.total_rupees, "net_pnl": round(gross - fric.total_rupees, 2)}


def _condor_pnl(chain: pd.DataFrame, put_wall: float, call_wall: float, qty: int) -> Optional[Dict[str, Any]]:
    shorts = [
        (put_wall, "PE", "SELL"),
        (call_wall, "CE", "SELL"),
        (put_wall - CONDOR_WING_OFFSET, "PE", "BUY"),
        (call_wall + CONDOR_WING_OFFSET, "CE", "BUY"),
    ]
    legs: List[OptionLeg] = []
    c_open = 0.0
    c_close = 0.0
    for strike, otype, action in shorts:
        px = _ohlc_at(chain, strike, otype)
        if px is None:
            return None
        o, c = px
        c_open += (o if action == "SELL" else -o)
        c_close += (c if action == "SELL" else -c)
        legs.append(OptionLeg(strike=strike, option_type=otype, action=action, entry_price=o, lot_size=qty))
    if c_open <= 0:
        return None
    gross = (c_open - c_close) * qty
    fric = calculate_friction(legs)
    return {"gross_pnl": round(gross, 2), "friction": fric.total_rupees, "net_pnl": round(gross - fric.total_rupees, 2)}


def replay_day(day_df: pd.DataFrame, prev_pct: Optional[float]) -> List[Dict[str, Any]]:
    """Replays ONE bhavcopy day through all 3 archetypes using only t-1 info for the decision.

    Returns a list of outcome dicts (0-3 entries). prev_pct is the PRIOR day's open->close %;
    when None (first day of the dataset) no directional signal exists yet.
    """
    nifty = day_df[day_df["symbol"] == "NIFTY"]
    if nifty.empty:
        return []

    fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
    if fut.empty:
        return []
    fut_row = fut.iloc[0]
    f_open, f_close, f_high, f_low = (float(fut_row[k]) for k in ("open", "close", "high", "low"))
    if f_open <= 0 or f_close <= 0:
        return []

    trade_date = _parse_trade_date(fut_row["trade_date"])
    if trade_date is None:
        return []

    options = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
    if options.empty:
        return []
    nearest_exp = _nearest_expiry(options)
    if nearest_exp is None:
        return []
    chain = options[options["expiry"] == nearest_exp]
    if chain.empty:
        return []

    pe_chain = chain[chain["option_type"] == "PE"]
    ce_chain = chain[chain["option_type"] == "CE"]
    put_wall = float(pe_chain.loc[pe_chain["open_interest"].idxmax()]["strike"]) if not pe_chain.empty else None
    call_wall = float(ce_chain.loc[ce_chain["open_interest"].idxmax()]["strike"]) if not ce_chain.empty else None

    atm = round(f_open / 50.0) * 50.0
    qty = lot_for_date(trade_date)

    # ---- t-1 decision (the ONLY place the signal is used; entry prices below are day-t) ----
    trend = "NONE" if prev_pct is None else ("UP" if prev_pct >= TREND_THRESHOLD_PCT else "DOWN" if prev_pct <= -TREND_THRESHOLD_PCT else "FLAT")

    # ---- entry at day-t open, exit at day-t close, for ALL archetypes ----
    sim_results = {
        BULL: _spread_pnl(chain, atm, SPREAD_OFFSET, is_call=True, qty=qty),
        BEAR: _spread_pnl(chain, atm, SPREAD_OFFSET, is_call=False, qty=qty),
    }
    if put_wall is not None and call_wall is not None:
        sim_results[CONDOR] = _condor_pnl(chain, put_wall, call_wall, qty)
    else:
        sim_results[CONDOR] = None

    rows: List[Dict[str, Any]] = []
    for archetype in ARCHETYPES:
        sim = sim_results.get(archetype)
        row = {
            "date": trade_date.isoformat(),
            "weekday": trade_date.strftime("%A"),
            "archetype": archetype,
            "signal": trend,
            "selected_by_rule": (archetype == BULL and trend == "UP")
            or (archetype == BEAR and trend == "DOWN")
            or (archetype == CONDOR and trend == "FLAT"),
            "lot": qty,
            "gross_pnl": sim["gross_pnl"] if sim else 0.0,
            "friction": sim["friction"] if sim else 0.0,
            "net_pnl": sim["net_pnl"] if sim else 0.0,
            "simulated": sim is not None,
            "win": bool(sim and sim["net_pnl"] > 0),
        }
        rows.append(row)
    return rows


def replay_all(historical_dir: Path, limit: Optional[int] = None) -> pd.DataFrame:
    """Replays every parquet partition chronologically, carrying t-1 signal state."""
    files = sorted(historical_dir.glob("**/*.parquet"))
    if limit:
        files = files[-limit:]

    all_rows: List[Dict[str, Any]] = []
    prev_pct: Optional[float] = None
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        # Extract the day's own open->close return for use as the NEXT day's signal.
        nifty = df[df["symbol"] == "NIFTY"]
        fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])] if not nifty.empty else nifty
        day_pct: Optional[float] = None
        if not fut.empty:
            o, c = float(fut.iloc[0]["open"]), float(fut.iloc[0]["close"])
            if o > 0:
                day_pct = (c - o) / o * 100.0

        all_rows.extend(replay_day(df, prev_pct))
        prev_pct = day_pct

    return pd.DataFrame(all_rows)


def summarize(labels: pd.DataFrame) -> str:
    """Human-readable comparison report (old biased numbers vs honest replay)."""
    lines: List[str] = []
    lines.append("E001 LEAK-FREE REPLAY — HONEST BASELINE (decision from t-1 close, entry at day-t open)")
    lines.append("=" * 88)
    lines.append(f"rows: {len(labels)} | days with signal: {labels.loc[labels['signal'] != 'NONE', 'date'].nunique() if not labels.empty else 0}")

    lines.append("")
    lines.append("Per archetype, ALL days simulated:")
    lines.append(f"{'archetype':<18}{'n':>6}{'win_rate':>10}{'avg_net':>10}{'total_net':>12}{'pf':>8}")
    for arch in ARCHETYPES:
        sub = labels[(labels["archetype"] == arch) & labels["simulated"]] if not labels.empty else labels
        if sub.empty:
            lines.append(f"{arch:<18}{0:>6}{'-':>10}{'-':>10}{'-':>12}{'-':>8}")
            continue
        wins = sub[sub["win"]]["net_pnl"].sum()
        losses = abs(sub[~sub["win"]]["net_pnl"].sum())
        pf = round(wins / losses, 2) if losses > 0 else float("inf")
        lines.append(
            f"{arch:<18}{len(sub):>6}{sub['win'].mean():>10.3f}{sub['net_pnl'].mean():>10.1f}{sub['net_pnl'].sum():>12.0f}{pf:>8}"
        )

    lines.append("")
    lines.append("Rule-selected subset (what the t-1 momentum rule would actually have traded):")
    sel = labels[labels["selected_by_rule"] & labels["simulated"]] if not labels.empty else labels
    if sel.empty:
        lines.append("  (no rows)")
    else:
        for arch in ARCHETYPES:
            sub = sel[sel["archetype"] == arch]
            if sub.empty:
                continue
            wins = sub[sub["win"]]["net_pnl"].sum()
            losses = abs(sub[~sub["win"]]["net_pnl"].sum())
            pf = round(wins / losses, 2) if losses > 0 else float("inf")
            lines.append(
                f"  {arch:<18}n={len(sub):<5} wr={sub['win'].mean():.3f}  avg_net={sub['net_pnl'].mean():>8.1f}  total={sub['net_pnl'].sum():>10.0f}  pf={pf}"
            )
        lines.append(f"  TOTAL: n={len(sel)}  net={sel['net_pnl'].sum():,.0f}  wr={sel['win'].mean():.3f}")

    lines.append("")
    lines.append("OLD BIASED ENGINE (for comparison — NOT valid): decision from day-t close = look-ahead.")
    lines.append("Old output: Bull 79.5% wr pf 12.41 | Bear 87.4% wr pf 26.16 | Condor 45.9% wr pf 7.03 | aggregate pf 22.17")
    lines.append("Expectation: honest numbers must land near ~50% wr / pf ~1. Anything far above suggests residual bias — investigate, don't celebrate.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="E001 leak-free replay")
    parser.add_argument("--limit", type=int, default=None, help="Only replay the last N parquet days (smoke test)")
    parser.add_argument("--historical-dir", type=str, default=None)
    args = parser.parse_args()

    import config

    hist = Path(args.historical_dir) if args.historical_dir else config.HISTORICAL_DATA_DIR
    labels = replay_all(hist, limit=args.limit)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = ARTIFACTS_DIR / "labels_daily.csv"
    labels.to_csv(out_csv, index=False)

    report = summarize(labels)
    (ARTIFACTS_DIR / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nartifacts written: {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
