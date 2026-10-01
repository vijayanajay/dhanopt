"""E006: the breach-only book under LIVE constraints — compounding, circuit breakers, sizing.

The handoff's +₹940k/83%-yr headline is a flat 1 lot with no compounding and no risk
caps. Before stage-1 capital goes in, this answers the reviewer's real question: what
does the book do on the ₹2,00,000 account WITH config's monthly DD circuit-breaker and
a margin-aware 1→2-lot ladder?

Mechanics (frozen here, no tuning):
- Bankroll starts at config.TOTAL_CAPITAL. Trades replay chronologically from
  breach_spread_target_100.csv (SL 1.4×, target 100% of credit, era-correct lots).
- Ladder: 1 lot while cash < L2, 2 lots when cash ≥ L2, demoted back automatically
  (defined-risk spread margin releases at settlement, no hysteresis).
  L2 = 2 × ~₹10k/lot spread margin + 1 month's DD-cap headroom (₹10k) = ₹30,000 —
  the margin figure is the handoff's broker-calculator estimate, flagged for verify.
- Daily-loss kill: config.MAX_DAILY_LOSS is a HARD STOP — when a day's realized loss
  breaches the cap, the position is flattened and the day loses exactly the cap.
  The sim clamps the trade's net at −MAX_DAILY_LOSS (daily CSV cannot see the
  intraday bar where the cap fires; # ponytail: clamping assumes the flatten fills
  AT the cap — gap-through days would lose a bit more; the 5-min replay is the
  upgrade path).
- Monthly circuit breaker: if realized losses within the month breach
  config.MONTHLY_DRAWDOWN_CAP, no more trades that calendar month. # ponytail: the
  cap is enforced as monthly peak-to-trough on realized cash INCLUDING 2-lot charges,
  which kills more trades than a daily-realized-loss reading — conservative; the live
  broker semantics (when the counter resets) are unwritten and must be pinned before
  go-live.
- No compounding of size beyond the ladder (margin arithmetic, not Kelly).

Run: python -m experiments.e006_compound_sim.compound_sim
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from experiments.common.lots import lot_for_date
from experiments.e005_theta_condor.replay_theta import ARTIFACTS as E005_ARTIFACTS
from experiments.e005_theta_condor.target_sweep import stats

HERE = Path(__file__).resolve().parent
OUT = HERE / "artifacts"
BREACH_CSV = E005_ARTIFACTS / "breach_spread_target_100.csv"

MARGIN_PER_LOT = 10_000.0   # defined-risk spread margin, per handoff — verify with broker calc
L2_THRESHOLD = 2 * MARGIN_PER_LOT + 10_000.0  # 2-lot margin + one DD-cap of headroom


def simulate(df: pd.DataFrame, start_capital: float, enable_ladder: bool,
             enable_breaker: bool, l2_threshold: float = L2_THRESHOLD,
             margin_per_lot: float = MARGIN_PER_LOT) -> dict:
    import config

    d = df.sort_values("date").copy()
    d["month"] = d["date"].str[:7]
    cash = start_capital
    lots = 1
    month_peak = cash
    breaker_trips = 0
    killed_daily = 0
    killed_breaker = 0
    trades_at_2 = 0
    first_2 = last_2 = None
    curve = []
    rows = []
    first_date = str(d["date"].iloc[0])
    curve.append({"date": first_date, "month": "", "cash": cash})  # anchor: DD counts from start

    for _, t in d.iterrows():
        if t["month"] != (curve[-1]["month"] if curve else ""):
            month_peak = cash  # new month: breaker window resets
        skip = None
        if enable_ladder:
            want = 2 if cash >= l2_threshold else 1
            if want != lots:
                lots = want
        if enable_breaker and cash < month_peak - config.MONTHLY_DRAWDOWN_CAP:
            skip = "BREAKER"
        if skip is not None:
            killed_breaker += 1
            rows.append({"date": t["date"], "lots": 0, "skip": skip, "net": 0.0})
            curve.append({"date": t["date"], "month": t["month"], "cash": cash})
            continue

        # CSV pnl is per 1 lot (= era_lot contracts); the ladder multiplies the LOT count
        pnl = float(t["net_pnl"]) * lots
        if enable_breaker and pnl < -config.MAX_DAILY_LOSS:
            pnl = -float(config.MAX_DAILY_LOSS)  # hard daily stop: flatten at the cap
            killed_daily += 1
        if lots == 2:
            trades_at_2 += 1
            if first_2 is None:
                first_2 = t["date"]
            last_2 = t["date"]
        cash += pnl
        month_peak = max(month_peak, cash)
        rows.append({"date": t["date"], "lots": lots, "skip": "", "net": pnl})
        curve.append({"date": t["date"], "month": t["month"], "cash": cash})

    eq = pd.Series([c["cash"] for c in curve], index=pd.to_datetime([c["date"] for c in curve]))
    max_dd = float(eq.cummax().sub(eq).max())
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / start_capital) ** (1 / years) - 1 if years > 0 else 0.0
    return {
        "start_capital": start_capital, "end_cash": round(float(eq.iloc[-1]), 0),
        "cagr_pct": round(100 * cagr, 1), "max_dd": round(max_dd, 0),
        "max_dd_pct": round(-100 * max_dd / start_capital, 1),
        "n_trades_taken": int((pd.DataFrame(rows)["lots"] > 0).sum()),
        "n_skipped_daily_kill": killed_daily, "n_skipped_breaker": killed_breaker,
        "breaker_trips": breaker_trips if enable_breaker else 0,
        "trades_at_2_lots": trades_at_2, "first_2lot": first_2, "last_2lot": last_2,
        "l2_threshold": l2_threshold, "years": round(years, 2),
    }, rows, curve


def main() -> int:
    import config

    df = pd.read_csv(BREACH_CSV)
    df["date"] = df["date"].str[:10]

    out = {}
    flat, flat_rows, flat_curve = simulate(df, config.TOTAL_CAPITAL, enable_ladder=False,
                                           enable_breaker=False)
    out["flat_1_lot"] = flat
    scaled, rows, curve = simulate(df, config.TOTAL_CAPITAL, enable_ladder=True,
                                   enable_breaker=True)
    out["live_constraints"] = scaled
    # isolate the breaker's cost: ladder on, breaker off
    nobreak, _, _ = simulate(df, config.TOTAL_CAPITAL, enable_ladder=True,
                             enable_breaker=False)
    out["ladder_only"] = nobreak

    # arithmetic reference: same trades, constant 2 lots, no constraints (upper bound)
    eq2 = config.TOTAL_CAPITAL + (2 * df["net_pnl"]).cumsum()
    dd2 = float(eq2.cummax().sub(eq2).max())
    yrs = (pd.to_datetime(df["date"].iloc[-1]) - pd.to_datetime(df["date"].iloc[0])).days / 365.25
    out["flat_2_lot_reference"] = {
        "start_capital": config.TOTAL_CAPITAL, "end_cash": round(float(eq2.iloc[-1]), 0),
        "cagr_pct": round(100 * ((eq2.iloc[-1] / config.TOTAL_CAPITAL) ** (1 / yrs) - 1), 1),
        "max_dd": round(dd2, 0), "max_dd_pct": round(-100 * dd2 / config.TOTAL_CAPITAL, 1),
        "n_trades_taken": len(df), "n_skipped_daily_kill": 0, "n_skipped_breaker": 0,
        "trades_at_2_lots": len(df), "first_2lot": None, "last_2lot": None,
        "l2_threshold": None, "years": round(yrs, 2),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compound_sim.json").write_text(json.dumps(out, indent=2, default=str))
    pd.DataFrame(rows).to_csv(OUT / "compound_sim_trades.csv", index=False)

    for name, s in out.items():
        print(f"{name:22s} end {s['end_cash']:>11,.0f}  CAGR {s['cagr_pct']:>6.1f}%  "
              f"maxDD {s['max_dd']:>8,.0f} ({s['max_dd_pct']}%)  trades {s['n_trades_taken']}"
              + (f"  2-lot {s['trades_at_2']}" if "trades_at_2" in s and s["trades_at_2"] else ""))
    s = out["live_constraints"]
    print(f"\nlive constraints: {s['n_skipped_daily_kill']} daily-stop clamps, "
          f"{s['n_skipped_breaker']} breaker-month skips; "
          f"2 lots from {s['first_2lot']} to {s['last_2lot']}")
    print(f"written: {OUT / 'compound_sim.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
