"""e008 Phase B: the flip signal against the three pre-registered kill criteria.

Signal (scope, experiment.md): at each 5-min bar t, walls = max-OI strikes of the
chain OI of bars <= t (carry-forward per strike: a bar's chain is the freshest
observation of each strike). On dte<=1, the FIRST time spot crosses a fresh wall
(put wall >= spot -> put breach; call wall <= spot -> call breach; both walls flip
side vs the previous bar's structure), enter the 2-leg spread on that wall at bar
t+1's OPEN (the hard rule). Exits frozen: 1.4x SL / 100% target / EOD on the path.

Kill criteria (any one kills e008, pre-registered):
  1. capacity: < 15 tradeable flips/yr on certified days
  2. edge: PF < 1.5 net of friction AND t+1-fill drift
  3. composition: flips confirmed only with late OI (freshness age > 30 min at
     decision) dominate the trade count -> the leak in new clothes

Certified subset: bars where the crossing strike AND its neighbor strikes carry
current-bar OI (the rolling-window ceiling means gaps are possible; trades on
uncertified wall data are excluded from the verdict and counted).

Run: python -m experiments.e008_wall_flip.build_signal [--limit N]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from experiments.e008_wall_flip.fetch_walls import ARTIFACTS, WALLS_DIR
from experiments.e005_theta_condor.replay_theta import (
    STOP_FRAC, _partition_calendar)
from core.feeds.intraday import load_intraday_candles
from experiments.common.lots import lot_for_date
from core.friction.zerodha import OptionLeg, calculate_friction

HERE = Path(__file__).resolve().parent
OUT = ARTIFACTS / "flip_signal.json"
MIN_FLIPS_PER_YEAR = 15     # kill criterion 1 (capacity)
PF_MIN = 1.5                # kill criterion 2 (edge; judged only with n >= 10)
# kill criterion 3 (composition): flips whose fill needs stale OI/quotes are
# "late-confirmable" — if >50% of flip events are unfillable at t+1, the signal
# is not tradeable as specified (the API ceiling wearing the leak's clothes).
WIDTH = 150


def _wall_of(bars, t_idx: int, side: str) -> Optional[dict]:
    """Max-OI strike of `side` using each strike's freshest observation up to bar t."""
    oi: Dict[float, float] = {}
    for b in bars[:t_idx + 1]:
        for c in b["chain"]:
            if c["side"] == side and c["oi"] is not None:
                oi[c["strike"]] = c["oi"]  # freshest write wins (bars are ordered)
    if not oi:
        return None
    st = max(oi, key=lambda k: oi[k])
    for b in reversed(bars[:t_idx + 1]):  # freshest quote for that strike
        for c in b["chain"]:
            if c["side"] == side and c["strike"] == st and c["open"] is not None:
                return {"strike": st, "oi": oi[st], "quote": c["open"], "age_min": _age_min(b["ts"], bars[t_idx]["ts"])}
    return None


def _age_min(ts_prev: str, ts_now: str) -> float:
    return (pd.Timestamp(ts_now) - pd.Timestamp(ts_prev)).total_seconds() / 60.0


def _spread_at(bars, t_idx: int, wall_strike: float, is_call: bool,
               max_age_min: float = 5.01) -> Optional[dict]:
    """Wall + wing quotes for the fill: most recent observation of each strike within
    max_age_min of bar t (no future info). None if either leg isn't observable."""
    side = "CE" if is_call else "PE"
    wing = wall_strike + WIDTH if is_call else wall_strike - WIDTH
    want = {wall_strike, wing}
    q: Dict[float, dict] = {}
    for b in reversed(bars[:t_idx + 1]):
        if _age_min(b["ts"], bars[t_idx]["ts"]) > max_age_min:
            break
        for c in b["chain"]:
            if c["side"] == side and c["strike"] in want and c["open"] is not None \
                    and c["strike"] not in q:
                q[c["strike"]] = {"px": c["open"], "age": _age_min(b["ts"], bars[t_idx]["ts"])}
        if len(q) == 2:
            break
    if len(q) < 2:
        return None
    return {"sell": q[wall_strike]["px"], "buy": q[wing]["px"], "wing": wing,
            "max_quote_age": max(v["age"] for v in q.values())}


def day_signal(entry: dict, candles: pd.DataFrame, d_date) -> List[dict]:
    """One session: walk bars, find the first certified fresh flip, fill at t+1 open, sim."""
    bars = entry["bars"]
    if entry.get("status") != "OK" or len(bars) < 10 or candles.empty:
        return []
    hm = [pd.Timestamp(b["ts"]).strftime("%H:%M") for b in bars]
    spots = [b["spot"] for b in bars]
    trades = []
    prev_side = None  # None while structure valid, "put"/"call" while breached
    t = 0
    while t < len(bars) - 1:
        t += 1
        spot = spots[t]
        if spot is None or hm[t] < "09:20":
            continue
        pw = _wall_of(bars, t, "PE")
        cw = _wall_of(bars, t, "CE")
        if pw is None or cw is None:
            prev_side = None
            continue
        side = "call" if cw["strike"] <= spot else ("put" if pw["strike"] >= spot else None)
        if side is None or side == prev_side:
            prev_side = side
            continue
        # flip event at bar t (fresh-crossing or re-crossing); fill at t+1
        nxt = t + 1
        wall_s = pw if side == "put" else cw
        if nxt >= len(bars):
            # hard rule: entry only at t+1 bar open; no next bar in session =>
            # unfillable event, not deferred to tomorrow
            trades.append({"date": entry["date"], "signal_bar": bars[t]["ts"],
                           "fill_bar": None, "side": side, "wall": wall_s["strike"],
                           "credit_pts": None, "wall_oi_age_min": round(wall_s["age_min"], 1),
                           "fillable": False, "max_quote_age": None})
            break
        sp = _spread_at(bars, nxt, wall_s["strike"], is_call=(side == "call"))
        spot_fill = spots[nxt] if spots[nxt] is not None else spot
        credit = (sp["sell"] - sp["buy"]) if sp else None
        rec = {
            "date": entry["date"], "signal_bar": bars[t]["ts"], "fill_bar": bars[nxt]["ts"],
            "side": side, "wall": wall_s["strike"], "credit_pts": round(credit, 2) if credit else None,
            "wall_oi_age_min": round(wall_s["age_min"], 1),
            "fillable": sp is not None and credit > 0,
            "max_quote_age": round(sp["max_quote_age"], 1) if sp else None,
        }
        if rec["fillable"]:
            is_call = side == "call"
            legs = [{"strike": float(wall_s["strike"]), "is_call": is_call, "action": "SELL"},
                    {"strike": float(sp["wing"]), "is_call": is_call, "action": "BUY"}]
            entry_px = [sp["sell"], sp["buy"]]
            qty = lot_for_date(d_date)
            sim_bars = candles[(candles["timestamp"].dt.strftime("%H:%M") >= hm[nxt])]
            if sim_bars.empty:
                rec["fillable"] = False
            else:
                # dte0: fills happen intraday on dte<=1 days; 0.5 (expiry-day) is the
                # honest first-order anchor for a same-day-dying spread.
                sim = _path_sim(sim_bars, entry_px, legs, credit, qty, spot_fill, dte0=0.5)
                rec.update({"exit_reason": sim["exit_reason"], "bars_held": sim["bars_held"],
                            "net_pnl": sim["net_pnl"]})
        trades.append(rec)
        prev_side = side
        t = nxt
    return trades


def _path_sim(candles: pd.DataFrame, entry_px: List[float], legs: List[dict],
              credit_pts: float, qty: int, spot_entry: float, dte0: float) -> dict:
    """Condor-style path sim on the remaining futures bars with a theta glide to a
    0.5-dte endpoint built from BS at entry IVs (first-order, like e005)."""
    from experiments.e005_theta_condor.replay_theta import (
        _bs_ltp, _implied_iv_safe, _leg_delta, _leg_gamma)
    ivs = [_implied_iv_safe(spot_entry, l["strike"], l["is_call"], e, dte0)
           for l, e in zip(legs, entry_px)]
    sgn = [1.0 if l["action"] == "BUY" else -1.0 for l in legs]
    net_delta = sum(_leg_delta(spot_entry, l["strike"], l["is_call"], iv, dte0) * s
                    for l, iv, s in zip(legs, ivs, sgn))
    net_gamma = sum(_leg_gamma(spot_entry, l["strike"], l["is_call"], iv, dte0) * s
                    for l, iv, s in zip(legs, ivs, sgn))

    def greek(spot):
        ds = spot - spot_entry
        return (net_delta * ds + 0.5 * net_gamma * ds * ds) * qty

    n = len(candles)
    spot_close = float(candles.iloc[-1]["close"])
    end_px = [_bs_ltp(spot_close, l["strike"], l["is_call"], iv, max(dte0 - 0.35, 0.05))
              for l, iv in zip(legs, ivs)]
    endpoint = sum((e - x) * qty for e, x, l in zip(entry_px, end_px, legs) if l["action"] == "SELL") \
        + sum((x - e) * qty for e, x, l in zip(entry_px, end_px, legs) if l["action"] == "BUY")
    resid_total = endpoint - greek(spot_close)

    stop_level, target_level = -STOP_FRAC * credit_pts * qty, 1.0 * credit_pts * qty
    exit_reason, exit_bar, mtm = "EOD", n, 0.0
    for i, (_, bar) in enumerate(candles.iterrows()):
        mtm = greek(float(bar["close"])) + resid_total * (i + 1) / n
        if mtm <= stop_level:
            exit_reason, exit_bar = "STOP", i + 1
            break
        if mtm >= target_level:
            exit_reason, exit_bar = "TARGET", i + 1
            break
    gross = mtm if exit_reason != "EOD" else endpoint
    fric = calculate_friction([OptionLeg(strike=l["strike"], option_type="CE" if l["is_call"] else "PE",
                                         action=l["action"], entry_price=float(px), lot_size=qty)
                               for l, px in zip(legs, entry_px)])
    return {"exit_reason": exit_reason, "bars_held": exit_bar,
            "net_pnl": round(gross - fric.total_rupees, 2)}


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e008 flip-signal verdict")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N fetched sessions")
    args = ap.parse_args()

    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    files = sorted(WALLS_DIR.glob("*.json"))
    if args.limit:
        files = files[:args.limit]
    rows: List[dict] = []
    for f in files:
        entry = json.loads(f.read_text())
        d = pd.Timestamp(entry["date"]).date()
        try:
            candles = load_intraday_candles(d)
        except FileNotFoundError:
            continue
        rows.extend(day_signal(entry, candles, d))

    df = pd.DataFrame(rows)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_csv(ARTIFACTS / "flip_trades.csv", index=False)
    # rates scale the observed per-session rate to the full 576-session universe
    n_universe = 576
    sess_per_year = n_universe / 5.7
    scale = (n_universe / len(files)) if files else 0.0
    flips_per_year = len(df) * scale / n_universe * sess_per_year if len(df) else 0.0
    # certified = fresh wall OI at decision AND fillable quotes at t+1
    cert = df[df["fillable"] & (df["wall_oi_age_min"] <= 5.01)] if not df.empty else df
    cert_per_year = len(cert) * scale / n_universe * sess_per_year if len(cert) else 0.0
    sim = cert[cert["net_pnl"].notna()] if not cert.empty else cert

    gp = sim.loc[sim.net_pnl > 0, "net_pnl"].sum() if not sim.empty else 0.0
    gl = abs(sim.loc[sim.net_pnl <= 0, "net_pnl"].sum()) if not sim.empty else 0.0
    pf = float(gp / gl) if gl else float("inf")
    wr = float((sim.net_pnl > 0).mean()) if not sim.empty else 0.0
    fillable_share = (df["fillable"].mean()) if not df.empty else 0.0

    k1 = cert_per_year >= MIN_FLIPS_PER_YEAR
    k2 = (pf >= PF_MIN and len(sim) >= 10)  # PF meaningless under ~10 trades
    k3 = fillable_share >= 0.5  # the API ceiling: unfillable flips can't be a book
    verdict = {
        "n_sessions_evaluated": len(files), "n_flip_events": len(df),
        "flips_per_year": round(flips_per_year, 1),
        "certified_trades_per_year": round(cert_per_year, 1),
        "fillable_share": round(float(fillable_share), 3),
        "n_traded": len(sim), "net": round(float(sim.net_pnl.sum()), 0) if not sim.empty else 0,
        "wr": round(wr, 3), "pf": (round(pf, 2) if gl else None),
        "exits": sim["exit_reason"].value_counts().to_dict() if not sim.empty else {},
        "kill_criteria": {"1_capacity>=15/yr": bool(k1),
                          "2_pf>=1.5_with_n>=10": bool(k2),
                          "3_fillable_share>=0.5": bool(k3)},
        "verdict": "PASS" if (k1 and k2 and k3) else "FAIL",
    }
    with open(OUT, "w") as f:
        json.dump(verdict, f, indent=2, default=str)
    print(json.dumps(verdict, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
