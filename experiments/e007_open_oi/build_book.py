"""e007 Phase B: gate-0 certification — rebuild the breach book on OPENING-OI walls.

The frozen breach book's walls are day-t EOD OI (6h of look-ahead; e005 Add. 8).
This book keeps everything else frozen — day-t real leg opens/exits, 2-leg pair,
1.4x SL / 100% target on the 5-min path, era lots — and changes ONLY the wall
source to the walls as they stood AT 09:15 (from fetch_open_oi's per-bar OI).

Certification bars (handoff §7, gate 0) on the certified subset:
  PF >= 5, WR >= 85%, net >= 40% of the frozen book's net (+940,697 -> +376,279).
Days the opening gate stands down on (walls valid at open) contribute 0 — the live
book simply doesn't trade them. Coverage < 80% of the 249 days makes the verdict
WEAK regardless of the bars.

Run: python -m experiments.e007_open_oi.build_book
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from experiments.e007_open_oi.fetch_open_oi import ARTIFACTS as E007_ARTIFACTS, CHECKPOINT
from experiments.e005_theta_condor.paper_trade import _px_map
from experiments.e005_theta_condor.replay_theta import (
    WING_OFFSET, _chain_view, _partition_calendar, _safe_exp, simulate_theta_condor)
from core.feeds.intraday import available_dates, load_intraday_candles
from experiments.common.lots import lot_for_date

HERE = Path(__file__).resolve().parent
BREACH_CSV = HERE.parent / "e005_theta_condor" / "artifacts" / "breach_spread_target_100.csv"
FROZEN_NET = 940_697.0
BARS = {"pf_min": 5.0, "wr_min": 0.85, "net_min_frac": 0.40, "coverage_min_frac": 0.80}


def _opening_walls(entry: dict):
    """(put_wall, call_wall, n_with_oi, n_strikes) from a fetched opening chain."""
    pe = [(r["strike"], r["oi_open"]) for r in entry["opening"]
          if r["side"] == "PE" and r.get("oi_open") is not None]
    ce = [(r["strike"], r["oi_open"]) for r in entry["opening"]
          if r["side"] == "CE" and r.get("oi_open") is not None]
    if not pe or not ce:
        return None, None, len(pe) + len(ce), len(entry["opening"])
    return (max(pe, key=lambda x: x[1])[0], max(ce, key=lambda x: x[1])[0],
            len(pe) + len(ce), len(entry["opening"]))


def trade_day(d, opening_entry: dict, own_df: pd.DataFrame, candles: pd.DataFrame,
              frozen_side: str) -> dict:
    """One day through the opening-wall gate. Walls from opening OI; prices from day-t."""
    ts = pd.Timestamp(d)
    d_date = ts.date() if hasattr(d, "date") else d
    row = {"date": ts.isoformat(), "signal": "NODATA", "side": None, "wall": None,
           "wing": None, "credit_pts": None, "exit_reason": None,
           "net_pnl": 0.0, "net_pnl_stressed": None, "agree_frozen": None}
    put_w, call_w, n_oi, n_all = _opening_walls(opening_entry)
    row["n_opening_oi"], row["n_opening_strikes"] = n_oi, n_all
    if put_w is None:
        row["signal"] = "NO_CHAIN"
        return row
    spot_open = float(candles.iloc[0]["open"])
    exps = [x for x in (_safe_exp(e) for e in own_df["expiry"].unique()) if x and x >= d_date]
    if not exps:
        row["signal"] = "NO_CHAIN"
        return row
    expiry = min(exps)
    dte0 = max((expiry - d_date).days, 0.5)
    if dte0 > 1.0:
        row["signal"] = "DTE_HOLD"
        return row
    if call_w <= spot_open:
        side = "call"
    elif put_w >= spot_open:
        side = "put"
    else:
        row["signal"] = "STANDDOWN"
        row["agree_frozen"] = frozen_side is None
        return row
    row["agree_frozen"] = (side == frozen_side)
    wall = call_w if side == "call" else put_w
    wing = wall + WING_OFFSET if side == "call" else wall - WING_OFFSET
    is_call = side == "call"
    ot = "CE" if is_call else "PE"
    pe, ce = _chain_view(own_df, expiry)
    open_map = _px_map(pd.concat([pe, ce]), "open")
    exit_map = _px_map(pd.concat([pe, ce]), "close")
    sell_open, buy_open = open_map.get((float(wall), ot)), open_map.get((float(wing), ot))
    exits = [exit_map.get((float(wall), ot)), exit_map.get((float(wing), ot))]
    if sell_open is None or buy_open is None or any(e is None for e in exits):
        row["signal"] = "NOFILL"
        row.update({"side": side, "wall": wall, "wing": wing})
        return row
    credit_pts = sell_open - buy_open
    if credit_pts <= 0:
        row["signal"] = "SKIP_CREDIT"
        row.update({"side": side, "wall": wall, "wing": wing, "credit_pts": round(credit_pts, 2)})
        return row
    legs2 = [{"strike": float(wall), "is_call": is_call, "action": "SELL"},
             {"strike": float(wing), "is_call": is_call, "action": "BUY"}]
    qty = lot_for_date(d_date)
    sim = simulate_theta_condor(candles, legs2, [sell_open, buy_open], exits, qty,
                                dte0, spot_open, target_frac=1.0)
    row.update({"signal": "TRADE", "side": side, "wall": wall, "wing": wing,
                "credit_pts": round(credit_pts, 2), "exit_reason": sim["exit_reason"],
                "net_pnl": sim["net_pnl"], "dte0": dte0})
    return row


def main() -> int:
    import config

    cp = json.loads(CHECKPOINT.read_text())
    bs = pd.read_csv(BREACH_CSV)
    bs["d"] = pd.to_datetime(bs["date"]).dt.strftime("%Y-%m-%d")
    frozen_side = dict(zip(bs["d"], bs["side"]))
    frozen_net = dict(zip(bs["d"], bs["net_pnl"]))

    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    dates = sorted(set(available_dates()))
    rows: List[dict] = []
    for d in dates:
        key = str(d)[:10]
        if key not in frozen_side:
            continue  # certification applies to the frozen book's 249 days
        entry = cp.get(key)
        if entry is None or entry.get("status") != "OK":
            rows.append({"date": key, "signal": "NOT_FETCHED", "net_pnl": 0.0})
            continue
        try:
            candles = load_intraday_candles(d)
        except FileNotFoundError:
            rows.append({"date": key, "signal": "NODATA", "net_pnl": 0.0})
            continue
        own_path = cal.get(pd.Timestamp(d).date() if hasattr(d, "date") else d)
        if own_path is None:
            rows.append({"date": key, "signal": "NODATA", "net_pnl": 0.0})
            continue
        row = trade_day(d, entry, pd.read_parquet(own_path), candles, frozen_side.get(key))
        row["frozen_net"] = frozen_net.get(key)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("date")
    df.to_csv(E007_ARTIFACTS / "book_opening_walls.csv", index=False)

    cert = df[df["signal"].isin(["TRADE", "STANDDOWN", "NOFILL", "SKIP_CREDIT", "DTE_HOLD"])]
    trades = df[df["signal"] == "TRADE"]
    gp = trades.loc[trades.net_pnl > 0, "net_pnl"].sum()
    gl = abs(trades.loc[trades.net_pnl <= 0, "net_pnl"].sum())
    net = float(trades["net_pnl"].sum())
    wr = float((trades["net_pnl"] > 0).mean()) if len(trades) else 0.0
    pf = float(gp / gl) if gl else float("inf")
    agree = df["agree_frozen"].dropna()
    coverage = len(cert) / len(df) if len(df) else 0.0
    verdict = {
        "n_frozen_days": len(df), "n_certified": len(cert), "coverage": round(coverage, 3),
        "n_trades": len(trades), "n_stood_down": int((df["signal"] == "STANDDOWN").sum()),
        "n_nofill": int((df["signal"] == "NOFILL").sum()),
        "side_agreement_with_frozen": round(float(agree.mean()), 3) if len(agree) else None,
        "net": round(net, 0), "wr": round(wr, 3), "pf": round(pf, 2),
        "frozen_net_same_days": round(float(df["frozen_net"].dropna().sum()), 0),
        "bars": BARS,
        "pass_pf": bool(pf >= BARS["pf_min"]), "pass_wr": bool(wr >= BARS["wr_min"]),
        "pass_net": bool(net >= BARS["net_min_frac"] * FROZEN_NET),
        "pass_coverage": bool(coverage >= BARS["coverage_min_frac"]),
    }
    verdict["gate0"] = ("PASS" if (verdict["pass_pf"] and verdict["pass_wr"] and verdict["pass_net"]
                                   and verdict["pass_coverage"]) else "FAIL")
    with open(E007_ARTIFACTS / "gate0.json", "w") as f:
        json.dump(verdict, f, indent=2, default=str)

    print(f"certified subset: {len(cert)}/{len(df)} days (coverage {coverage:.0%})")
    print(f"opening-wall book: {len(trades)} trades | net {net:,.0f} | wr {wr:.3f} | pf {pf:.2f}")
    print(f"stand-downs: {verdict['n_stood_down']} | nofill: {verdict['n_nofill']} | "
          f"side agreement with frozen: {verdict['side_agreement_with_frozen']}")
    print(f"frozen book net on the same days: {verdict['frozen_net_same_days']:,.0f}")
    print(f"GATE 0: {verdict['gate0']} "
          f"(pf {pf:.2f}>={BARS['pf_min']}? {verdict['pass_pf']} | "
          f"wr {wr:.3f}>={BARS['wr_min']}? {verdict['pass_wr']} | "
          f"net {net:,.0f}>={BARS['net_min_frac']*FROZEN_NET:,.0f}? {verdict['pass_net']} | "
          f"coverage {coverage:.0%}>={BARS['coverage_min_frac']:.0%}? {verdict['pass_coverage']})")
    print(f"written: {E007_ARTIFACTS / 'gate0.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
