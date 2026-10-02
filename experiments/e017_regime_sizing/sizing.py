"""E017: Regime-based position sizing on the frozen E011 delta-hedged straddle.

Pure arithmetic on frozen artifacts — no re-simulation. The E011 engine's
per-session PnL is linear in the size fraction f:

    net(f) = f * net(1) - (1 - f) * flat

where flat = 94.40 (entry+exit brokerage 2x(20 + 20*0.18)) + 23.60 * hedge_trades
(futures brokerage 20*1.18 per order) is the only size-invariant cost: every
turnover- or quantity-proportional term (STT, exchange, slippage, futures PnL)
scales with the traded lot multiple, and the hedge trigger is per-share
(|delta_net| >= 0.15), so the hedge trade sequence is identical at any size.

Frozen rule (PREREG.md): f = 0.5 when sigma_GK,10d(t-1) sits above its trailing
60-session 75th percentile OR the last two taken sessions both lost; else 1.0.
Part B: fixed-fraction and loss-cluster-stop risk budget tables.

ponytail: fractional lots (0.5 x 75 = 37.5) are not live-tradeable — this is the
fractional-size information bound; live 1-lot granularity means *skipping* flagged
sessions (diagnostic reported in README). Ceiling documented, upgrade path = skip
semantics or capital scaling.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = HERE / "artifacts"
E011_CSV = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts" / "vrp_daily.csv"

FROZEN = {
    "size_fraction": 0.5,
    "regime_percentile": 0.75,
    "regime_window": 60,
    "regime_min_periods": 30,
    "cluster_k": 2,
    "stop_cooldown": 2,
    "fixed_fractions": [1.0, 0.75, 0.5, 0.4, 0.3, 0.25],
    "stop_ks": [2, 3],
    "kill_max_dd_inr": 16000.0,
    "kill_min_ev_inr": 1200.0,
    "kill_min_total_frac": 0.50,
    "e011_total_net": 743572.25,
    "years": 5.7,
    "capital": 200000.0,
}

# Size-invariant per-order costs, straight from the engine cost model:
# per side = 2 legs x Rs20 brokerage + 18% GST = 40 + 7.2 = 47.2; entry + exit = 94.4.
FLAT_ENTRY_EXIT = 2 * (2 * 20.0 + 2 * 20.0 * 0.18)  # 94.4
FLAT_PER_HEDGE = 20.0 * 1.18  # 23.6


def load_base() -> pd.DataFrame:
    """Frozen E011 per-session records with the flat/variable cost decomposition."""
    df = pd.read_csv(E011_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    df["flat"] = FLAT_ENTRY_EXIT + FLAT_PER_HEDGE * df["hedge_trades"]
    df["variable_friction"] = df["friction"] - df["flat"]
    # net(f) = f * net_v - flat  <=>  net_v = net(1) + flat
    df["net_v"] = df["net_pnl"] + df["flat"]
    return df


def validate_decomposition(df: pd.DataFrame) -> None:
    """Fail loudly if the flat/variable split is inconsistent with the frozen run."""
    # Analytic option-book variable component (STT 0.1% sell + slippage 6 pts +
    # exchange/SEBI 0.0505%+0.003% x 1.18 GST, on IC/FD turnover).
    opt_var = df["lot_size"] * (
        df["initial_credit"] * (0.001 + 0.000505 * 1.18 + 0.00003 * 1.18)
        + df["final_debit"] * 0.000505 * 1.18
        + 6.0
    )
    hedge_var = df["variable_friction"] - opt_var  # residual = futures turnover costs
    if (hedge_var < -1e-6).any():
        bad = df.loc[hedge_var < -1e-6, "date"].tolist()
        raise AssertionError(f"negative futures-turnover residual on {bad[:5]} — decomposition broken")
    # A session with zero hedge orders has zero futures costs: the residual there must
    # be exactly 0. This pins the flat-fee constant (a halved entry/exit term would
    # silently shift every residual by +Rs47.2 without tripping the >= 0 check).
    no_hedge = df["hedge_trades"] == 0
    if no_hedge.any() and (hedge_var[no_hedge].abs() > 1e-6).any():
        bad = df.loc[no_hedge & (hedge_var.abs() > 1e-6), "date"].tolist()
        raise AssertionError(f"nonzero futures residual on no-hedge sessions {bad[:5]} — flat cost constant wrong")
    if not np.allclose(df["net_v"] - df["flat"], df["net_pnl"], atol=1e-6):
        raise AssertionError("f=1.0 reconstruction does not reproduce frozen net_pnl")
    total = float(df["net_pnl"].sum())
    if abs(total - FROZEN["e011_total_net"]) > 0.01:
        raise AssertionError(f"base total {total} != frozen E011 {FROZEN['e011_total_net']}")


def elevated_flags(df: pd.DataFrame, vdf: pd.DataFrame) -> pd.Series:
    """sigma_GK,10d(t-1) > trailing 60-session 75th percentile (shift(1), no lookahead)."""
    v = vdf.copy()
    v["date"] = pd.to_datetime(v["date"]).dt.date
    v = v.sort_values("date").reset_index(drop=True)
    sigma = v["sigma_gk_10d_t1"]
    hurdle = sigma.rolling(
        FROZEN["regime_window"], min_periods=FROZEN["regime_min_periods"]
    ).quantile(FROZEN["regime_percentile"]).shift(1)
    lookup = dict(zip(v["date"], sigma > hurdle))
    flags = df["date"].map(lookup)
    if flags.isna().any():
        missing = df.loc[flags.isna(), "date"].tolist()
        raise AssertionError(f"session dates missing from volatility frame: {missing[:5]}")
    return flags.fillna(False).astype(bool)


def apply_rule(df: pd.DataFrame, elevated: pd.Series, mode: str = "combined") -> pd.DataFrame:
    """Sequential sizing rule. mode in {combined, regime, cluster, full}.

    Returns per-session size_fraction plus the two flags used at decision time
    (cluster_active = the last two *taken* sessions both closed net-negative).
    """
    size = FROZEN["size_fraction"]
    k = FROZEN["cluster_k"]
    n = len(df)
    f = np.ones(n)
    regime_used = np.zeros(n, dtype=bool)
    cluster_used = np.zeros(n, dtype=bool)
    streak = 0
    for i in range(n):
        cluster_active = streak >= k
        use_regime = mode in ("combined", "regime") and bool(elevated.iloc[i])
        use_cluster = mode in ("combined", "cluster") and cluster_active
        f[i] = size if (use_regime or use_cluster) else 1.0
        regime_used[i] = bool(elevated.iloc[i])
        cluster_used[i] = cluster_active
        net_i = f[i] * float(df["net_v"].iloc[i]) - float(df["flat"].iloc[i])
        streak = streak + 1 if net_i < 0 else 0
    return pd.DataFrame(
        {"size_fraction": f, "regime_elevated": regime_used, "cluster_active": cluster_used}
    )


def scaled_series(df: pd.DataFrame, f: np.ndarray) -> pd.DataFrame:
    out = pd.DataFrame({"date": df["date"], "hedge_trades": df["hedge_trades"]})
    out["size_fraction"] = f
    out["net_pnl"] = f * df["net_v"].to_numpy() - df["flat"].to_numpy()
    out["cum_net"] = out["net_pnl"].cumsum()
    out["peak"] = out["cum_net"].cummax()
    out["drawdown"] = out["cum_net"] - out["peak"]
    return out


def summarize(series: pd.DataFrame, label: str, taken: np.ndarray | None = None) -> dict:
    net = series["net_pnl"]
    if taken is None:
        taken = np.ones(len(series), dtype=bool)
    taken_net = net[taken]
    n_taken = int(taken.sum())
    total = float(net.sum())
    ev = total / n_taken if n_taken else 0.0
    std = float(taken_net.std())
    sharpe = (ev / std) * math.sqrt(n_taken / FROZEN["years"]) if n_taken and std > 0 else 0.0
    gp = float(taken_net[taken_net > 0].sum())
    gl = abs(float(taken_net[taken_net < 0].sum()))
    max_dd = float(series["drawdown"].min())
    return {
        "label": label,
        "sessions": len(series),
        "taken_sessions": n_taken,
        "total_net_pnl": round(total, 2),
        "net_ev_per_trade": round(ev, 2),
        "win_rate": round(float((taken_net > 0).mean()), 4) if n_taken else 0.0,
        "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_inr": round(max_dd, 2),
        "max_drawdown_pct_of_2l": round(abs(max_dd) / (FROZEN["capital"] / 100.0), 2),
        "annual_net_pnl": round(total / FROZEN["years"], 2),
        "avg_size_fraction": round(float(series["size_fraction"].mean()), 3),
    }


def cluster_stop_series(df: pd.DataFrame, k: int) -> tuple[pd.DataFrame, np.ndarray]:
    """Full-size book that sits out `cooldown` sessions after k consecutive losses.

    Trigger fires when a *taken* loss extends the streak to >= k; the next
    `cooldown` sessions are skipped (flat: no orders, zero PnL, no fees), then
    trading resumes — a further taken loss re-arms the stop, a win resets it.
    """
    cooldown = FROZEN["stop_cooldown"]
    n = len(df)
    taken = np.zeros(n, dtype=bool)
    streak = 0
    cooldown_left = 0
    for i in range(n):
        if cooldown_left > 0:
            cooldown_left -= 1  # skipped session: no orders, zero PnL
            continue
        taken[i] = True
        net_i = float(df["net_pnl"].iloc[i])
        if net_i < 0:
            streak += 1
            if streak >= k:
                cooldown_left = cooldown
        else:
            streak = 0
    series = scaled_series(df, taken.astype(float))
    series.loc[~taken, "net_pnl"] = 0.0  # skipped = no orders, no fees
    series["cum_net"] = series["net_pnl"].cumsum()
    series["peak"] = series["cum_net"].cummax()
    series["drawdown"] = series["cum_net"] - series["peak"]
    return series, taken


def fixed_fraction_table(df: pd.DataFrame) -> list[dict]:
    rows = []
    for f in FROZEN["fixed_fractions"]:
        series = scaled_series(df, np.full(len(df), f))
        rows.append(summarize(series, f"f={f:g}"))
    return rows


def breakeven_fraction(df: pd.DataFrame, cap: float = None) -> dict:
    """Largest f on a 0.001 grid in [0.05, 1.0] with |max DD| <= cap.

    Also characterizes the DD(f) curve: flat per-order fees put a floor under the
    drawdown as f -> 0 (near-zero positions still pay ~Rs284/session of fixed
    fees), so DD(f) is U-shaped, not monotone.
    """
    cap = cap if cap is not None else FROZEN["kill_max_dd_inr"]
    n = len(df)
    net = df["net_pnl"].to_numpy()
    flat = df["flat"].to_numpy()
    fs = np.arange(1.0, 0.049, -0.001)
    dds = np.empty(len(fs))
    passing = None  # scan from f=1.0 down: first pass = largest passing f
    for j, f in enumerate(fs):
        pnl = f * net - (1.0 - f) * flat
        cum = pnl.cumsum()
        dds[j] = float((cum - np.maximum.accumulate(cum)).min())
        if passing is None and abs(dds[j]) <= cap:
            passing = (round(float(f), 3), round(float(dds[j]), 2), round(float(pnl.sum()), 2))
    j_min = int(np.argmin(np.abs(dds)))
    curve = {"f": [round(float(f), 3) for f in fs[::20]],
             "max_dd_inr": [round(float(d), 2) for d in dds[::20]]}
    return {"f_star": passing[0] if passing else None,
            "max_dd_at_f_star": passing[1] if passing else None,
            "total_net_at_f_star": passing[2] if passing else None,
            "annual_net_at_f_star": round(passing[2] / FROZEN["years"], 2) if passing else None,
            "first_failing_f_above": None if passing else round(float(fs[0]), 3),
            "grid_min_dd": {"f": round(float(fs[j_min]), 3), "max_dd_inr": round(float(dds[j_min]), 2)},
            "dd_curve_coarse": curve}


def gates(metrics: dict) -> dict:
    g1 = abs(metrics["max_drawdown_inr"]) <= FROZEN["kill_max_dd_inr"]
    g2 = metrics["net_ev_per_trade"] >= FROZEN["kill_min_ev_inr"]
    g3 = metrics["total_net_pnl"] >= FROZEN["kill_min_total_frac"] * FROZEN["e011_total_net"]
    return {
        "gate1_max_dd_le_16k": g1,
        "gate2_ev_ge_1200": g2,
        "gate3_total_ge_50pct_e011": g3,
        "verdict": "PASS" if (g1 and g2 and g3) else "FAIL",
    }


def run() -> dict:
    from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

    df = load_base()
    validate_decomposition(df)
    vdf = load_or_compute_volatility()
    elevated = elevated_flags(df, vdf)

    base_metrics = summarize(scaled_series(df, np.ones(len(df))), "E011 base f=1.0")

    primary_flags = apply_rule(df, elevated, "combined")
    primary_series = scaled_series(df, primary_flags["size_fraction"].to_numpy())
    primary = summarize(primary_series, "combined (regime OR cluster)")
    primary_gates = gates(primary)

    diagnostics = {}
    for mode in ("regime", "cluster"):
        flags = apply_rule(df, elevated, mode)
        diagnostics[mode] = summarize(
            scaled_series(df, flags["size_fraction"].to_numpy()), f"{mode}-only"
        )

    fractions = fixed_fraction_table(df)
    breakeven = breakeven_fraction(df)
    stops = []
    for k in FROZEN["stop_ks"]:
        series, taken = cluster_stop_series(df, k)
        stops.append(summarize(series, f"stop k={k} (cooldown {FROZEN['stop_cooldown']})", taken))

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    daily = pd.DataFrame({
        "date": df["date"],
        "sigma_gk_10d_t1": df["date"].map(
            dict(zip(pd.to_datetime(vdf["date"]).dt.date, vdf["sigma_gk_10d_t1"]))
        ),
        "regime_elevated": primary_flags["regime_elevated"],
        "cluster_active": primary_flags["cluster_active"],
        "size_fraction": primary_flags["size_fraction"],
        "net_pnl_full": df["net_pnl"],
        "net_pnl": primary_series["net_pnl"],
        "cum_net": primary_series["cum_net"],
        "peak": primary_series["peak"],
        "drawdown": primary_series["drawdown"],
        "hedge_trades": df["hedge_trades"],
    })
    daily.to_csv(ARTIFACTS / "sizing_daily.csv", index=False)

    metrics_out = {
        "frozen": FROZEN,
        "base": base_metrics,
        "primary": primary,
        "primary_gates": primary_gates,
        "diagnostics": diagnostics,
        "n_elevated_sessions": int(primary_flags["regime_elevated"].sum()),
        "n_cluster_half_sessions": int(
            (primary_flags["cluster_active"] & ~primary_flags["regime_elevated"]).sum()
        ),
    }
    with open(ARTIFACTS / "sizing_metrics.json", "w") as fh:
        json.dump(metrics_out, fh, indent=2)

    risk_budget = {
        "base_annual_net_pnl": round(FROZEN["e011_total_net"] / FROZEN["years"], 2),
        "fixed_fractions": fractions,
        "breakeven": breakeven,
        "cluster_stops": stops,
    }
    with open(ARTIFACTS / "risk_budget.json", "w") as fh:
        json.dump(risk_budget, fh, indent=2)

    return metrics_out


if __name__ == "__main__":
    m = run()
    print(json.dumps({
        "primary": m["primary"],
        "gates": m["primary_gates"],
        "diagnostics": m["diagnostics"],
    }, indent=2))
