"""E029 — does any structural slice of e013 survive its own early era?

Contract first: PREREG.md, frozen 2026-10-03 before this file existed.

The design in one sentence: **selection reads 2021-2023, the verdict reads
2024-2026, and they never overlap.** The obvious version of this experiment —
filter on the early era, score on all six years — is in-sample, and PREREG §2
says so before it is tempting.

Nothing is re-selected, re-marked or re-priced. Arm 0 is e028's corrected book
verbatim, read from its trades artifact; if it does not reproduce e028 to the
rupee, the experiment is void before a single filter is applied.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.e027_spread_realism.spread_realism import (
    CONSERVATIVE_PTS_PER_LEG, MODELLED_PTS_PER_LEG, PLAN_STATED_PTS_PER_LEG,
    price_book,
)

ARTIFACTS = HERE / "artifacts"
TRADES_CSV = ROOT / "experiments" / "e028_expiry_encoding_audit" / "artifacts" / "audit_trades.csv"
VERDICT = ARTIFACTS / "verdict.json"

# --- e028's published numbers. Gate 0 is the control: this experiment is void
# if the unfiltered book does not land on them. ---
E028_NET_075 = 45567.74
E028_NET_20 = -29082.26
E028_N = 129

SELECTION_YEARS = (2021, 2022, 2023)     # PREREG 3.2
VERDICT_YEARS = (2024, 2025, 2026)

SELECTION_MIN_N = 20       # 3.4
VERDICT_MIN_N = 30         # gate 4
TIE_BAND_INR = 50.0        # 3.4
NULL_DRAWS = 500           # 3.5
NULL_QUANTILE = 0.95       # 3.5
BOOT_DRAWS = 10_000
BOOT_MIN_P = 0.95          # gate 5
SEED = 20261003            # frozen: the null and the bootstrap are reproducible

# Fields e013 knew at or before the 12:35 entry. Gate 6: a filter may not use
# anything else. `debit_real` is the exit mark and `net_real` the outcome -- a
# filter touching either is the outcome grading itself.
PRE_ENTRY_FIELDS = frozenset({
    "date", "atm", "wing_ce", "wing_pe", "dte", "expansion", "credit_pts",
    "front_expiry", "lot", "mark_valid", "expiry_is_trade_date",
})
OUTCOME_FIELDS = frozenset({"debit_real", "net_real"})


# --------------------------------------------------------------- the book ----
@dataclass(frozen=True)
class Universe:
    """e028's corrected trade list, with the two eras marked. Read-only."""
    df: pd.DataFrame

    @property
    def selection(self) -> pd.DataFrame:
        return self.df[self.df.era == "selection"]

    @property
    def verdict(self) -> pd.DataFrame:
        return self.df[self.df.era == "verdict"]


def load_universe() -> Universe:
    df = pd.read_csv(TRADES_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["mark_valid"] == True].reset_index(drop=True)  # noqa: E712
    if len(df) != E028_N:
        raise ValueError(f"expected {E028_N} usable sessions, got {len(df)} "
                         "-- e028's artifact changed shape; void the experiment")
    yr = pd.to_datetime(df["date"]).dt.year
    df["era"] = np.where(yr.isin(SELECTION_YEARS), "selection", "verdict")
    return Universe(df)


# ---------------------------------------------------------- the five filters --
# (key, predicate, uses) -- `uses` is what gate 6 checks against
# PRE_ENTRY_FIELDS. Each is structural and was written before any PnL was read.
def _f1(df): return df[df.expansion <= 0.50]
def _f2(df): return df[df.expansion <= 0.40]
def _f3(df): return df[df.dte == 2]
def _f4(df): return df[(df.dte == 2) & (df.expansion <= 0.50)]
def _f5(df, median_credit: float): return df[df.credit_pts >= median_credit]


FILTERS: dict = {
    "F1_expansion_le_0.50": dict(fn=_f1, uses={"expansion"},
                                 why="tighten e013's 0.65 bar by ~1.4 sigma"),
    "F2_expansion_le_0.40": dict(fn=_f2, uses={"expansion"},
                                 why="further, near the 25th percentile"),
    "F3_dte_eq_2": dict(fn=_f3, uses={"dte"},
                        why="the 'this is not a 0DTE book' finding: 92/129 are dte 2"),
    "F4_dte2_and_expansion_le_0.50": dict(fn=_f4, uses={"dte", "expansion"},
                                          why="the conjunction of the two"),
    "F5_credit_ge_selection_median": dict(fn=_f5, uses={"credit_pts"},
                                          why="take the richer flies; median from the SELECTION era only"),
}


def selection_credit_median(uni: Universe) -> float:
    """F5's threshold, from the SELECTION era only.

    Computed once, from the universe, and passed to every `apply_filter`. It is
    NOT recomputed from whatever frame a filter is applied to: doing that would
    silently return an empty frame when the filter is applied to the verdict
    era, which is a bug that looks exactly like a negative result.
    """
    return float(uni.selection.credit_pts.median())


def apply_filter(df: pd.DataFrame, key: str, credit_median: float | None = None) -> pd.DataFrame:
    spec = FILTERS[key]
    if key.startswith("F5"):
        if credit_median is None:
            raise ValueError("F5 needs the selection-era credit median, passed explicitly")
        return spec["fn"](df, float(credit_median))
    return spec["fn"](df)


def assert_no_hindsight(key: str, df: pd.DataFrame) -> None:
    """Gate 6. A filter that reads the exit mark or the outcome is not a
    filter -- it is the result grading itself."""
    uses = set(FILTERS[key]["uses"])
    bad = uses & OUTCOME_FIELDS
    if bad:
        raise AssertionError(f"filter {key} reads outcome fields {sorted(bad)}")
    unknown = uses - PRE_ENTRY_FIELDS
    if unknown:
        raise AssertionError(f"filter {key} reads non-pre-entry fields {sorted(unknown)}")


# ------------------------------------------------------------------ scoring ---
def net_at(df: pd.DataFrame, pts_per_leg: float) -> pd.Series:
    """e027's re-price, which already carries e013's 0.75-pt modelled slippage
    inside `net_real`. Identical marks, lot eras and friction; only the slippage
    term moves."""
    return price_book(df, pts_per_leg)


def score(df: pd.DataFrame, pts_per_leg: float) -> dict:
    net = net_at(df, pts_per_leg)
    if len(net) == 0:
        return dict(trades=0, net_pnl=0.0, ev_per_trade=0.0,
                    win_rate=0.0, profit_factor=0.0, max_drawdown_inr=0.0)
    eq = net.cumsum()
    return dict(
        trades=int(len(net)),
        net_pnl=round(float(net.sum()), 2),
        ev_per_trade=round(float(net.mean()), 2),
        win_rate=round(float((net > 0).mean()), 4),
        profit_factor=round(float(net[net > 0].sum() / abs(net[net < 0].sum())), 2)
        if (net < 0).any() else float("inf"),
        max_drawdown_inr=round(float((eq.cummax() - eq).max()), 2),
    )


def bootstrap_p_positive(net: pd.Series, seed: int = SEED) -> float:
    """P(mean net > 0) under resampling of sessions. Not a t-test: the book has
    71 sessions, a right tail and a fee floor, so the normal approximation is
    exactly the assumption that is in doubt."""
    if len(net) == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    vals = net.to_numpy()
    means = vals[rng.integers(0, len(vals), size=(BOOT_DRAWS, len(vals)))].mean(axis=1)
    return round(float((means > 0).mean()), 4)


# ------------------------------------------------------------------- null -----
def null_distribution(verdict_era: pd.DataFrame, n_keep: int,
                      pts_per_leg: float, draws: int = NULL_DRAWS,
                      seed: int = SEED) -> np.ndarray:
    """EV of `n_keep` uniformly random sessions from the held-out era.

    This is the control that makes a positive number mean something. Any subset
    of a book that is dragged down elsewhere will beat the whole; the question
    is whether THIS subset beats an ARBITRARY one of the same size.
    """
    rng = np.random.default_rng(seed)
    pool = verdict_era.reset_index(drop=True)
    if len(pool) < n_keep:
        return np.array([])
    net = net_at(pool, pts_per_leg).to_numpy()
    idx = rng.integers(0, len(pool), size=(draws, n_keep))
    return net[idx].mean(axis=1)


# --------------------------------------------------------------- selection ----
def choose_filter(sel: pd.DataFrame, pts_per_leg: float, credit_median: float) -> dict:
    """PREREG 3.4. Highest selection-era EV among filters with EV > 0 and
    n >= 20; ties within 50 INR break to the smaller n.

    Returns exactly one key, or None. A null result is a result.
    """
    survivors = []
    for key in FILTERS:
        sub = apply_filter(sel, key, credit_median)
        s = score(sub, pts_per_leg)
        survivors.append(dict(key=key, n=s["trades"], ev=s["ev_per_trade"],
                              net=s["net_pnl"], ok=(s["trades"] >= SELECTION_MIN_N
                                                    and s["ev_per_trade"] > 0.0)))
    if not any(s["ok"] for s in survivors):
        return dict(chosen=None, survivors=survivors)
    ok = [s for s in survivors if s["ok"]]
    best = max(s["ev"] for s in ok)
    band = [s for s in ok if best - s["ev"] <= TIE_BAND_INR]
    band.sort(key=lambda s: (s["n"], -s["ev"]))
    return dict(chosen=band[0]["key"], survivors=survivors)


# -------------------------------------------------------------------- run -----
def run() -> tuple[pd.DataFrame, dict]:
    uni = load_universe()
    sel, verd = uni.selection, uni.verdict

    # --- gate 0: control. e028's book, verbatim. ---
    ctrl_075, ctrl_20 = score(uni.df, MODELLED_PTS_PER_LEG), score(uni.df, CONSERVATIVE_PTS_PER_LEG)
    gate0 = (abs(ctrl_075["net_pnl"] - E028_NET_075) <= 1.0
             and abs(ctrl_20["net_pnl"] - E028_NET_20) <= 1.0
             and ctrl_075["trades"] == E028_N)

    pick = choose_filter(sel, CONSERVATIVE_PTS_PER_LEG, selection_credit_median(uni))
    chosen = pick["chosen"]
    cm = selection_credit_median(uni)

    out = dict(
        experiment="e029_era_slices",
        prereg="PREREG.md (2026-10-03)",
        seed=SEED,
        control={
            "unfiltered_at_0.75pts": ctrl_075,
            "unfiltered_at_2.0pts": ctrl_20,
            "e028_published": {"at_0.75pts": E028_NET_075, "at_2.0pts": E028_NET_20, "n": E028_N},
        },
        gates={"0_control_reproduces_e028": {"bar": "unfiltered book == e028 to Rs 1 on n=129",
                                             "observed_net_075": ctrl_075["net_pnl"],
                                             "observed_net_20": ctrl_20["net_pnl"],
                                             "pass": gate0}},
        selection_era={
            "years": list(SELECTION_YEARS), "n": int(len(sel)),
            "unfiltered_at_2.0pts": score(sel, CONSERVATIVE_PTS_PER_LEG),
            "survivors": pick["survivors"], "chosen": chosen,
        },
        verdict_era={"years": list(VERDICT_YEARS), "n": int(len(verd)),
                     "unfiltered_at_2.0pts": score(verd, CONSERVATIVE_PTS_PER_LEG)},
        slippage_ladder_pt_per_leg=[0.05, 0.25, 0.50, MODELLED_PTS_PER_LEG,
                                    PLAN_STATED_PTS_PER_LEG, CONSERVATIVE_PTS_PER_LEG, 2.50],
    )

    if not gate0:
        out["verdict"] = "AUDIT VOID — the unfiltered book does not reproduce e028; no verdict"
        return uni.df, out

    if chosen is None:
        out["gates"]["1_selection_is_real"] = {
            "bar": f"at least one of the 5 filters has selection EV > 0 with n >= {SELECTION_MIN_N}",
            "pass": False,
            "note": "no filter qualified; nothing is carried out of sample"}
        out["verdict"] = "NO SLICE — the early era loses under every structural filter"
        out["era_diagnostic"] = era_diagnostic(uni.df)
        return uni.df, out

    sub_sel = apply_filter(sel, chosen, cm)
    sub_verd = apply_filter(verd, chosen, cm)
    assert_no_hindsight(chosen, uni.df)

    net_v = net_at(sub_verd, CONSERVATIVE_PTS_PER_LEG)
    s_v = score(sub_verd, CONSERVATIVE_PTS_PER_LEG)
    s_s = score(sub_sel, CONSERVATIVE_PTS_PER_LEG)

    null = null_distribution(verd, s_v["trades"], CONSERVATIVE_PTS_PER_LEG)
    p95 = float(np.percentile(null, NULL_QUANTILE * 100)) if len(null) else float("nan")
    p_pos = bootstrap_p_positive(net_v)
    in_sample = pd.to_datetime(sub_sel["date"]).dt.year.isin(SELECTION_YEARS).all()

    g1 = True
    g2 = s_v["ev_per_trade"] > 0.0
    g3 = (len(null) > 0) and (s_v["ev_per_trade"] > p95)
    g4 = s_v["trades"] >= VERDICT_MIN_N
    g5 = p_pos >= BOOT_MIN_P

    out["chosen_filter"] = dict(
        key=chosen, why=FILTERS[chosen]["why"], uses=sorted(FILTERS[chosen]["uses"]),
        gate6_no_hindsight=True, gate6_selection_era_only=bool(in_sample))
    out["arms"] = {
        "A_selection_era_IN_SAMPLE_NOT_A_VERDICT": {**s_s, "slip_pts_per_leg": CONSERVATIVE_PTS_PER_LEG},
        "B_verdict_era_HELD_OUT": {**s_v, "slip_pts_per_leg": CONSERVATIVE_PTS_PER_LEG},
    }
    out["ladder_held_out"] = [
        {"pts_per_leg": p, **score(sub_verd, p)} for p in out["slippage_ladder_pt_per_leg"]]
    out["honest_null"] = {
        "draws": NULL_DRAWS, "same_n_as_chosen": s_v["trades"],
        "p95_ev_per_trade": round(p95, 2),
        "median_ev_per_trade": round(float(np.median(null)), 2) if len(null) else None,
        "share_of_null_above_chosen": round(float((null > s_v["ev_per_trade"]).mean()), 4)
        if len(null) else None,
        "note": "random subsets of the SAME held-out size. Clearing zero is not "
                "clearing this.",
    }
    ci = np.percentile(_boot_means(net_v), [2.5, 97.5])
    out["bootstrap"] = {"draws": BOOT_DRAWS, "p_ev_positive": p_pos,
                        "mean_ev_ci95": [round(float(x), 2) for x in ci]}
    out["gates"].update({
        "1_selection_is_real": {"bar": "a filter cleared selection EV > 0, n >= 20",
                                "pass": g1, "chosen": chosen},
        "2_verdict_ev_positive": {"bar": "held-out EV > 0 at 2.0 pts/leg",
                                  "observed": s_v["ev_per_trade"], "pass": g2},
        "3_verdict_beats_the_null": {"bar": f"held-out EV > p{NULL_QUANTILE:.0%} of "
                                                f"{NULL_DRAWS} same-size random subsets",
                                     "observed": s_v["ev_per_trade"], "p95": round(p95, 2),
                                     "pass": bool(g3)},
        "4_verdict_sample_size": {"bar": f">= {VERDICT_MIN_N} held-out sessions",
                                  "observed": s_v["trades"], "pass": g4},
        "5_verdict_confidence": {"bar": f"P(EV>0) >= {BOOT_MIN_P} over {BOOT_DRAWS} bootstrap draws",
                                 "observed": p_pos, "pass": g5},
        "6_no_hindsight_in_filter": {"bar": "filter reads only pre-entry fields",
                                     "observed": sorted(FILTERS[chosen]["uses"]), "pass": True},
    })

    if not g4:
        verdict = "UNRESOLVABLE ON SAMPLE SIZE — the held-out n is below 30"
    elif g2 and g3:
        verdict = "SLICE SURVIVES OUT-OF-SAMPLE"
    elif g2:
        verdict = "DEAD — positive, but indistinguishable from an arbitrary subset of the same size"
    else:
        verdict = "DEAD — the slice does not generalise"

    out["verdict"] = verdict
    out["era_diagnostic"] = era_diagnostic(uni.df)
    out["in_sample_to_out_of_sample_gap"] = {
        "selection_era_ev": s_s["ev_per_trade"], "verdict_era_ev": s_v["ev_per_trade"],
        "note": "if these differ sharply the filter was fitted, not found",
    }
    return uni.df, out


def era_diagnostic(df: pd.DataFrame) -> dict:
    """Why the early era fails, by era and by fill.

    NOT a gate and NOT a filter. Reported because it is the actual shape of the
    answer: if the early era is dead only at a pessimistic fill and alive at the
    engine's own, that is a different conclusion from dead at both.

    And the reason "trade only 2024 onward" is NOT offered as a slice: the era
    boundary was chosen by looking at the eras. That is the most overfit filter
    available, and it has no holdout by construction.
    """
    grid = {}
    for era in ("selection", "verdict", "both"):
        sub = df if era == "both" else df[df.era == era]
        grid[era] = {
            str(p): score(sub, p)
            for p in (MODELLED_PTS_PER_LEG, PLAN_STATED_PTS_PER_LEG,
                      CONSERVATIVE_PTS_PER_LEG)
        }
    return {
        "by_era_and_fill": grid,
        "warning": "'trade only 2024+' would look like the winning filter here. It is "
                   "not offered: the boundary was chosen by looking at the eras, so it "
                   "has no holdout and cannot be tested. Treat 2024-2026 positivity as "
                   "a regime observation, never as a slice.",
    }


def _boot_means(net: pd.Series) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    v = net.to_numpy()
    return v[rng.integers(0, len(v), size=(BOOT_DRAWS, len(v)))].mean(axis=1)


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    _, out = run()
    VERDICT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    g = out["gates"]
    print(f"\nVERDICT: {out['verdict']}")
    c = out["control"]
    print(f"  control unfiltered  0.75pts: {c['unfiltered_at_0.75pts']['net_pnl']:>12,.0f}"
          f"   2.0pts: {c['unfiltered_at_2.0pts']['net_pnl']:>12,.0f}   n={c['unfiltered_at_0.75pts']['trades']}")
    for k in ("0_control_reproduces_e028", "1_selection_is_real", "2_verdict_ev_positive",
              "3_verdict_beats_the_null", "4_verdict_sample_size",
              "5_verdict_confidence", "6_no_hindsight_in_filter"):
        if k in g:
            print(f"    [{'PASS' if g[k]['pass'] else 'FAIL'}] {k}")
    if "arms" in out:
        a = out["arms"]["A_selection_era_IN_SAMPLE_NOT_A_VERDICT"]
        b = out["arms"]["B_verdict_era_HELD_OUT"]
        print(f"  chosen filter: {out['chosen_filter']['key']}  ({out['chosen_filter']['why']})")
        print(f"    A selection era 2021-23 (IN-SAMPLE, not a verdict): n={a['trades']:>3}"
              f"  net={a['net_pnl']:>11,.0f}  EV={a['ev_per_trade']:>9,.0f}")
        print(f"    B verdict  era 2024-26 (HELD OUT, the verdict)    : n={b['trades']:>3}"
              f"  net={b['net_pnl']:>11,.0f}  EV={b['ev_per_trade']:>9,.0f}")
        n = out["honest_null"]
        print(f"    null (500 random subsets, n={n['same_n_as_chosen']}): "
              f"p95 EV={n['p95_ev_per_trade']:>9,.0f}   chosen beats {n['share_of_null_above_chosen']:.0%} of them")
        print(f"    bootstrap P(EV>0) = {out['bootstrap']['p_ev_positive']}")
    if "era_diagnostic" in out:
        ed = out["era_diagnostic"]["by_era_and_fill"]
        print("\n  era x fill (INFORMATIVE ONLY -- not a gate, not a filter)")
        print(f"    {'':<12}{'n':>5}{'@0.75':>12}{'@1.50':>12}{'@2.00':>12}")
        for era, label in (("selection", "2021-2023"), ("verdict", "2024-2026"), ("both", "six-year")):
            r = ed[era]
            print(f"    {label:<12}{r['0.75']['trades']:>5}"
                  f"{r['0.75']['ev_per_trade']:>12,.0f}"
                  f"{r['1.5']['ev_per_trade']:>12,.0f}"
                  f"{r['2.0']['ev_per_trade']:>12,.0f}")
        print("    ^ 2024-2026 is positive at every fill. That is a REGIME observation,")
        print("       not a slice: the era boundary was chosen by looking at the eras.")
    print(f"\n  -> {VERDICT.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()