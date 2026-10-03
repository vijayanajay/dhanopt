"""e028 — the per-leg no-arbitrage bound that DOES hold on every mark.

e026's iron-fly bound `(entry - W) <= gross <= entry` is an EXPIRY-payoff
statement: at expiry the fly is worth min(|S-K|, W). It does not hold on a
contract with days of life left, which e026's own docstring says. e026 asserts
it on every real mark anyway (`at_expiry=True`), and it never fired - because
the only session in the corrected sample that breaches it is a session the
encoding bug had excluded.

The bound that holds at ANY mark is per-leg: a traded option cannot close
materially below its intrinsic value. This checks all four legs of all 193
marks, so a stale close is measured rather than argued about.

Run: .venv/Scripts/python.exe -m experiments.e028_expiry_encoding_audit.intrinsic_audit
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.feeds.bhavcopy import with_expiry_date
from experiments.e026_realmark_audit import audit_realmark as A
from experiments.e026_realmark_audit.audit_realmark import (
    build_bhavcopy_calendar, collect_trades,
)
from experiments.e027_spread_realism.spread_realism import (
    CONSERVATIVE_PTS_PER_LEG, MODELLED_PTS_PER_LEG,
)

import numpy as np

# NIFTY options quote on a 0.05 tick. A close may sit a tick or two below
# intrinsic on a stale final print; beyond that it is a defect, not a spread.
TICK = 0.05
TOLERANCE_PTS = 4 * TICK


def floored_debit(cal, trades) -> dict:
    """Per-session 4-leg debit with any below-intrinsic leg floored at intrinsic.

    Direction of the bias matters: we are LONG the fly (short straddle, long
    wings), and fly value = ATM straddle - wings. A leg whose bhavcopy close is
    a stale EARLY print reads LOW, so the fly reads cheap and the book looks
    BETTER than it was. This correction can only remove PnL.
    """
    cols = ["symbol", "instrument", "expiry", "strike", "option_type", "close"]
    out, n_floored = {}, 0
    for t in trades:
        if t.debit_real is None:
            continue
        df = pd.read_parquet(cal[t.date], columns=cols)
        n = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")])
        c = n[n["expiry_date"] == t.front_expiry]
        f = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "FUTIDX")])
        fc = f[f["expiry_date"] == t.front_expiry]
        s = float(fc["close"].iloc[0]) if not fc.empty else t.spot_1230
        legs = {}
        for k, side in ((t.atm, "CE"), (t.atm, "PE"), (t.wing_ce, "CE"), (t.wing_pe, "PE")):
            q = c[(c["strike"] == float(k)) & (c["option_type"] == side)]
            if q.empty:
                legs = None
                break
            px = float(q.iloc[0]["close"])
            intrinsic = max(s - k, 0.0) if side == "CE" else max(k - s, 0.0)
            if intrinsic - px > TOLERANCE_PTS:
                n_floored += 1
                px = intrinsic
            legs[(k, side)] = px
        if legs:
            out[str(t.date)] = (legs[(t.atm, "CE")] + legs[(t.atm, "PE")]) - \
                               (legs[(t.wing_ce, "CE")] + legs[(t.wing_pe, "PE")])
    out["__floored_legs__"] = n_floored
    return out


def main() -> int:
    vol, _ = A._vol_frame()
    cal = build_bhavcopy_calendar()
    trades = collect_trades(vol, cal)

    cols = ["symbol", "instrument", "expiry", "strike", "option_type", "close", "contracts"]
    rows, breaches = [], []
    for t in trades:
        if t.debit_real is None:
            continue
        df = pd.read_parquet(cal[t.date], columns=cols)
        n = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")])
        c = n[n["expiry_date"] == t.front_expiry]
        # The mark's OWN clock, and the mark's OWN expiry. The bhavcopy option
        # close and the futures close for the SAME expiry are both struck at the
        # end of the session; the 15:15 5-min spot bar is 15 minutes earlier, and
        # the FRONT futures can be a different (monthly) expiry entirely, worth
        # hundreds of basis points. Using either makes a late sell-off look like
        # a broken print.
        f = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "FUTIDX")])
        fc = f[f["expiry_date"] == t.front_expiry]
        s = float(fc["close"].iloc[0]) if not fc.empty else t.spot_1230
        for k, side in ((t.atm, "CE"), (t.atm, "PE"), (t.wing_ce, "CE"), (t.wing_pe, "PE")):
            q = c[(c["strike"] == float(k)) & (c["option_type"] == side)]
            if q.empty:
                continue
            r = q.iloc[0]
            px, volc = float(r["close"]), int(r["contracts"])
            intrinsic = max(s - k, 0.0) if side == "CE" else max(k - s, 0.0)
            gap = intrinsic - px  # >0 means the close is BELOW intrinsic
            rows.append({"date": str(t.date), "strike": k, "side": side, "close": px,
                         "intrinsic": round(intrinsic, 2), "gap": round(gap, 2),
                         "contracts": volc, "dte": t.dte})
            if gap > TOLERANCE_PTS:
                breaches.append(rows[-1])

    df = pd.DataFrame(rows)
    print(f"legs checked: {len(df)} over {df.date.nunique()} sessions")
    print(f"closes below intrinsic (> {TOLERANCE_PTS} pts): {len(breaches)}")
    if breaches:
        print("\nworst offenders:")
        print(df.sort_values("gap", ascending=False).head(12).to_string(index=False))
        print(f"\nof which printed < 10,000 contracts: "
              f"{len(df[(df.gap > TOLERANCE_PTS) & (df.contracts < 10_000)])}")
        print(f"worst gap on a leg printing > 1M contracts: "
              f"{df[df.contracts > 1_000_000].gap.max():.2f}")
    print(f"\nmedian gap (all legs): {df.gap.median():.2f} pts")
    print(f"max gap among legs printing > 100k contracts: "
          f"{df[df.contracts > 100_000].gap.max():.2f} pts")

    # --- what flooring them at intrinsic costs -------------------------------
    print("\n--- correction: floor every below-intrinsic leg at intrinsic ---")
    floored = floored_debit(cal, trades)
    n_legs_floored = floored.pop("__floored_legs__")
    dfb = pd.read_csv(HERE / "artifacts" / "audit_trades.csv", parse_dates=["date"])
    dfb = dfb[dfb["mark_valid"] == True]  # noqa: E712
    dfb["debit_floored"] = [floored.get(str(d.date()) if hasattr(d, "date") else str(d), np.nan)
                            for d in dfb["date"]]
    for slip, label in ((MODELLED_PTS_PER_LEG, "0.75"), (CONSERVATIVE_PTS_PER_LEG, "2.00")):
        # `net_real` carries e013's modelled 0.75; re-base both sides to `slip`
        # so the comparison is like-for-like.
        shift = 8.0 * (MODELLED_PTS_PER_LEG - slip) * dfb.lot
        base = dfb["net_real"].sum() + shift.sum()
        adj = ((dfb.credit_pts - dfb.debit_floored) * dfb.lot
               - (dfb.friction - 8.0 * MODELLED_PTS_PER_LEG * dfb.lot) - 8.0 * slip * dfb.lot)
        print(f"  {label} pts/leg: as published Rs {base:>10,.0f} -> floored Rs {adj.sum():>10,.0f}"
              f"  (EV {adj.mean():>7,.0f}/trade)")
    print(f"  legs floored: {n_legs_floored} of {len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
