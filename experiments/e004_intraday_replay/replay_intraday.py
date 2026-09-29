"""E004: Intraday replay of the 3 archetypes on 5-min candles (SL/target/EOG paths).

Fixes the accepted ceiling of e001/e002: daily open->close bars cannot see intraday
stop-losses or profit targets. Here each archetype is priced leg-by-leg along the
5-minute path using the same closed-form BS approximation as the live engine
(core.feeds.dhan._approx_bs_greeks — reused, not copied), with exits:
  - EOD: square off at the 15:25 bar (matches the engine's intraday mandate),
  - STOP: portfolio MTM crosses -stop_fraction x net outlay,
  - TARGET: portfolio MTM crosses +target_fraction x net outlay.
Conservative rule when both SL and target could trigger within one bar: STOP wins.

# ponytail: BS re-pricing with a fixed per-day IV is a approximation, not a market fill:
# no intraday vol crush, no bid/ask, no liquidity impact. Direction of bias is stated
# per-archetype in the README verdict. Upgrade path: bolt Dhan tick data onto this loop.

Requires data/intraday partitions (download via download_intraday.py first) AND
e001's labels_daily.csv for the prior-day decision rule.
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.dhan import _approx_bs_greeks
from core.feeds.intraday import available_dates, load_intraday_candles
from core.feeds.bhavcopy import parse_date
from experiments.common.lots import lot_for_date

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"

BULL, BEAR, CONDOR = "Bull Call Spread", "Bear Put Spread", "Iron Condor"
ARCHETYPES = (BULL, BEAR, CONDOR)
TREND_THRESHOLD_PCT = 0.25  # same rule as e001

# Exit fractions (match the strategies' documented rules: 35% debit SL / 70% max-profit
# for spreads; 1.4x credit SL / 50% credit-decay target for condor).
EXIT_RULES: Dict[str, Tuple[float, float]] = {
    BULL: (0.35, 0.70),
    BEAR: (0.35, 0.70),
    CONDOR: (1.40, 0.50),
}

SPREAD_OFFSET = 150
WING_OFFSET = 150


def _price_leg(spot: float, strike: float, is_call: bool, iv: float, dte: float) -> float:
    g = _approx_bs_greeks(spot, strike, is_call=is_call, iv=iv, dte_days=dte)
    return max(0.05, float(g["ltp"]))


def _safe_parse(e):
    try:
        return parse_date(str(e).strip())
    except Exception:
        return None


def _load_prior_partition(historical_dir: Path, d, _cache: Dict = {}) -> Optional[pd.DataFrame]:
    """Loads the most recent bhavcopy partition strictly BEFORE day d (stem date = YYYYMMDD)."""
    if not _cache:
        for f in historical_dir.glob("**/*.parquet"):
            stem = f.stem
            if stem.startswith("fo_") and len(stem) == 11 and stem[3:].isdigit():
                try:
                    fd = datetime.strptime(stem[3:], "%Y%m%d").date()
                except ValueError:
                    continue
                _cache[fd] = f
    prior_dates = sorted([fd for fd in _cache if fd < d])
    if not prior_dates:
        return None
    return pd.read_parquet(_cache[prior_dates[-1]])


def _iv_from_straddle(spot: float, atm: float, dte: float, straddle: float) -> float:
    """Solves approximate IV from an ATM straddle price (Brenner-Subrahmanyam: sigma ≈ P/(0.8 S sqrt(t)))."""
    t = max(dte, 0.1) / 365.0
    sigma = straddle / (0.8 * spot * math.sqrt(t))
    return min(2.0, max(0.05, sigma))


def _legs_for(archetype: str, spot_open: float, put_wall: float, call_wall: float) -> Optional[List[dict]]:
    atm = round(spot_open / 50.0) * 50.0
    if archetype == BULL:
        legs = [{"strike": atm, "is_call": True, "action": "BUY"},
                {"strike": atm + SPREAD_OFFSET, "is_call": True, "action": "SELL"}]
    elif archetype == BEAR:
        legs = [{"strike": atm, "is_call": False, "action": "BUY"},
                {"strike": atm - SPREAD_OFFSET, "is_call": False, "action": "SELL"}]
    else:
        if not (put_wall < atm < call_wall):
            return None  # malformed day
        legs = [
            {"strike": put_wall, "is_call": False, "action": "SELL"},
            {"strike": call_wall, "is_call": True, "action": "SELL"},
            {"strike": put_wall - WING_OFFSET, "is_call": False, "action": "BUY"},
            {"strike": call_wall + WING_OFFSET, "is_call": True, "action": "BUY"},
        ]
    return legs


def simulate_day(candles: pd.DataFrame, archetype: str, lot: int, iv: float, dte: float) -> Optional[Dict]:
    """Walks one archetype through the 5-min path. Returns outcome dict or None."""
    legs = candles.attrs.get("legs_by_arch", {}).get(archetype)
    if not legs:
        return None

    qty = lot
    prices_open = [_price_leg(candles.iloc[0]["open"], l["strike"], l["is_call"], iv, dte) for l in legs]
    short_outlay = sum(p * qty for p, l in zip(prices_open, legs) if l["action"] == "SELL")
    long_outlay = sum(p * qty for p, l in zip(prices_open, legs) if l["action"] == "BUY")
    net_outlay = long_outlay - short_outlay  # negative for credit books

    stop_frac, target_frac = EXIT_RULES[archetype]
    stop_level = -stop_frac * abs(net_outlay)
    target_level = target_frac * abs(net_outlay)

    exit_reason, exit_mtms = "EOD", None
    mtm_series: List[float] = []
    for _, bar in candles.iterrows():
        prices = [_price_leg(bar["close"], l["strike"], l["is_call"], iv, dte) for l in legs]
        mtm = sum((p - p0) * qty for p, p0, l in zip(prices, prices_open, legs) if l["action"] == "BUY") \
            + sum((p0 - p) * qty for p, p0, l in zip(prices, prices_open, legs) if l["action"] == "SELL")
        mtm_series.append(mtm)
        if mtm <= stop_level:
            exit_reason, exit_mtms = "STOP", len(mtm_series)
            break
        if mtm >= target_level:
            exit_reason, exit_mtms = "TARGET", len(mtm_series)
            break
    if exit_mtms is None:
        exit_mtms = len(mtm_series)
    gross_pnl = float(mtm_series[exit_mtms - 1])

    # Friction via the core engine on real-ish entry prices; EOD path adds exit legs at last prices.
    from core.friction.zerodha import OptionLeg, calculate_friction
    olegs = [
        OptionLeg(
            strike=l["strike"], option_type="CE" if l["is_call"] else "PE", action=l["action"],
            entry_price=prices_open[i], lot_size=qty,
        )
        for i, l in enumerate(legs)
    ]
    fric = calculate_friction(olegs)

    return {
        "archetype": archetype,
        "exit_reason": exit_reason,
        "bars_held": exit_mtms,
        "gross_pnl": round(gross_pnl, 2),
        "friction": fric.total_rupees,
        "net_pnl": round(gross_pnl - fric.total_rupees, 2),
        "win": bool(gross_pnl - fric.total_rupees > 0),
    }


def run_days(dates: List, historical_dir: Path, intraday_dir: Optional[Path] = None) -> pd.DataFrame:
    """Replays all 3 archetypes on each available intraday day with the t-1 rule signal.

    Ponytail ceiling: O(prior-partition scan) per day — acceptable at backfill scale;
    upgrade path: cache prior-day walls/IV next to the intraday partitions.
    """
    # Prior-day signals from e001 labels (rule decisions), aligned by date.
    e001_labels = pd.read_csv(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv",
                              parse_dates=["date"])
    fut_sig = (e001_labels.groupby("date")["signal"].first())

    rows: List[Dict] = []
    for d in dates:
        try:
            candles = load_intraday_candles(d, data_dir=intraday_dir)
        except FileNotFoundError:
            continue

        sig = fut_sig.get(pd.Timestamp(d))
        trend = "NONE" if pd.isna(sig) else str(sig)
        lot = lot_for_date(d)

        # Daily chain context for walls + IV proxy from the PRIOR day's partition (no look-ahead:
        # walls/strikes are fixed from t-1 OI before the open).
        prior_df = _load_prior_partition(historical_dir, d)
        if prior_df is None:
            continue
        nifty = prior_df[prior_df["symbol"] == "NIFTY"]
        fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
        opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
        if fut.empty or opts.empty:
            continue
        expiries = sorted([(parse_date(str(e).strip()), str(e).strip()) for e in opts["expiry"].unique()
                           if _safe_parse(e) is not None])
        if not expiries:
            continue
        chain = opts[opts["expiry"] == expiries[0][1]]
        pe, ce = chain[chain["option_type"] == "PE"], chain[chain["option_type"] == "CE"]
        if pe.empty or ce.empty:
            continue
        put_wall = float(pe.loc[pe["open_interest"].idxmax(), "strike"])
        call_wall = float(ce.loc[ce["open_interest"].idxmax(), "strike"])

        # ATM straddle (prior day, nearest expiry) -> IV proxy
        prev_close = float(fut.iloc[0]["close"])
        atm = round(prev_close / 50.0) * 50.0
        atm_ce = ce[ce["strike"] == atm]
        atm_pe = pe[pe["strike"] == atm]
        if atm_ce.empty or atm_pe.empty:
            continue
        straddle = float(atm_ce.iloc[0]["close"]) + float(atm_pe.iloc[0]["close"])
        dte = max((expiries[0][0] - d).days, 0.5)
        iv = _iv_from_straddle(prev_close, atm, dte, straddle)

        # Same-day open for leg construction (known at 09:15 entry time; strikes fixed pre-open
        # from prior-day walls — the open only sets the ATM leg strike, which is observable at entry).
        day_open = float(candles.iloc[0]["open"])
        legs_by_arch = {a: _legs_for(a, day_open, put_wall, call_wall) for a in ARCHETYPES}
        candles = candles.copy()
        candles.attrs["legs_by_arch"] = legs_by_arch

        for arch in ARCHETYPES:
            sim = simulate_day(candles, arch, lot, iv, dte)
            rows.append({
                "date": d.isoformat(),
                "weekday": d.strftime("%A"),
                "signal": trend,
                "archetype": arch,
                "rule_selected": (arch == BULL and trend == "UP") or (arch == BEAR and trend == "DOWN") or (arch == CONDOR and trend == "FLAT"),
                **(sim if sim else {"exit_reason": "NOSIM", "bars_held": 0, "gross_pnl": 0.0,
                                    "friction": 0.0, "net_pnl": 0.0, "win": False}),
            })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> str:
    lines = ["E004 INTRADAY REPLAY (5-min SL/target/EOG paths)", "=" * 64]
    for arch in ARCHETYPES:
        sub = df[(df["archetype"] == arch) & (df["exit_reason"] != "NOSIM")]
        if sub.empty:
            lines.append(f"{arch:<18} n=0")
            continue
        exits = sub["exit_reason"].value_counts().to_dict()
        wr = sub["win"].mean()
        lines.append(
            f"{arch:<18} n={len(sub):<5} wr={wr:.3f} net={sub['net_pnl'].sum():>10,.0f} "
            f"avg={sub['net_pnl'].mean():>8.1f} exits={exits}"
        )
    sel = df[df["rule_selected"] & (df["exit_reason"] != "NOSIM")]
    if not sel.empty:
        lines.append(f"\nRule-selected subset: n={len(sel)} net={sel['net_pnl'].sum():,.0f} wr={sel['win'].mean():.3f}")
    lines.append("\nCompare with e001 (open->close): Bull 32.4% wr / PF 0.47 | Bear 44.3% / 0.81 | Condor 47.5% / 3.67")
    return "\n".join(lines)


def main() -> int:
    import config

    parser = argparse.ArgumentParser(description="E004 intraday path replay")
    args = parser.parse_args()

    dates = available_dates()
    if not dates:
        print("No intraday partitions found. Run: python download_intraday.py --start YYYY-MM-DD --end YYYY-MM-DD")
        return 1

    # Chunked checkpointing: append after each chunk, skip already-replayed dates on re-run,
    # so an interrupted full-window replay resumes instead of restarting from zero.
    out_csv = ARTIFACTS / "intraday_replay.csv"
    if out_csv.exists():
        done = set(pd.read_csv(out_csv, usecols=["date"])["date"].map(parse_date))
        dates = [d for d in dates if d not in done]
        print(f"resuming: {len(done)} sessions already replayed")
    if not dates:
        df = pd.read_csv(out_csv)
    else:
        print(f"Replaying {len(dates)} intraday sessions (SL/target/EOG paths)...")
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        CHUNK = 60
        for i in range(0, len(dates), CHUNK):
            df = run_days(dates[i:i + CHUNK], config.HISTORICAL_DATA_DIR)
            df.to_csv(out_csv, mode="a", header=not out_csv.exists(), index=False)
            print(f"  {min(i + CHUNK, len(dates))}/{len(dates)} sessions done", flush=True)
        df = pd.read_csv(out_csv)

    report = summarize(df)
    (ARTIFACTS / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
