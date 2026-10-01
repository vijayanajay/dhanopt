"""Paper-trade harness for the breach book's 4-expiry-week gate (handoff §4.2).

The frozen backtest (breach_spread.py) inherited e001's day-t chain convention for
walls; the LIVE gate can only see the PRIOR session's bhavcopy. This harness is the
pre-live version of the same book:

  - walls = max-OI strikes of the t-1 partition (observable before 09:15);
  - signal = dte<=1 AND spot OPEN gapped over a wall -> SELL wall / BUY +-150 wing;
  - fills  = the day's real leg opens (09:15 snapshot, the sweep-validated marks);
  - exits  = 1.4x credit SL / 100%-of-credit target on the 5-min path (e005 sim).

"Realized slippage" before live fills exist is measured as MODELED FILL DRIFT: each
leg repriced at BS (its own open-backed IV) on the 09:20 spot — i.e. what a fill 5
minutes late would cost in points. The gate report compares max drift per leg against
the friction model (1.5 pts/leg) and the 12x monthly-DD boundary (18.0 pts/leg, §3),
plus a stressed re-simulation with ADVERSE fills (sell lower / buy higher by |drift|).
Once paper trading starts, the same rows carry real fills instead.

Run: python -m experiments.e005_theta_condor.paper_trade [--gate-weeks 4] [--context-weeks 26] [--full]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from experiments.e005_theta_condor.replay_theta import (
    ARTIFACTS, WING_OFFSET, _chain_view, _implied_iv_safe, _partition_calendar,
    _safe_exp, _bs_ltp, simulate_theta_condor)
from core.feeds.intraday import available_dates, load_intraday_candles
from experiments.common.lots import lot_for_date

MODEL_PTS_PER_LEG = 1.5      # config.SLIPPAGE_POINTS_PER_LEG (friction model)
BOUNDARY_PTS_PER_LEG = 12 * MODEL_PTS_PER_LEG  # 18.0 — monthly-DD cap breach at ~12x (§3)
STAGE2_TRIGGER_PTS = 5 * MODEL_PTS_PER_LEG     # 7.5 — handoff §5 stage-2 slippage trigger

ROW_COLUMNS = ["date", "signal", "side", "wall", "wing", "spot_open", "dte0",
               "sell_open", "buy_open", "credit_pts", "drift_sell", "drift_buy",
               "max_leg_drift", "exit_reason", "net_pnl", "net_pnl_stressed",
               "lot", "expiry"]


def _px_map(df: pd.DataFrame, col: str) -> Dict:
    """First positive price per (strike, option_type) — e001's _ohlc_at convention
    (copied from prepare_day's nested helper; strike keys collide across PE/CE)."""
    m: Dict = {}
    for _, r in df.iterrows():
        k = (float(r["strike"]), str(r["option_type"]))
        if k not in m and float(r[col]) > 0:
            m[k] = float(r[col])
    return m


def _prev_session_map(dates: List) -> Dict:
    """trade date -> previous trade date (bhavcopy partitions define sessions)."""
    ds = sorted(dates)
    return {ds[i]: ds[i - 1] for i in range(1, len(ds))}


def _walls_from_partition(df: pd.DataFrame, on_or_after: date):
    """Max-OI put/call walls of the nearest expiry in a partition (e001 convention)."""
    nifty = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["OPTIDX", "IDO"]))]
    exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= on_or_after]
    if not exps:
        return None, None
    pe, ce = _chain_view(nifty, min(exps))
    if pe.empty or ce.empty:
        return None, None
    return float(pe.loc[pe["open_interest"].idxmax(), "strike"]), \
        float(ce.loc[ce["open_interest"].idxmax(), "strike"])


def evaluate_day(d, cal: Dict, prev_map: Dict) -> dict:
    """One day through the live gate. Returns a fixed-schema row (signal in
    TRADE / STANDDOWN / DTE_HOLD / NOFILL / SKIP_CREDIT / NODATA)."""
    ts = pd.Timestamp(d)
    d_date = ts.date()
    row = {c: None for c in ROW_COLUMNS}
    row.update({"date": ts.isoformat(), "signal": "NODATA"})

    try:
        candles = load_intraday_candles(d)
    except FileNotFoundError:
        return row
    own_path, prev_date = cal.get(d_date), prev_map.get(d_date)
    if own_path is None or prev_date is None:
        return row

    put_wall, call_wall = _walls_from_partition(pd.read_parquet(cal[prev_date]), d_date)
    if put_wall is None:
        return row
    row.update({"put_wall_t1": put_wall, "call_wall_t1": call_wall})

    own_df = pd.read_parquet(own_path)
    nifty = own_df[(own_df["symbol"] == "NIFTY") & (own_df["instrument"].isin(["OPTIDX", "IDO"]))]
    exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= d_date]
    if not exps:
        return row
    expiry = min(exps)
    dte0 = max((expiry - d_date).days, 0.5)
    spot_open = float(candles.iloc[0]["open"])

    if call_wall <= spot_open:
        side = "call"
    elif put_wall >= spot_open:
        side = "put"
    else:
        row.update({"signal": "STANDDOWN", "side": "none", "spot_open": spot_open,
                    "dte0": dte0, "expiry": expiry.isoformat(),
                    "wall": None if dte0 > 1 else (call_wall if call_wall - spot_open <= spot_open - put_wall else put_wall)})
        return row
    if dte0 > 1.0:
        row.update({"signal": "DTE_HOLD", "side": side, "wall": call_wall if side == "call" else put_wall,
                    "spot_open": spot_open, "dte0": dte0, "expiry": expiry.isoformat()})
        return row

    wall = call_wall if side == "call" else put_wall
    wing = wall + WING_OFFSET if side == "call" else wall - WING_OFFSET
    is_call = side == "call"
    ot = "CE" if is_call else "PE"
    pe, ce = _chain_view(own_df, expiry)
    open_map = _px_map(pd.concat([pe, ce]), "open")
    exit_map = _px_map(pd.concat([pe, ce]), "close")
    sell_open, buy_open = open_map.get((float(wall), ot)), open_map.get((float(wing), ot))
    exits = [exit_map.get((float(wall), ot)), exit_map.get((float(wing), ot))]
    if sell_open is None or buy_open is None or any(e is None for e in exits):
        row.update({"signal": "NOFILL", "side": side, "wall": wall, "wing": wing,
                    "spot_open": spot_open, "dte0": dte0, "expiry": expiry.isoformat()})
        return row
    credit_pts = sell_open - buy_open
    if credit_pts <= 0:
        row.update({"signal": "SKIP_CREDIT", "side": side, "wall": wall, "wing": wing,
                    "spot_open": spot_open, "dte0": dte0, "sell_open": sell_open,
                    "buy_open": buy_open, "credit_pts": round(credit_pts, 2),
                    "expiry": expiry.isoformat()})
        return row

    # Modeled fill drift: leg repriced at BS(own open-backed IV) on the 09:20 spot.
    spot_0920 = float(candles.iloc[0]["close"])
    drifts = []
    for px, strike in ((sell_open, wall), (buy_open, wing)):
        iv = _implied_iv_safe(spot_open, float(strike), is_call, px, dte0)
        drifts.append(_bs_ltp(spot_0920, float(strike), is_call, iv, dte0) - px)
    drift_sell, drift_buy = drifts

    legs2 = [{"strike": float(wall), "is_call": is_call, "action": "SELL"},
             {"strike": float(wing), "is_call": is_call, "action": "BUY"}]
    qty = lot_for_date(d_date)
    sim = simulate_theta_condor(candles, legs2, [sell_open, buy_open], exits, qty, dte0, spot_open,
                                target_frac=1.0)
    # Adverse-fill stress: SELL fills |drift| lower, BUY fills |drift| higher.
    stressed = simulate_theta_condor(
        candles, legs2, [sell_open - abs(drift_sell), buy_open + abs(drift_buy)], exits,
        qty, dte0, spot_open, target_frac=1.0)

    row.update({"signal": "TRADE", "side": side, "wall": wall, "wing": wing,
                "spot_open": spot_open, "dte0": dte0, "sell_open": sell_open,
                "buy_open": buy_open, "credit_pts": round(credit_pts, 2),
                "drift_sell": round(drift_sell, 2), "drift_buy": round(drift_buy, 2),
                "max_leg_drift": round(max(abs(drift_sell), abs(drift_buy)), 2),
                "exit_reason": sim["exit_reason"], "net_pnl": sim["net_pnl"],
                "net_pnl_stressed": stressed["net_pnl"], "lot": qty,
                "expiry": expiry.isoformat()})
    return row


def evaluate_days(dates: List, cal: Dict, prev_map: Dict) -> pd.DataFrame:
    rows = [evaluate_day(d, cal, prev_map) for d in dates]
    return pd.DataFrame(rows, columns=ROW_COLUMNS + ["put_wall_t1", "call_wall_t1"])


def gate_report(rows: pd.DataFrame, gate_weeks: int) -> dict:
    trades = rows[rows["signal"] == "TRADE"].copy()
    out = {"n_days_evaluated": int(len(rows)),
           "signals": rows["signal"].value_counts().to_dict()}
    if len(trades):
        out["n_trades"] = len(trades)
        out["net"] = round(float(trades["net_pnl"].sum()), 0)
        out["net_stressed"] = round(float(trades["net_pnl_stressed"].sum()), 0)
        out["wr"] = round(float((trades["net_pnl"] > 0).mean()), 3)
        out["max_leg_drift_pts"] = {"mean": round(float(trades["max_leg_drift"].mean()), 2),
                                    "p95": round(float(trades["max_leg_drift"].quantile(0.95)), 2),
                                    "max": round(float(trades["max_leg_drift"].max()), 2)}
        out["boundary_pts_per_leg"] = BOUNDARY_PTS_PER_LEG
        out["model_pts_per_leg"] = MODEL_PTS_PER_LEG
        worst = trades.loc[trades["max_leg_drift"].idxmax()]
        out["worst_drift_day"] = {"date": worst["date"], "pts": float(worst["max_leg_drift"])}
        out["within_12x_boundary"] = bool(trades["max_leg_drift"].max() < BOUNDARY_PTS_PER_LEG)
        out["within_stage2_trigger"] = bool(trades["max_leg_drift"].quantile(0.95) < STAGE2_TRIGGER_PTS)
    # Gate window = the most recent `gate_weeks` sessions present in the log.
    recent = rows.dropna(subset=["date"]).tail(gate_weeks * 5)
    gt = recent[recent["signal"] == "TRADE"]
    out["gate_window"] = {"weeks": gate_weeks, "n_trades": len(gt),
                          "net": round(float(gt["net_pnl"].sum()), 0) if len(gt) else 0.0,
                          "trades": gt[["date", "side", "wall", "credit_pts", "max_leg_drift",
                                        "exit_reason", "net_pnl", "net_pnl_stressed"]].to_dict("records")}
    return out


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="Breach-book paper-trade harness (t-1 walls)")
    ap.add_argument("--gate-weeks", type=int, default=4)
    ap.add_argument("--context-weeks", type=int, default=26)
    ap.add_argument("--full", action="store_true", help="evaluate the whole stored window")
    args = ap.parse_args()

    dates = available_dates()
    if not dates:
        print("No intraday partitions found.")
        return 1
    if not args.full:
        cutoff = max(dates) - timedelta(weeks=args.context_weeks)
        dates = [d for d in dates if d >= cutoff]
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    prev_map = _prev_session_map(cal.keys())

    print(f"evaluating {len(dates)} sessions through the t-1-wall gate...")
    rows = evaluate_days(dates, cal, prev_map)
    rows.to_csv(ARTIFACTS / "paper_trade.csv", index=False)

    rep = gate_report(rows, args.gate_weeks)
    print(f"\nsignals: {rep['signals']}")
    if "n_trades" in rep:
        print(f"trades: n={rep['n_trades']} net={rep['net']:,.0f} (stressed {rep['net_stressed']:,.0f}) "
              f"wr={rep['wr']}")
        d = rep["max_leg_drift_pts"]
        print(f"fill drift pts/leg: mean={d['mean']} p95={d['p95']} max={d['max']} "
              f"vs model {MODEL_PTS_PER_LEG} / 12x boundary {BOUNDARY_PTS_PER_LEG}")
        print(f"within 12x boundary: {rep['within_12x_boundary']} | "
              f"p95 within stage-2 trigger (7.5): {rep['within_stage2_trigger']}")
    g = rep["gate_window"]
    print(f"gate window ({g['weeks']}w): {g['n_trades']} trades, net {g['net']:,.0f}")
    for t in g["trades"]:
        print(f"  {t['date']} {t['side']:>4} wall {t['wall']:.0f} credit {t['credit_pts']} "
              f"drift {t['max_leg_drift']} -> {t['exit_reason']} net {t['net_pnl']} "
              f"(stressed {t['net_pnl_stressed']})")

    # Honest compare: same dates under the frozen day-t-wall book, where they overlap.
    trades = rows[rows["signal"] == "TRADE"]
    ref = ARTIFACTS / "breach_spread_target_100.csv"
    if ref.exists():
        b = pd.read_csv(ref)
        b["date"] = b["date"].str[:10]
        common = trades[trades["date"].isin(set(b["date"]))] if "n_trades" in rep else trades.head(0)
        if len(common):
            ref_net = float(b[b["date"].isin(set(common["date"]))]["net_pnl"].sum())
            rep["t1_vs_dayt_walls"] = {"common_trades": len(common),
                                       "net_t1": round(float(common["net_pnl"].sum()), 0),
                                       "net_dayt": round(ref_net, 0)}
            print(f"\nt-1 walls vs day-t walls on {len(common)} common trades: "
                  f"{rep['t1_vs_dayt_walls']['net_t1']:,.0f} vs {ref_net:,.0f}")

    with open(ARTIFACTS / "paper_trade.json", "w") as f:
        json.dump(rep, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'paper_trade.json'}, {ARTIFACTS / 'paper_trade.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
