"""e026 — real-price re-audit of the e013 pin harvest.

PREREG-frozen: ../PREREG.md (2026-10-03, before any code in this directory).

The design in one line: **the signal is frozen, only the mark moves.** e013's
selection walk is re-implemented deliberately rather than imported, so Gate 0
(control reproduces predecessor) is a genuine reproduction and not a tautology
against a shared helper.

Why this exists: e013's +Rs 4,14,721 is the repo's only surviving strategy
claim, and every rupee of it is a Black-Scholes output. No real option price
enters that number. e018 proved on its own book that model-reconstructed marks
are where phantom money lives (Rs 1,04,000 from a stale expiry-day close), and
that audit was never applied to e013.

Arms (PREREG section 4):
  A  CONTROL   e013 verbatim, BS marks on the e011 (void) IV  -> must land on
               the published number, else the audit is void
  B  REAL/VALID  real bhavcopy 4-leg close, front expiry re-derived from the
               trade date's own partition; expiry-day exits EXCLUDED
  C  REAL/INVALID  the same mark on expiry-day exits, reported separately and
               never pooled into the verdict (e018: expiry close is a stale
               last-trade price)
  D  CREDIT   e013's selection, credit re-priced on e018's contract-correct IV
  E  DECOMPOSITION  BS@15:15 vs BS@15:30 vs real@15:30 on identical sessions,
               separating a 15-minute timing mismatch from modelling error

One-sidedness is a property of the data, stated in PREREG section 3: there is
no intraday option price on disk, so the 12:35 entry credit stays
Black-Scholes in every arm. This audit can only make e013 look worse.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.feeds.bhavcopy import front_expiry as _front_expiry, parse_date, with_expiry_date
from core.feeds.intraday import load_intraday_candles
from core.pricing import bs_call, bs_put
from experiments.common.lots import lot_for_date

WALLS_DIR = ROOT / "experiments" / "e008_wall_flip" / "artifacts" / "walls"
HISTORICAL_DIR = ROOT / "data" / "historical"
E011_VOL = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts" / "volatility_daily.parquet"
E018_VOL = ROOT / "experiments" / "e018_vrp_weekly" / "artifacts" / "volatility_daily.parquet"
ARTIFACTS = HERE / "artifacts"

# --- e013's frozen constants. Changing any of these voids the control. -------
PIN_MAX_EXPANSION = 0.65          # e013 strategy A trigger
WING_WIDTH = 150.0                # e013 iron-fly wings, ATM +/- 150
STRIKE_STEP = 50.0                # e013 strike rounding
ENTRY_BAR = 40                    # 12:35 IST open
EXIT_BAR = 71                     # 15:15 IST close
T_EXIT_PUBLISHED = 0.0001         # e013's exit mark, in years. See PREREG s1.
EVENING_EXPIRY_FRACTION = 0.0265  # 10 min of 375 trading min, days -> years

CHAIN_COLS = ["symbol", "instrument", "expiry", "strike", "option_type", "close"]


# --------------------------------------------------------------- bhavcopy ---
def build_bhavcopy_calendar(root: Path | None = None) -> dict[_date, Path]:
    """trade_date -> partition path. Filenames are authoritative (0 mismatches)."""
    from datetime import datetime

    root = root or HISTORICAL_DIR
    cal: dict[_date, Path] = {}
    for f in root.glob("**/*.parquet"):
        stem = f.stem
        if stem.startswith("fo_") and len(stem) == 11 and stem[3:].isdigit():
            try:
                cal[datetime.strptime(stem[3:], "%Y%m%d").date()] = f
            except ValueError:
                continue
    return cal


def front_expiry(expiries, trade_date: _date):
    """Deprecated shim. The rule now lives in `core.feeds.bhavcopy.front_expiry`
    (e028) -- see the note there on why two copies of a contract-identity rule is
    one copy too many. Kept as a name so e027/e028 keep importing it."""
    return _front_expiry(expiries, trade_date)


def load_front_chain(cal: dict, d: _date):
    """NIFTY OPTIDX chain for `d`'s own partition, with its front expiry resolved.

    The expiry filter compares DATES, not strings. This used to be
    `df["expiry"] == str(fe)`, which matches nothing on every partition written
    in the legacy `DD-Mon-YYYY` encoding and silently returned an empty chain on
    all 2021-2024 sessions. That is the e028 conviction; the defective loader is
    kept beside this one as `load_front_chain_string_eq` because e028's control
    arm must be able to reproduce e026's published +Rs 61,842.51.
    """
    p = cal.get(d)
    if p is None:
        return None, None
    df = pd.read_parquet(p, columns=CHAIN_COLS)
    n = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")])
    if n.empty:
        return None, None
    fe = front_expiry({e for e in n["expiry_date"].unique() if e is not None}, d)
    if fe is None:
        return None, None
    return n[n["expiry_date"] == fe], fe


def load_front_chain_string_eq(cal: dict, d: _date):
    """**CONVICTED — do not use.** e026's original loader.

    `df["expiry"] == str(fe)` compares a formatted date against a raw string. The
    store holds two encodings (`04-Feb-2021` legacy, `2025-01-02` UDiff); ISO
    matches only the latter, so every pre-2025 session returned an empty chain,
    `debit_real` was None, and §5.5's fail-closed rule dropped the session as
    NO TRADE. It obeyed the rule perfectly and hid the bug inside correct
    behaviour.

    Retained, unused, solely as e028's control. See ../e028_expiry_encoding_audit.
    """
    p = cal.get(d)
    if p is None:
        return None, None
    df = pd.read_parquet(p, columns=CHAIN_COLS)
    n = df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")]
    if n.empty:
        return None, None
    expiries = {parse_date(str(e)) for e in n["expiry"].unique()}
    fe = front_expiry(expiries, d)
    if fe is None:
        return None, None
    return n[n["expiry"] == str(fe)], fe


def leg_close(chain: pd.DataFrame, strike: float, side: str):
    """Close for one leg, or None. A missing leg is NO TRADE, never interpolated."""
    q = chain[(chain["strike"] == float(strike)) & (chain["option_type"] == side)]
    if q.empty:
        return None
    v = q.iloc[0]["close"]
    return None if pd.isna(v) else float(v)


@dataclass
class Trade:
    """One audited pin session, with every mark computed once, up front."""
    date: _date
    lot: int
    atm: float
    wing_ce: float
    wing_pe: float
    dte: float
    iv: float
    expansion: float
    spot_entry: float
    spot_1230: float
    credit_pts: float                      # e013's BS credit, points
    entry_turnover_inr: float              # ATM straddle premium x lot
    debit_bs: float                        # e013's mark
    debit_bs_1530: float                   # same model, 15:30 spot
    debit_real: float | None               # real bhavcopy close, points
    front_expiry: _date | None = None
    expiry_is_trade_date: bool | None = None


# ------------------------------------------------------------------ marks ---
def fly_price(spot: float, atm: float, wing_ce: float, wing_pe: float,
              iv: float, t: float) -> float:
    """e013's iron-fly debit in points, priced on Black-Scholes at `iv`, `t`.

    Reproduces e013's own expression exactly: (ATM straddle) - (both wings).
    """
    if t <= 0:
        # e013's degenerate branch: pure intrinsic, no time value anywhere.
        return (max(spot - atm, 0.0) + max(atm - spot, 0.0)) - \
               (max(spot - wing_ce, 0.0) + max(wing_pe - spot, 0.0))
    return ((bs_call(spot, atm, iv, t) + bs_put(spot, atm, iv, t))
            - (bs_call(spot, wing_ce, iv, t) + bs_put(spot, wing_pe, iv, t)))


def intrinsic_debit(spot: float, atm: float, wing_ce: float, wing_pe: float) -> float:
    return fly_price(spot, atm, wing_ce, wing_pe, 0.0, 0.0)


def e013_credit(spot: float, atm: float, wing_ce: float, wing_pe: float,
                iv: float, dte: float) -> float:
    """e013's entry credit, with e013's own mixed day-count convention.

    Reproduced verbatim on purpose: the control must inherit e013's arithmetic,
    including its conventions, so that any difference in the result is
    attributable to the MARK and nothing else.
    """
    t = (0.426 / 365.0) if dte <= 0.01 else (dte - 0.5) / 365.0
    return fly_price(spot, atm, wing_ce, wing_pe, iv, t)


def e013_friction(entry_turnover_inr: float, lot: int) -> float:
    """e013's 4-leg friction model, verbatim: Rs 160 round-trip brokerage,
    0.1% STT on the ATM sell turnover, 6.0 pts/leg slippage x lot, GST."""
    return 160.0 + (0.001 * entry_turnover_inr) + (6.0 * lot) + (160.0 * 0.18)


# ------------------------------------------------------- selection walk -----
def _vol_frame(e011_path: Path = E011_VOL, e018_path: Path = E018_VOL):
    a = pd.read_parquet(e011_path).set_index("date")
    b = pd.read_parquet(e018_path).set_index("date")
    return a, b


def collect_trades(vol_e011: pd.DataFrame, cal: dict, loader=load_front_chain) -> list[Trade]:
    """e013's pin session, re-implemented. Selection only; marks attached later.

    `loader` is the one injectable part, so a follow-up can hold the signal
    frozen and move only the chain lookup. e028 uses it to run its control arm
    against the convicted `load_front_chain_string_eq`.
    """
    trades: list[Trade] = []
    for f in sorted(WALLS_DIR.glob("*.json")):
        d = parse_date(f.stem)
        if d not in vol_e011.index:
            continue
        row = vol_e011.loc[d]
        iv = float(row["iv_atm_t1"]) if pd.notna(row["iv_atm_t1"]) else 0.15
        dte = float(row["dte_t1"]) if pd.notna(row["dte_t1"]) else 1.0

        try:
            candles = load_intraday_candles(d)
        except Exception:
            continue
        if len(candles) < 72:
            continue

        # --- e013's signal, bars 0..39 only (09:15 -> 12:30) ------------------
        morning = candles.iloc[:40]
        range_1230 = float(morning["high"].max() - morning["low"].min())
        s_0920 = float(candles.iloc[1]["open"])
        atm_0920 = round(s_0920 / STRIKE_STEP) * STRIKE_STEP
        t0 = max(dte, 0.05) / 365.0
        straddle_0920 = bs_call(s_0920, atm_0920, iv, t0) + bs_put(s_0920, atm_0920, iv, t0)
        if straddle_0920 <= 5.0:
            continue
        expansion = range_1230 / straddle_0920
        if expansion > PIN_MAX_EXPANSION:
            continue  # not the pin arm; e013's breakout arm is out of scope here

        # --- entry at bar 40 open, exit at bar 71 close -----------------------
        s_entry = float(candles.iloc[ENTRY_BAR]["open"])
        s_exit = float(candles.iloc[EXIT_BAR]["close"])
        s_exit_1530 = float(candles.iloc[-1]["close"])
        atm = round(s_entry / STRIKE_STEP) * STRIKE_STEP
        lot = lot_for_date(d)
        wc, wp = atm + WING_WIDTH, atm - WING_WIDTH

        t_entry = (0.426 / 365.0) if dte <= 0.01 else (dte - 0.5) / 365.0
        credit = e013_credit(s_entry, atm, wc, wp, iv, dte)
        atm_entry_px = bs_call(s_entry, atm, iv, t_entry) + bs_put(s_entry, atm, iv, t_entry)

        # --- e013's exit mark, verbatim ---------------------------------------
        debit_bs = intrinsic_debit(s_exit, atm, wc, wp) if dte <= 0.01 else \
            fly_price(s_exit, atm, wc, wp, iv, T_EXIT_PUBLISHED)
        debit_bs_1530 = intrinsic_debit(s_exit_1530, atm, wc, wp) if dte <= 0.01 else \
            fly_price(s_exit_1530, atm, wc, wp, iv, T_EXIT_PUBLISHED)

        # --- the real mark -----------------------------------------------------
        chain, fe = loader(cal, d)
        debit_real = None
        if chain is not None:
            legs = {
                ("CE", atm): leg_close(chain, atm, "CE"),
                ("PE", atm): leg_close(chain, atm, "PE"),
                ("CE", wc): leg_close(chain, wc, "CE"),
                ("PE", wp): leg_close(chain, wp, "PE"),
            }
            if all(v is not None for v in legs.values()):
                debit_real = ((legs[("CE", atm)] + legs[("PE", atm)])
                              - (legs[("CE", wc)] + legs[("PE", wp)]))

        trades.append(Trade(
            date=d, lot=lot, atm=atm, wing_ce=wc, wing_pe=wp, dte=dte, iv=iv,
            expansion=expansion, spot_entry=s_entry, spot_1230=s_exit,
            credit_pts=credit, entry_turnover_inr=atm_entry_px * lot,
            debit_bs=debit_bs, debit_bs_1530=debit_bs_1530, debit_real=debit_real,
            front_expiry=fe,
            expiry_is_trade_date=(fe == d) if fe is not None else None,
        ))
    return trades


# ------------------------------------------------------------------ gates ---
def iron_fly_bounds(entry_value_pts: float, lot: int) -> tuple[float, float]:
    """Closed-form gross-PnL bounds for e013's iron butterfly, in rupees.

    e013's convention: `fly_value` = ATM straddle minus both wings, so the
    book profits when that value decays (gross = entry_value - exit_value).

    At an EXPIRY mark the payoff is fully determined by spot and is
    min(|S - K_atm|, WING_WIDTH) — it cannot be negative and cannot exceed the
    wing width. Hence, for expiry marks only:

        (entry_value - WING_WIDTH) * lot  <=  gross  <=  entry_value * lot

    Neither bound holds at an intraday mark: an ATM straddle with days of life
    can exceed 150 points, and wings carry time value too. So this audit is
    asserted on expiry marks only, and is skipped elsewhere rather than
    producing a false violation. See PREREG section 9, amendment 1.
    """
    return (entry_value_pts - WING_WIDTH) * lot, entry_value_pts * lot


def check_identity(trades: list[Trade], cal: dict) -> tuple[int, list[str]]:
    """Gate 1. Re-derive each trade's front expiry from the trade date's own
    partition, per trade, and fail the run on a single mismatch."""
    bad: list[str] = []
    for t in trades:
        _, fe = load_front_chain(cal, t.date)
        if fe != t.front_expiry:
            bad.append(f"{t.date}: marked {t.front_expiry} but own-partition says {fe}")
    return len(bad), bad


def check_impossibility(trades: list[Trade]) -> tuple[int, list[str], list[str]]:
    """Gate 5. Cheap, general, and it caught Rs 1,04,000 in e018.

    The bound is asserted only where the mark is TRUSTWORTHY:

      * Black-Scholes marks are asserted when e013 took its intrinsic branch
        (`dte <= 0.01`) — there the mark IS the expiry payoff, exactly.
      * Real bhavcopy marks are asserted only when the front expiry is NOT the
        trade date. On expiry day the `close` is a stale last trade (e018
        measured 0.30 on options expiring at 0.00), so a breach there is a
        known data artifact, not a pricing bug. Those are returned separately
        as EVIDENCE for Arm C's exclusion, and never counted as gate failures.
    """
    bad: list[str] = []
    untrusted: list[str] = []
    for t in trades:
        lo, hi = iron_fly_bounds(t.credit_pts, t.lot)
        # (mark, is_expiry_payoff, is_the_price_trustworthy)
        #
        # Applicability and trust are SEPARATE. An expiry-day real close IS the
        # expiry payoff (so the bound applies) but a stale last trade (so a
        # breach is evidence rather than a pricing bug). Collapsing the two
        # would hide the very artifact e018 documented.
        #
        # The real-mark entry previously asserted the bound on EVERY mark
        # (`True`), which contradicts this function's own docstring: a fly with
        # days of life left can sit outside [entry - W, entry] when spot moves
        # fast or IV expands. It never fired because the one corrected-sample
        # session that breaches it is one the expiry-encoding bug had excluded
        # (e028: 2023-12-20, a 374-pt afternoon sell-off with the ATM straddle
        # up 2.4x). Asserted on expiry marks only, per the docstring. The bound
        # that does hold at any mark is per-leg -- no traded option closes
        # materially below intrinsic -- and e028 enforces that one instead.
        checks = [
            ("bs", t.debit_bs, t.dte <= 0.01, True),
            ("bs_1530", t.debit_bs_1530, t.dte <= 0.01, True),
            ("real", t.debit_real, bool(t.expiry_is_trade_date),
             not bool(t.expiry_is_trade_date)),
        ]
        for name, debit, at_expiry, trusted in checks:
            if debit is None or not at_expiry:
                continue
            gross = (t.credit_pts - debit) * t.lot
            msg = f"{t.date} [{name}] gross {gross:.2f} vs bounds [{lo:.2f}, {hi:.2f}]"
            if gross > hi + 1e-6 or gross < lo - 1e-6:
                (bad if trusted else untrusted).append(msg)
    return len(bad), bad, untrusted


# ------------------------------------------------------------- statistics ---
def stats(net: pd.Series) -> dict:
    """The repo's standard metric block, matching e013's own accounting."""
    net = net.dropna()
    n = len(net)
    if n == 0:
        return {"trades": 0}
    wins, losses = net[net > 0], net[net < 0]
    cum = net.cumsum()
    gl = abs(float(losses.sum()))
    return {
        "trades": n,
        "trades_per_year": round(n / 5.7, 1),
        "total_net_pnl": round(float(net.sum()), 2),
        "net_ev_per_trade": round(float(net.mean()), 2),
        "win_rate": round(float((net > 0).mean()), 4),
        "profit_factor": round(float(wins.sum()) / gl, 2) if gl > 0 else None,
        "max_drawdown_inr": round(float((cum - cum.cummax()).min()), 2),
    }


def run() -> tuple[pd.DataFrame, dict]:
    vol_e011, vol_e018 = _vol_frame()
    cal = build_bhavcopy_calendar()

    trades = collect_trades(vol_e011, cal)
    df = pd.DataFrame([asdict(t) for t in trades])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)

    df["friction"] = [e013_friction(r.entry_turnover_inr, r.lot) for r in df.itertuples()]
    df["net_A"] = (df.credit_pts - df.debit_bs) * df.lot - df.friction
    df["net_bs_1530"] = (df.credit_pts - df.debit_bs_1530) * df.lot - df.friction
    df["net_real"] = np.where(df.debit_real.notna(),
                              (df.credit_pts - df.debit_real) * df.lot - df.friction,
                              np.nan)

    # Arm D: the same selection, credit re-priced on the corrected IV.
    cred_corrected = []
    for t in trades:
        d = t.date
        if d in vol_e018.index and pd.notna(vol_e018.loc[d, "iv_signal_t1"]):
            iv_c = float(vol_e018.loc[d, "iv_signal_t1"])
            cred_corrected.append(e013_credit(t.spot_entry, t.atm, t.wing_ce,
                                              t.wing_pe, iv_c, t.dte))
        else:
            cred_corrected.append(np.nan)
    df["credit_corrected"] = cred_corrected
    df["net_D"] = (df.credit_corrected - df.debit_bs) * df.lot - df.friction

    # --- the sample split, which decides what may be believed ----------------
    df["mark_valid"] = df.debit_real.notna() & (~df.expiry_is_trade_date.fillna(True))

    # --- gates ---------------------------------------------------------------
    n_identity, id_fail = check_identity(trades, cal)
    n_imposs, imp_fail, stale_close_evidence = check_impossibility(trades)

    arm_A = stats(df.net_A)
    arm_B = stats(df.loc[df.mark_valid, "net_real"])
    arm_C = stats(df.loc[~df.mark_valid & df.debit_real.notna(), "net_real"])
    paired = df.dropna(subset=["net_real"])

    coverage = float(df.debit_real.notna().mean())

    gates = {
        "0_control_reproduces_predecessor": {
            "bar": "arm A within Rs 1 of +4,14,721; n=193; PF 9.41",
            "observed_net": arm_A.get("total_net_pnl"),
            "observed_n": arm_A.get("trades"),
            "observed_pf": arm_A.get("profit_factor"),
            "pass": (arm_A.get("trades") == 193
                     and abs((arm_A.get("total_net_pnl") or 0) - 414721.0) <= 1.0),
        },
        "1_contract_identity_of_exit_mark": {
            "bar": "0 mismatches, re-derived per trade from the trade date's own partition",
            "observed": n_identity,
            "pass": n_identity == 0,
        },
        "5_arithmetic_impossibility": {
            "bar": "0 violations of the closed-form iron-fly bound",
            "observed": n_imposs,
            "pass": n_imposs == 0,
        },
        "2_real_mark_coverage": {
            "bar": ">=50% of arm A sessions carry a complete 4-leg real chain",
            "observed_pct": round(100 * coverage, 2),
            "pass": coverage >= 0.50,
        },
        "3_edge_survives_real_marks": {
            "bar": "arm B net EV >= +600 per trade",
            "observed": arm_B.get("net_ev_per_trade"),
            "pass": (arm_B.get("net_ev_per_trade") or -1e9) >= 600.0,
        },
        "4_profit_factor_survives_real_marks": {
            "bar": "arm B PF >= 1.50",
            "observed": arm_B.get("profit_factor"),
            "pass": (arm_B.get("profit_factor") or 0.0) >= 1.50,
        },
    }
    audit_valid = all(gates[g]["pass"] for g in ("0_control_reproduces_predecessor",
                                                 "1_contract_identity_of_exit_mark",
                                                 "5_arithmetic_impossibility",
                                                 "2_real_mark_coverage"))
    book_survives = gates["3_edge_survives_real_marks"]["pass"] and \
        gates["4_profit_factor_survives_real_marks"]["pass"]
    if not audit_valid:
        verdict = "AUDIT VOID — the audit's own gates failed; no verdict about e013"
    elif book_survives:
        verdict = "SURVIVES REAL MARKS (restate at arm B; published figure does not ship un-audited)"
    else:
        # E028: when this experiment's loader was corrected, gate 3 stopped
        # passing — arm B's EV fell to +353 on the recovered 129-session sample.
        # "Pending correction" was written before that happened; it is no
        # longer pending. The restatement is the verdict.
        verdict = ("DOES NOT SURVIVE REAL MARKS — published +4,14,721 struck and the "
                   "corrected real-mark arm fails its own kill bar (EV +353 vs +600). "
                   "At a realistic 2.0 pts/leg fill it is negative; see e028.")

    metrics = {
        "experiment": "e026_realmark_audit",
        "prereg": "PREREG.md (2026-10-03)",
        "verdict": verdict,
        "audit_valid": audit_valid,
        "book_survives_real_marks": book_survives,
        "gates": gates,
        "arms": {
            "A_control_published_convention": arm_A,
            "B_real_marks_valid_sample": arm_B,
            "C_real_marks_expiry_day_EXCLUDED_FROM_VERDICT": arm_C,
            "D_credit_on_corrected_iv": stats(df.net_D),
        },
        "gap_decomposition": {
            "note": "identical sessions only; separates timing from modelling",
            "n": len(paired),
            "bs_1515": round(float(paired.net_A.sum()), 2),
            "bs_1530": round(float(paired.net_bs_1530.sum()), 2),
            "real_1530": round(float(paired.net_real.sum()), 2),
            "gap_from_timing": round(float(paired.net_A.sum() - paired.net_bs_1530.sum()), 2),
            "gap_from_modelling": round(float(paired.net_bs_1530.sum() - paired.net_real.sum()), 2),
            "per_session_gap_mean": round(float((paired.net_A - paired.net_real).mean()), 2),
            "per_session_gap_std": round(float((paired.net_A - paired.net_real).std()), 2),
            "sign_flips": int(((paired.net_A > 0) != (paired.net_real > 0)).sum()),
        },
        "composition": {
            "dte_distribution": {int(k): int(v) for k, v in
                                  sorted(df.dte.value_counts().items())},
            "sessions_dte_le_1": int((df.dte <= 1).sum()),
            "sessions_dte_ge_2": int((df.dte >= 2).sum()),
            "pct_pnl_from_dte_ge_2": round(
                float(df.loc[df.dte >= 2, "net_A"].sum() / df.net_A.sum() * 100), 1),
        },
        "diagnostics": {
            "identity_failures": id_fail[:10],
            "impossibility_failures": imp_fail[:10],
            "expiry_day_close_violations_EXCLUDED_AS_KNOWN_ARTIFACT": stale_close_evidence[:10],
            "expiry_day_close_violation_count": len(stale_close_evidence),
        },
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(ARTIFACTS / "audit_trades.csv", index=False)
    (ARTIFACTS / "verdict.json").write_text(json.dumps(metrics, indent=2))
    return df, metrics


if __name__ == "__main__":
    _, m = run()
    print(json.dumps({k: v for k, v in m.items() if k != "diagnostics"}, indent=2))