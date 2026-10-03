"""e027 — realized slippage on the restated e013 pin fly.

PREREG-frozen: ../PREREG.md (2026-10-03, before any code in this directory).

The question is arithmetic, not research. e026 restated the pin fly at
+Rs 61,843 (EV +966/trade) but left slippage at the inherited 1.5 pts/leg.
Against ~Rs 595 of modelled friction that leaves Rs 371/trade of headroom, and
8 leg-fills at lot 65 make one point worth Rs 520 — so the entire margin of
safety is **0.71 points per leg**.

There is no bid/ask anywhere in this repo, so the spread must be ESTIMATED from
daily OHLC. Two bounds are computed and the verdict must hold against both:

  TIGHT  one tick, derived from the data (the modal granularity of closes)
  WIDE   Corwin & Schultz (2012) two-day high-low effective spread

CS estimates the EFFECTIVE spread, which includes price impact, so on strikes
trading millions of contracts it is biased wide. It is an upper bound, not an
estimate, and is treated as such throughout.

Three arms on identical sessions and identical marks — only the slippage term
differs — so every difference in the result is attributable to slippage alone.
Arm A is the control and must reproduce e026's +61,842.51 on n=64.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.feeds.bhavcopy import parse_date, with_expiry_date
from experiments.e026_realmark_audit.audit_realmark import (
    HISTORICAL_DIR,
    WING_WIDTH,
    build_bhavcopy_calendar,
    e013_friction,
    front_expiry,
)

E026_TRADES = ROOT / "experiments" / "e026_realmark_audit" / "artifacts" / "audit_trades.csv"
ARTIFACTS = HERE / "artifacts"

OHLC = ["symbol", "instrument", "expiry", "strike", "option_type",
        "open", "high", "low", "close", "contracts"]
SQRT2 = math.sqrt(2.0)
K_CS = 3.0 - 2.0 * SQRT2  # 0.17157; the standard Corwin-Schultz constant

# e013's ACTUAL modelled slippage is 6.0 index points per lot for the whole
# 4-leg round trip = 8 leg-fills, i.e. 0.75 pts/leg. Note that actionplan s5.3
# states 1.5 pts/leg — twice what the engine ever charged. Both are reported.
MODELLED_PTS_PER_LEG = 6.0 / 8.0
PLAN_STATED_PTS_PER_LEG = 1.5
# A deliberately pessimistic fill, ~33% of the option's own median price. 8
# leg-fills x 2.0 pts is 16 points round trip; on a book whose median leg is
# ~59 pts that is a genuinely poor fill, not a mild one.
CONSERVATIVE_PTS_PER_LEG = 2.0


# ------------------------------------------------------------ leg loading ---
def load_front_chain_ohlc(cal: dict, d):
    """Front-expiry NIFTY chain WITH OHLC, for `d`'s own partition.

    Same expiry rule as e026 (and therefore the same contract-identity
    guarantee), just a wider column set. Kept local rather than widening
    e026's loader, which other code depends on.

    E028: this function compared `expiry` to `str(fe)` — the same date-vs-string
    defect e026 carried, in a second copy. It silently returned an empty chain
    for every 2021-2024 partition, so the Corwin-Schultz spread below was
    estimated on whatever era survived. Compare as a date.
    """
    p = cal.get(d)
    if p is None:
        return None, None
    df = pd.read_parquet(p, columns=OHLC)
    n = df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")]
    if n.empty:
        return None, None
    n = with_expiry_date(n)
    fe = front_expiry(set(n["expiry_date"]), d)
    if fe is None:
        return None, None
    return n[n["expiry_date"] == fe], fe


def _leg_row(chain: pd.DataFrame, strike: float, side: str):
    """The OHLC row for one leg, or None. Never fabricated."""
    q = chain[(chain["strike"] == float(strike)) & (chain["option_type"] == side)]
    if q.empty:
        return None
    r = q.iloc[0]
    if any(pd.isna(r[c]) for c in ("open", "high", "low", "close")):
        return None
    return r


def derive_tick(all_closes: pd.Series) -> float:
    """The exchange tick, derived rather than asserted.

    NIFTY options quote on a fixed grid. The modal granularity of observed
    closes is that grid. Returns the smallest granularity that explains the
    bulk of the price distribution.
    """
    v = all_closes[(all_closes > 0) & np.isfinite(all_closes)]
    if v.empty:
        return float("nan")
    for tick in (0.05, 0.10, 0.25):
        resid = np.abs(v / tick - np.round(v / tick))
        if (resid < 1e-6).mean() > 0.98:
            return tick
    return float("nan")


def corwin_schultz(h0, l0, h1, l1, c0, c1, c2) -> float:
    """Corwin & Schultz (2012) effective spread, in POINTS.

        beta  = (ln H0/L0)^2 + (ln H1/L1)^2          two-session range variance
        gamma = (ln C1/C2)^2 + (ln C0/C1)^2          two-session CLOSE variance
        alpha = (sqrt(2 beta) - sqrt beta)/k - sqrt(gamma/k)
        s_rel = 2 (e^alpha - 1) / (e^alpha + 1)

    gamma MUST come from closes, not from the high-low ranges — that is the
    whole mechanism by which the estimator separates a wide spread from a
    genuine intraday move. Setting gamma = beta (the obvious shortcut) forces
    s_rel to ~0 by construction and silently reports "no spread" on every leg.

    Returned in absolute points against the three-session mean price. A
    non-positive alpha means the range was fully explained by volatility: that
    is UNMEASURABLE, and returns NaN rather than a spurious tight zero.
    """
    vals = [h0, l0, h1, l1, c0, c1, c2]
    if any(v is None or not np.isfinite(v) or v <= 0 for v in vals):
        return float("nan")
    beta = math.log(h0 / l0) ** 2 + math.log(h1 / l1) ** 2
    gamma = math.log(c1 / c2) ** 2 + math.log(c0 / c1) ** 2
    if beta <= 0 or gamma <= 0:
        return float("nan")
    alpha = (SQRT2 * math.sqrt(beta) - math.sqrt(beta)) / K_CS - math.sqrt(gamma / K_CS)
    if alpha <= 0 or not np.isfinite(alpha):
        return float("nan")
    s_rel = 2.0 * (math.exp(alpha) - 1.0) / (math.exp(alpha) + 1.0)
    level = (h0 + l0 + h1 + l1 + c0 + c1 + c2) / 7.0
    return s_rel * level


# ------------------------------------------------------- spread extraction ---
def leg_labels(atm: float) -> list[tuple[str, float, str]]:
    """The four iron-fly legs, in the order the book trades them."""
    return [("atm_ce", atm, "CE"), ("atm_pe", atm, "PE"),
            ("wing_ce", atm + WING_WIDTH, "CE"), ("wing_pe", atm - WING_WIDTH, "PE")]


def collect_spreads(cal: dict) -> pd.DataFrame:
    """One row per traded leg-session, with its tight and wide spread bounds.

    Only the sessions e026 certified as valid marks (Arm B) are used, so this
    measures the cost of the book that actually survived.
    """
    trades = pd.read_csv(E026_TRADES)
    arm_b = trades[trades["mark_valid"] == True]  # noqa: E712
    rows: list[dict] = []
    closes_seen: list[float] = []

    for t in arm_b.itertuples():
        d = parse_date(str(t.date))
        # Corwin-Schultz needs THREE sessions: two for the high-low ranges and
        # a third for the close-to-close variance.
        prior: list = []
        for back in (1, 2, 3):
            cand = d - pd.Timedelta(days=back)
            if cand not in cal:
                break
            prior.append(cand)
        chain_d, fe_d = load_front_chain_ohlc(cal, d)
        if chain_d is None:
            continue
        # The three sessions must all reference the SAME contract, or the
        # estimator is comparing two different instruments.
        prior_chains = []
        for pd_ in prior[:2]:
            if len(prior_chains) >= 2:
                break
            ch, fe_p = load_front_chain_ohlc(cal, pd_)
            if ch is None or fe_d not in set(ch["expiry_date"]):
                prior_chains.append(None)
            else:
                prior_chains.append(ch)

        for label, strike, side in leg_labels(float(t.atm)):
            rd = _leg_row(chain_d, strike, side)
            if rd is None:
                rows.append(dict(date=d, label=label, ok=False))
                continue
            closes_seen.append(float(rd["close"]))
            wide = float("nan")
            c0 = c1 = c2 = None
            if len(prior_chains) >= 1 and prior_chains[0] is not None:
                r1 = _leg_row(prior_chains[0], strike, side)
                if r1 is not None:
                    c0 = float(r1["close"])
                    if len(prior_chains) >= 2 and prior_chains[1] is not None:
                        r2 = _leg_row(prior_chains[1], strike, side)
                        if r2 is not None:
                            c1 = float(r2["close"])
                            wide = corwin_schultz(
                                float(rd["high"]), float(rd["low"]),
                                float(r1["high"]), float(r1["low"]),
                                c0, float(rd["close"]), c1)
            rows.append(dict(date=d, label=label, ok=True,
                             contracts=float(rd["contracts"]),
                             close=float(rd["close"]),
                             open=float(rd["open"]),
                             high=float(rd["high"]), low=float(rd["low"]),
                             cs_wide=wide))
    df = pd.DataFrame(rows)
    df.attrs["tick"] = derive_tick(pd.Series(closes_seen))
    return df


# ------------------------------------------------------------------ arms -----
def price_book(arm_b: pd.DataFrame, slip_per_leg: float | pd.Series) -> pd.Series:
    """Re-price Arm B with a per-leg slippage, everything else frozen.

    Identical marks, identical sessions, identical lot eras. Only the slippage
    term moves. e026's `net_real` already carries e013's modelled slippage
    (6.0 index points per lot, = 8 leg-fills x 0.75 pts/leg x lot), so the
    swap is a single add-back of that term minus the measured one.
    """
    slip = slip_per_leg if isinstance(slip_per_leg, pd.Series) else None
    out = []
    for i, t in enumerate(arm_b.itertuples()):
        s = float(slip.iloc[i]) if slip is not None else float(slip_per_leg)
        modelled_inr = 8.0 * MODELLED_PTS_PER_LEG * float(t.lot)   # == 6.0 * lot
        measured_inr = 8.0 * s * float(t.lot)
        out.append(float(t.net_real) + modelled_inr - measured_inr)
    return pd.Series(out, index=arm_b.index)


def run() -> tuple[pd.DataFrame, dict]:
    tick = None
    df = collect_spreads(build_bhavcopy_calendar())
    tick = df.attrs.get("tick")
    good = df[df["ok"] == True]  # noqa: E712
    coverage = len(good) / len(df) if len(df) else 0.0

    trades = pd.read_csv(E026_TRADES)
    arm_b = trades[trades["mark_valid"] == True].reset_index(drop=True)  # noqa: E712
    arm_b["_d"] = [parse_date(str(x)) for x in arm_b["date"]]
    cs_by_session = good.groupby("date")["cs_wide"].mean()

    # --- arms ---------------------------------------------------------------
    net_control = price_book(arm_b, MODELLED_PTS_PER_LEG)
    net_plan = price_book(arm_b, PLAN_STATED_PTS_PER_LEG)
    tight = tick if tick and np.isfinite(tick) else 0.05
    net_tight = price_book(arm_b, tight)
    net_cons = price_book(arm_b, CONSERVATIVE_PTS_PER_LEG)

    # per-session CS average across the four legs, forward-filled onto arm_b
    sess_cs = arm_b["_d"].map(cs_by_session)
    sess_cs = sess_cs.fillna(sess_cs.median())
    net_wide = price_book(arm_b, sess_cs.clip(lower=tick))

    # --- gates --------------------------------------------------------------
    atm_cs = good[good["label"].isin(["atm_ce", "atm_pe"])]["cs_wide"]
    median_atm_cs = float(atm_cs.median()) if atm_cs.notna().any() else float("nan")

    resid = float(arm_b["net_real"].sub(arm_b["net_A"]).abs().mean())
    control_ok = abs(float(net_control.sum()) - 61842.51) <= 1.0
    n_control = int(net_control.count())

    # --- why CS failed here, stated as evidence rather than hidden ---------
    rng_ratio = {}
    for label, g in good.groupby("label"):
        rng_ratio[label] = round(float(g["cs_wide"].median()
                                       / (g["high"] - g["low"]).median()), 2)
    cs_vs_price = round(float(good["cs_wide"].median() / good["close"].median()), 2)
    cs_unmeasurable_pct = round(100 * float(good["cs_wide"].isna().mean()), 1)

    # --- the deliverable: a breakeven ladder ------------------------------
    # net(s) = sum(net_real) + sum(8 * lot) * (MODELLED - s); solve for s*.
    sum_net_real = float(arm_b["net_real"].sum())
    sum_leg_inr = float((8.0 * arm_b["lot"]).sum())
    breakeven_pts = MODELLED_PTS_PER_LEG + sum_net_real / sum_leg_inr
    ladder_pts = [0.05, 0.10, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00]
    ladder = [{"pts_per_leg": s,
               "net_pnl": round(float(price_book(arm_b, s).sum()), 2),
               "ev_per_trade": round(float(price_book(arm_b, s).mean()), 2)}
              for s in ladder_pts]

    gates = {
        "0_control_reproduces_e026": {
            "bar": "arm A within Rs 1 of +61,842.51 on n=64",
            "observed": round(float(net_control.sum()), 2), "n": n_control,
            "pass": control_ok and n_control == 64,
        },
        "0b_plan_stated_slippage_is_consistent": {
            "bar": "the plan's stated 1.5 pts/leg equals what the engine charges (0.75)",
            "engine_pts_per_leg": MODELLED_PTS_PER_LEG,
            "plan_pts_per_leg": PLAN_STATED_PTS_PER_LEG,
            "pass": abs(MODELLED_PTS_PER_LEG - PLAN_STATED_PTS_PER_LEG) < 1e-9,
        },
        "1_data_coverage": {
            "bar": ">=90% of leg-days carry both sessions' OHLC",
            "observed_pct": round(100 * coverage, 2),
            "pass": coverage >= 0.90,
        },
        "2_estimator_sanity": {
            "bar": "derived tick > 0 and median CS spread on ATM legs in (1 tick, 20 pts)",
            "derived_tick": tick,
            "median_atm_cs": round(median_atm_cs, 3) if np.isfinite(median_atm_cs) else None,
            "cs_over_price_ratio": cs_vs_price,
            "cs_over_range_ratio_by_leg": rng_ratio,
            "cs_unmeasurable_pct": cs_unmeasurable_pct,
            "verdict": ("CS FAILS on this data class: it reports a spread LARGER than "
                        "the option's own price, because the daily high-low range on "
                        "0-5 DTE NIFTY options is 96-202% of price and is dominated by "
                        "genuine intraday mean reversion, which CS cannot distinguish "
                        "from spread"),
            "pass": bool(tick and np.isfinite(tick) and tick > 0
                         and np.isfinite(median_atm_cs)
                         and tight < median_atm_cs < 20.0),
        },
        "3_consistency_crosscheck": {
            "bar": "CS magnitude within 2x of the e026 BS-vs-real per-session residual",
            "residual_per_session_inr": round(resid, 2),
            "cs_mean_inr": (round(float((sess_cs * 8 * arm_b["lot"]).mean()), 2)
                            if np.isfinite((sess_cs * 8 * arm_b["lot"]).mean()) else None),
            "pass": bool(resid and np.isfinite((sess_cs * 8 * arm_b["lot"]).mean())
                         and abs((sess_cs * 8 * arm_b["lot"]).mean() - resid) / resid <= 2.0),
        },
        "4_book_survives_measured_slippage": {
            "bar": "arm C (Corwin-Schultz upper bound) net PnL > 0",
            "observed": round(float(net_wide.sum()), 2),
            "pass": bool(float(net_wide.sum()) > 0),
        },
    }
    control_and_data_ok = (gates["0_control_reproduces_e026"]["pass"]
                           and gates["1_data_coverage"]["pass"])
    estimator_ok = gates["2_estimator_sanity"]["pass"]
    wide_pos = float(net_wide.fillna(0).sum()) > 0
    tight_pos = float(net_tight.sum()) > 0
    audit_ok = control_and_data_ok and estimator_ok and gates["3_consistency_crosscheck"]["pass"]

    if not control_and_data_ok:
        verdict = "AUDIT VOID — control or coverage failed; no verdict about e013"
    elif not estimator_ok:
        verdict = ("SUPERSEDED BY E028. UNRESOLVABLE ON CURRENT DATA — the wide bound could not be "
                   "measured. The book survives if and only if realized slippage is below "
                   f"{breakeven_pts:.2f} pts/leg. No data on disk can say whether it is.")
    elif wide_pos:
        verdict = "SURVIVES MEASURED SLIPPAGE"
    elif tight_pos:
        verdict = "SURVIVES ONLY AT THE TICK FLOOR — unresolvable on current data"
    else:
        verdict = "DEAD ON EXECUTION"

    metrics = {
        "experiment": "e027_spread_realism",
        "prereg": "PREREG.md (2026-10-03)",
        # E028: the loader below compared expiry to a raw string, so the n=64
        # sample this whole experiment prices is format-selected, not the
        # sessions e013 actually traded. Re-run corrected, the breakeven is
        # 1.51 pts/leg and the book is negative at 2.0. Read e028, not this.
        "superseded_by": "e028_expiry_encoding_audit (breakeven 2.64 -> 1.51; DEAD_AT_REALISTIC_FILL)",
        "verdict": verdict,
        "audit_valid": audit_ok,
        "gates": gates,
        "bounds": {
            "derived_tick_pts": tick,
            "engine_modelled_pts_per_leg": MODELLED_PTS_PER_LEG,
            "plan_stated_pts_per_leg": PLAN_STATED_PTS_PER_LEG,
            "tight_bound_pts_per_leg": tight,
            "cs_wide_mean_pts_per_leg": round(float(sess_cs.mean()), 4) if np.isfinite(sess_cs.mean()) else None,
            "cs_wide_median_pts_per_leg": round(float(sess_cs.median()), 4) if np.isfinite(sess_cs.median()) else None,
            "cs_wide_p90_pts_per_leg": round(float(sess_cs.quantile(0.90)), 4) if np.isfinite(sess_cs.quantile(0.90)) else None,
        },
        "arms": {
            "A_control_engine_modelled_0p75pts": _stats(net_control),
            "A2_plan_stated_1p5pts": _stats(net_plan),
            "B_tight_one_tick": _stats(net_tight),
            "B2_conservative_2p0pts": _stats(net_cons),
            "C_wide_corwin_schultz": _stats(net_wide),
        },
        "headroom": {
            "restated_ev_inr": 966.29,
            "modelled_friction_inr": 595.0,
            "value_of_one_point_inr": round(sum_leg_inr / 64.0, 1),
            "BREAKEVEN_pts_per_leg": round(breakeven_pts, 3),
            "margin_over_engine_modelled_pts": round(breakeven_pts - MODELLED_PTS_PER_LEG, 3),
            "margin_over_plan_stated_pts": round(breakeven_pts - PLAN_STATED_PTS_PER_LEG, 3),
        },
        "ladder": {
            "note": "net PnL on the 64 real-marked sessions across assumed slippage",
            "rows": ladder,
        },
        "concentration": _concentration(trades, arm_b, net_cons),
        "per_leg": {
            str(k): {
                "n": int(v["n"]),
                "median_cs_pts": round(float(v["median_cs"]), 4) if np.isfinite(v["median_cs"]) else None,
                "p90_cs_pts": round(float(v["p90_cs"]), 4) if np.isfinite(v["p90_cs"]) else None,
                "median_contracts": float(v["median_contracts"]),
                "cs_unmeasurable_pct": round(100 * float(v["unmeasurable"]), 1),
            }
            for k, v in _per_leg(good).items()
        },
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    good.to_csv(ARTIFACTS / "leg_spreads.csv", index=False)
    arm_b.assign(net_control=net_control, net_tight=net_tight,
                 cs_wide=sess_cs.values, net_wide=net_wide.values).to_csv(
        ARTIFACTS / "book_by_spread.csv", index=False)
    (ARTIFACTS / "verdict.json").write_text(json.dumps(metrics, indent=2))
    return df, metrics


def _stats(net: pd.Series) -> dict:
    net = net.dropna()
    n = len(net)
    if n == 0:
        return {"trades": 0}
    wins, losses = net[net > 0], net[net < 0]
    cum = net.cumsum()
    gl = abs(float(losses.sum()))
    return {"trades": n, "total_net_pnl": round(float(net.sum()), 2),
            "net_ev_per_trade": round(float(net.mean()), 2),
            "win_rate": round(float((net > 0).mean()), 4),
            "profit_factor": round(float(wins.sum()) / gl, 2) if gl > 0 else None,
            "max_drawdown_inr": round(float((cum - cum.cummax()).min()), 2)}


def _concentration(trades: pd.DataFrame, arm_b: pd.DataFrame, net: pd.Series) -> dict:
    """How much of the surviving book is one calendar year?

    The conservative annualisation in actionplan s5.5 spreads 64 validated
    sessions over the FULL 5.71-year calendar, because those 64 sessions
    actually span only the last 2.14 years. That is deliberate and
    conservative, but it hides the sharper fact: the validated sample is
    era-selected (valid share rises 38.7% -> 56.4% -> 70.0% by year) and its
    PnL is concentrated. ponytail: no pre-2024 valid mark exists on disk at
    all, so the 2021-2023 calendar earns zero here by omission, not by
    performance. Upgrade path is e009 coverage, not more replay.
    """
    d = pd.to_datetime(arm_b["date"], dayfirst=False, errors="coerce")
    if d.isna().any():
        d = pd.to_datetime(arm_b["date"], dayfirst=True)
    by_year = net.groupby(d.dt.year).agg(["count", "sum", "mean"]).round(0)
    # The denominator is the FULL 193-session calendar (5.71y), not the 2.14y
    # the validated sessions actually span. That is the conservative choice and
    # is what actionplan s5.5 reports.
    calendar_years = _span_years(trades)
    best = by_year["sum"].max()
    return {
        "validated_span_years": _span_years(arm_b),
        "full_calendar_span_years": calendar_years,
        "conservative_annualisation_years": calendar_years,
        "by_year": {str(k): {"sessions": int(v["count"]),
                             "net_pnl": float(v["sum"]),
                             "mean_per_session": float(v["mean"])}
                    for k, v in by_year.iterrows()},
        "share_of_pnl_from_best_year_pct": round(100 * float(best) / float(net.sum()), 1),
        "conservative_pnl_per_yr_inr": round(float(net.sum()) / calendar_years, 0),
        "conservative_pct_per_yr_on_2L": round(
            100 * float(net.sum()) / calendar_years / 200000, 2),
    }


def _span_years(arm_b: pd.DataFrame) -> float:
    d = pd.to_datetime(arm_b["date"], dayfirst=False, errors="coerce")
    if d.isna().any():
        d = pd.to_datetime(arm_b["date"], dayfirst=True)
    return round((d.max() - d.min()).days / 365.25, 2)


def _per_leg(good: pd.DataFrame) -> dict:
    out = {}
    for label, g in good.groupby("label"):
        out[label] = {
            "n": len(g),
            "median_cs": g["cs_wide"].median(),
            "p90_cs": g["cs_wide"].quantile(0.90),
            "median_contracts": g["contracts"].median(),
            "unmeasurable": g["cs_wide"].isna().mean(),
        }
    return out


if __name__ == "__main__":
    _, m = run()
    print(json.dumps(m, indent=2))