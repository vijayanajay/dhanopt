"""E005: Theta-aware intraday condor replay — settles whether the condor edge survives exits.

Why e004's condor column failed: (1) fixed-IV BS never credits theta decay — the
condor's entire income — and (2) core's greeks floor each leg at 0.50, so the modeled
book collected ~₹458 credit where the real (skewed) market charges thousands.

E005 design (delta-path with theta glide, anchored to the TRADED book's endpoints):
- Entry levels: each leg's REAL day-t OPEN price (bhavcopy 'open' column — observable at
  the 09:15 entry, the exact convention e001/e004 use; skew embedded).
- Exit levels: each leg's REAL day-t close. EOD exits therefore reproduce e001's
  open->close outcome EXACTLY, by construction.
- Net greeks: finite-difference delta/gamma of floor-free BS per leg at its own implied
  IV (bisection from the open price; clamped band — deltas stay well-behaved even at
  0-1 DTE where prices/IVs degenerate), referenced to the day's opening spot.
- Intraday MTM at bar i:
      MTM_i = [net_delta * dS + 0.5 * net_gamma * dS^2] * qty
              + (endpoint_pnl - that same greek PnL at the close) * (i+1)/n
  i.e. the real delta/gamma response to the 5-min futures path, plus the residual
  (theta + vol change + everything greeks miss) glided linearly to the real close.
  Intraday exits catch the greek-driven drawdowns the daily proxy cannot see (trend
  days, mid-day crashes that recover, gap-and-restore days).

Exits: 1.4x credit SL / +50% credit-decay target / EOD 15:25, SL wins inside a bar.
The question this answers: with honest levels AND a real delta path, does the condor
edge survive intraday stop risk?

# ponytail: first-order model — gamma convexity near the walls is missed, so spike
# losses past the walls are UNDERSTATED (biases toward fewer stops). No intraday vol
# response (vanna/volga). Per-leg BS ratios were tried and explode at 0-1 DTE where
# cheap legs back out absurd IVs; delta+glide is the stable floor. Upgraded answer
# needs historical intraday option candles.

Run: python -m experiments.e005_theta_condor.replay_theta
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.bhavcopy import parse_date
from core.feeds.intraday import available_dates, load_intraday_candles
from experiments.common.lots import lot_for_date
from experiments.e004_intraday_replay.replay_intraday import CONDOR

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"

# Same condor exit rules as e004 / the strategies' documented rules.
STOP_FRAC, TARGET_FRAC = 1.40, 0.50
N_BARS = 75  # full 09:15-15:30 session at 5-min bars
WING_OFFSET = 150  # e001's CONDOR_WING_OFFSET


def _condor_legs_unconditional(put_wall: float, call_wall: float) -> List[dict]:
    """Legs exactly as e001 builds them: NO put_wall < atm < call_wall guard.
    e001's label set includes days where the max-OI call wall sits BELOW spot
    (resistance lags in strong rallies) and it sells that ITM call anyway — e005 must
    mirror that leg-for-leg or the comparison to the frozen labels is invalid."""
    return [
        {"strike": put_wall, "is_call": False, "action": "SELL"},
        {"strike": call_wall, "is_call": True, "action": "SELL"},
        {"strike": put_wall - WING_OFFSET, "is_call": False, "action": "BUY"},
        {"strike": call_wall + WING_OFFSET, "is_call": True, "action": "BUY"},
    ]


def _bs_ltp(spot: float, strike: float, is_call: bool, iv: float, dte_days: float) -> float:
    """Floor-free BS price mirroring core.feeds.dhan._approx_bs_greeks's closed form.

    The core function floors ltp at 0.50 (a display floor); e005 needs pure ratios,
    where a floor corrupts the elasticity of cheap legs.
    """
    import math
    t = max(dte_days, 0.1) / 365.0
    vol = max(iv, 0.05)
    denom = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * t) / denom
    d2 = d1 - denom
    cdf = lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    if is_call:
        return spot * cdf(d1) - strike * cdf(d2)
    return strike * (1.0 - cdf(d2)) - spot * (1.0 - cdf(d1))


def _partition_calendar(historical_dir: Path) -> Dict:
    """trade date -> parquet path, indexed once (bhavcopy stems are fo_YYYYMMDD)."""
    cal: Dict = {}
    for f in historical_dir.glob("**/*.parquet"):
        stem = f.stem
        if stem.startswith("fo_") and len(stem) == 11 and stem[3:].isdigit():
            try:
                cal[datetime.strptime(stem[3:], "%Y%m%d").date()] = f
            except ValueError:
                continue
    return cal


def _safe_exp(e):
    try:
        return parse_date(str(e).strip())
    except Exception:
        return None


def _chain_view(df: pd.DataFrame, expiry) -> Tuple[pd.DataFrame, pd.DataFrame]:
    nifty = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["OPTIDX", "IDO"]))]
    chain = nifty[nifty["expiry"].map(lambda e: _safe_exp(e) == expiry)]
    return chain[chain["option_type"] == "PE"], chain[chain["option_type"] == "CE"]


def _implied_iv_safe(spot: float, strike: float, is_call: bool, price: float, dte_days: float) -> float:
    """Per-leg IV for DELTA estimation only, clamped to a sane band. Deltas are
    insensitive to IV misestimation; the clamp avoids 0-DTE degenerate backouts."""
    return min(max(_implied_iv(spot, strike, is_call, price, dte_days), 0.05), 2.0)


def _leg_delta(spot: float, strike: float, is_call: bool, iv: float, dte_days: float,
               bump: float = 25.0) -> float:
    """Finite-difference delta of the floor-free BS at the leg's own IV."""
    return (_bs_ltp(spot + bump, strike, is_call, iv, dte_days)
            - _bs_ltp(spot - bump, strike, is_call, iv, dte_days)) / (2.0 * bump)


def _leg_gamma(spot: float, strike: float, is_call: bool, iv: float, dte_days: float,
               bump: float = 25.0) -> float:
    """Finite-difference gamma of the floor-free BS at the leg's own IV."""
    up = _bs_ltp(spot + bump, strike, is_call, iv, dte_days)
    mid = _bs_ltp(spot, strike, is_call, iv, dte_days)
    dn = _bs_ltp(spot - bump, strike, is_call, iv, dte_days)
    return (up - 2.0 * mid + dn) / (bump * bump)


def _implied_iv(spot: float, strike: float, is_call: bool, price: float, dte_days: float) -> float:
    """Backs out the leg's own implied vol from its real close (bisection; BS is
    monotone in iv). Clamps to [0.005, 5.0] — the clamp only pins elasticity, and the
    ratio construction stays consistent at any iv."""
    lo, hi = 0.005, 5.0
    if _bs_ltp(spot, strike, is_call, lo, dte_days) >= price:
        return lo
    if _bs_ltp(spot, strike, is_call, hi, dte_days) <= price:
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _bs_ltp(spot, strike, is_call, mid, dte_days) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build_sigma_path(sigma_prev_close: float, sigma_day_close: float, n_bars: int = N_BARS) -> np.ndarray:
    """Linear interpolation of IV across the session (kept for tests/experiments)."""
    return np.linspace(sigma_prev_close, sigma_day_close, n_bars)


def simulate_theta_condor(candles: pd.DataFrame, legs: List[dict], entry_closes: List[float],
                          exit_closes: List[float], lot: int, dte0: float,
                          spot_open: float) -> Dict:
    """Walks the condor through the 5-min path: real greek response + theta glide
    landing exactly on the real open->close endpoint PnL (see module docstring)."""
    qty = lot
    ivs = [_implied_iv_safe(spot_open, l["strike"], l["is_call"], float(ec), dte0)
           for l, ec in zip(legs, entry_closes)]
    sgn = [1.0 if l["action"] == "BUY" else -1.0 for l in legs]
    net_delta = sum(_leg_delta(spot_open, l["strike"], l["is_call"], iv, dte0) * s
                    for l, iv, s in zip(legs, ivs, sgn))  # per-point MTM per unit qty
    net_gamma = sum(_leg_gamma(spot_open, l["strike"], l["is_call"], iv, dte0) * s
                    for l, iv, s in zip(legs, ivs, sgn))  # per-point^2 MTM per unit qty

    spot_close = float(candles.iloc[-1]["close"])
    endpoint_pnl = sum((e - x) * qty for e, x, l in zip(entry_closes, exit_closes, legs)
                       if l["action"] == "SELL") \
        + sum((x - e) * qty for e, x, l in zip(entry_closes, exit_closes, legs)
              if l["action"] == "BUY")

    def greek_pnl(spot: float) -> float:
        ds = spot - spot_open
        return (net_delta * ds + 0.5 * net_gamma * ds * ds) * qty

    resid_total = endpoint_pnl - greek_pnl(spot_close)

    entry_credit = sum(e * qty for e, l in zip(entry_closes, legs) if l["action"] == "SELL") \
        - sum(e * qty for e, l in zip(entry_closes, legs) if l["action"] == "BUY")
    stop_level = -STOP_FRAC * abs(entry_credit)
    target_level = TARGET_FRAC * abs(entry_credit)

    n = len(candles)
    exit_reason, exit_bar = "EOD", n
    mtm_series: List[float] = []
    for i, (_, bar) in enumerate(candles.iterrows()):
        mtm = greek_pnl(float(bar["close"])) + resid_total * (i + 1) / n
        mtm_series.append(mtm)
        if mtm <= stop_level:
            exit_reason, exit_bar = "STOP", i + 1
            break
        if mtm >= target_level:
            exit_reason, exit_bar = "TARGET", i + 1
            break
    gross_pnl = float(mtm_series[exit_bar - 1])

    from core.friction.zerodha import OptionLeg, calculate_friction
    olegs = [OptionLeg(strike=l["strike"], option_type="CE" if l["is_call"] else "PE",
                       action=l["action"], entry_price=float(entry_closes[i]), lot_size=qty)
             for i, l in enumerate(legs)]
    fric = calculate_friction(olegs)
    return {
        "exit_reason": exit_reason, "bars_held": exit_bar,
        "gross_pnl": round(gross_pnl, 2), "friction": fric.total_rupees,
        "net_pnl": round(gross_pnl - fric.total_rupees, 2),
        "win": bool(gross_pnl - fric.total_rupees > 0),
        "net_delta": round(net_delta, 4),
        "credit": round(entry_credit, 2),
    }


def run_days(dates: List, historical_dir: Path, cal: Dict, rule_days: set) -> pd.DataFrame:
    rows: List[Dict] = []
    for d in dates:
        d_date = d.date() if hasattr(d, "date") else d
        ts = pd.Timestamp(d)
        try:
            candles = load_intraday_candles(d)
        except FileNotFoundError:
            continue
        own_df = cal.get(d_date)  # day-d's own partition: entry opens, exit closes, e001 anchor
        own_df = pd.read_parquet(own_df) if own_df else None
        if own_df is None:
            continue

        # Walls + expiry from day-d's OWN chain — the exact convention of the e001 labels
        # (walls = max-OI strike of the nearest expiry in the same partition). Matching it
        # makes EOD exits comparable to e001 leg-for-leg; the no-look-ahead wall variant
        # (t-1 OI) is a stricter design left to a follow-up.
        nifty = own_df[(own_df["symbol"] == "NIFTY") & (own_df["instrument"].isin(["OPTIDX", "IDO"]))]
        exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= d_date]
        if not exps:
            continue
        expiry = min(exps)
        pe, ce = _chain_view(own_df, expiry)
        if pe.empty or ce.empty:
            continue
        put_wall = float(pe.loc[pe["open_interest"].idxmax(), "strike"])
        call_wall = float(ce.loc[ce["open_interest"].idxmax(), "strike"])
        dte0 = max((expiry - d_date).days, 0.5)

        legs = _condor_legs_unconditional(put_wall, call_wall)
        base = {"date": ts.isoformat(), "is_rule_day": ts in rule_days, "expiry": expiry.isoformat()}

        # Entry anchors = the leg OPEN prices of day d (observable at 09:15, e001's
        # convention); exit anchors = the leg closes. Same chain/expiry, day-d partition.
        pe_e, ce_e = _chain_view(own_df, expiry)
        e1_chain = pd.concat([pe_e, ce_e])

        def _px_map(col: str) -> Dict:
            m = {}
            for _, r in e1_chain.iterrows():
                k = (float(r["strike"]), str(r["option_type"]))  # strikes collide across PE/CE
                if k not in m and float(r[col]) > 0:
                    m[k] = float(r[col])  # first row per (strike, type), e001's _ohlc_at convention
            return m

        open_map, exit_map = _px_map("open"), _px_map("close")
        entry_closes = [open_map.get((float(l["strike"]), "PE" if not l["is_call"] else "CE")) for l in legs]
        exit_closes = [exit_map.get((float(l["strike"]), "PE" if not l["is_call"] else "CE")) for l in legs]
        if (any(c is None or c <= 0 for c in entry_closes)
                or any(c is None or c < 0 for c in exit_closes)):
            rows.append({**base, "exit_reason": "NOLEG", "net_pnl": 0.0})
            continue
        # e001 skips the day when the structure opens at zero-or-negative credit.
        credit = sum(entry_closes[i] * lot_for_date(d) for i, l in enumerate(legs) if l["action"] == "SELL") \
            - sum(entry_closes[i] * lot_for_date(d) for i, l in enumerate(legs) if l["action"] == "BUY")
        if credit <= 0:
            rows.append({**base, "exit_reason": "NOSIM", "net_pnl": 0.0})
            continue

        sim = simulate_theta_condor(candles, legs, [float(c) for c in entry_closes],
                                    [float(c) for c in exit_closes], lot_for_date(d),
                                    dte0, float(candles.iloc[0]["open"]))
        rows.append({**base, **sim})
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> str:
    sim = df[~df["exit_reason"].isin(["NOSIM", "NOLEG"])].copy()
    sim["date"] = pd.to_datetime(sim["date"])
    gp = sim.loc[sim.net_pnl > 0, "net_pnl"].sum()
    gl = abs(sim.loc[sim.net_pnl <= 0, "net_pnl"].sum())
    daily = sim.groupby("date")["net_pnl"].sum().sort_index().cumsum()
    dd = float((daily - daily.cummax()).min())
    lines = [
        "E005 PRICE-ANCHORED THETA-AWARE CONDOR REPLAY (real endpoint closes, 5-min paths)",
        "=" * 78,
        f"n={len(sim)} wr={(sim.net_pnl > 0).mean():.3f} net={sim.net_pnl.sum():,.0f} "
        f"avg={sim.net_pnl.mean():,.1f} pf={(gp / gl if gl else float('inf')):.2f} maxDD={dd:,.0f}",
        f"exits={sim.exit_reason.value_counts().to_dict()}",
    ]
    for era_name, mask in [("Thu-expiry era (->2025-08)", sim.date < "2025-09-01"),
                           ("Tue-expiry era (2025-09->)", sim.date >= "2025-09-01")]:
        s = sim[mask]
        exp = s[s.date.dt.weekday == (3 if "Thu" in era_name else 1)]
        lines.append(f"{era_name}: n={len(s)} net={s.net_pnl.sum():,.0f} | expiry-day n={len(exp)} "
                     f"net={exp.net_pnl.sum():,.0f} wr={(exp.net_pnl > 0).mean() if len(exp) else float('nan'):.3f}")
    rule = sim[sim.is_rule_day]
    lines.append(f"rule-selected condor days: n={len(rule)} net={rule.net_pnl.sum():,.0f} "
                 f"wr={(rule.net_pnl > 0).mean() if len(rule) else float('nan'):.3f}")
    lines.append("\nCompare: e001 open->close +731,746 wr .475 | e004 fixed-IV (INVALID) -547,744 wr .041")
    return "\n".join(lines)


def main() -> int:
    import config

    parser = argparse.ArgumentParser(description="E005 theta-aware condor replay")
    parser.parse_args()

    dates = available_dates()
    if not dates:
        print("No intraday partitions found.")
        return 1

    labels = pd.read_csv(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv",
                         parse_dates=["date"])
    rule_days = set(labels[(labels.archetype == "Iron Condor") & labels.selected_by_rule]["date"])

    out_csv = ARTIFACTS / "theta_condor.csv"
    if out_csv.exists():
        done = set(pd.read_csv(out_csv, usecols=["date"])["date"])
        dates = [d for d in dates if pd.Timestamp(d).isoformat() not in done]
        print(f"resuming: {len(done)} sessions already replayed")
    if not dates:
        df = pd.read_csv(out_csv)
    else:
        print(f"Replaying {len(dates)} sessions (theta-aware condor)...")
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
        CHUNK = 90
        for i in range(0, len(dates), CHUNK):
            part = run_days(dates[i:i + CHUNK], config.HISTORICAL_DATA_DIR, cal, rule_days)
            part.to_csv(out_csv, mode="a", header=not out_csv.exists(), index=False)
            print(f"  {min(i + CHUNK, len(dates))}/{len(dates)} sessions done", flush=True)
        df = pd.read_csv(out_csv)

    report = summarize(df)
    (ARTIFACTS / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
