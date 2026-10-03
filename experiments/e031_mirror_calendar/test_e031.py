"""Self-checks for e031. No network; every function takes its data as arguments.

PREREG.md line 4 makes a specific claim:

    Machine-checked by `test_e031.py::test_prereg_bars_match_the_code`.

When this experiment was written that sentence was not true -- the file it names
did not exist, so nothing verified that the gate bars frozen in the PREREG were
still the bars the code evaluates. That is the hole this suite closes. The
claim's symbol is defined at module level with exactly the name the PREREG
quotes, so the node id it writes resolves under pytest; TestPreregFrozen
re-exposes the same assertion as a TestCase method because this repo runs
unittest, which collects only TestCase methods. Two entry points, one
assertion: the sentence is true under either runner.

The single most important thing this suite pins is a NEGATIVE. e031 is LEAD
DEAD: the mirror calendar collects a real credit and the back leg's residual
time value consumes it, so median net PnL is negative and gate 5 fails. If that
ever flips positive, this file fails and the plan must be revisited -- which is
the point of freezing the measurement before trusting it.
"""
from __future__ import annotations

import re
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from experiments.e031_mirror_calendar.mirror_calendar import (
    ARTIFACTS,
    CONTROL_TOL,
    COVER_BAR,
    RHO_BAR,
    TOL,
    _atm,
    _closes,
    run,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "PREREG.md"

# (gate, the literal the PREREG's own gate row must contain, the code constant,
#  the value the PREREG froze). An inline literal in the engine has no row here,
#  which is exactly why the bars were lifted to module constants.
BARS = (
    (0, "paisa", CONTROL_TOL, 1e-9),
    (2, "90%", COVER_BAR, 90.0),
    (3, "1e-6", TOL, 1e-6),
    (4, "0.05", RHO_BAR, 0.05),
)


def gate_row(txt: str, n: int) -> str:
    """The PREREG's gates-table row for gate `n`, or raise."""
    for line in txt.splitlines():
        if line.startswith(f"| **{n}** |"):
            return line
    raise AssertionError(f"PREREG gates table has no row for gate {n}")


def test_prereg_bars_match_the_code():
    """The symbol PREREG.md names. See the module docstring.

    A bar loosened in the engine without touching the PREREG is no longer the
    bar that was frozen, and a bar in the PREREG the engine does not evaluate is
    a bar nobody runs. Both directions are checked here.
    """
    txt = PREREG.read_text(encoding="utf-8")

    for n, needle, constant, frozen in BARS:
        if constant != frozen:
            raise AssertionError(
                f"gate {n}: engine constant {constant!r} != PREREG frozen {frozen!r}")
        row = gate_row(txt, n)
        if needle not in row:
            raise AssertionError(
                f"gate {n}: PREREG row does not contain {needle!r}: {row!r}")

    # Gate 5 has no numeric constant -- its bar is a pair of signs on measured
    # medians -- but the row must exist or the gate is undocumented.
    gate_row(txt, 5)


class TestPreregFrozen(unittest.TestCase):
    """The PREREG must be frozen BEFORE the code, and must still describe what
    the code actually does. If a bar is edited here and not in the PREREG, or
    vice versa, this fails -- that is the whole anti-post-hoc mechanism."""

    def test_prereg_bars_match_the_code(self):
        """Same assertion as the module-level function of this name.

        Deliberately two entry points: the PREREG quotes the bare pytest node id
        `test_e031.py::test_prereg_bars_match_the_code`, which only resolves for
        a module-level function, but this repo runs `python -m unittest`, which
        collects only TestCase methods. Without this method the claim would be
        true under pytest and silently false here.
        """
        test_prereg_bars_match_the_code()

    def test_prereg_exists_and_declares_every_gate(self):
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("PREREG-frozen", txt)
        for n in range(6):
            gate_row(txt, n)

    def test_prereg_names_a_test_that_actually_exists(self):
        """The claim itself, checked rather than assumed.

        This is the assertion whose absence let PREREG.md quote a machine check
        that no machine was performing.
        """
        txt = PREREG.read_text(encoding="utf-8")
        m = re.search(r"`(test_e031\.py)::(\w+)`", txt)
        self.assertIsNotNone(m, "PREREG does not name `test_e031.py::<symbol>`")
        self.assertTrue((HERE / m.group(1)).exists(),
                        f"PREREG names {m.group(1)}, which does not exist")
        symbol = m.group(2)
        self.assertTrue(callable(globals().get(symbol)),
                        f"{m.group(1)} defines no callable {symbol}")
        self.assertIn(symbol, {k for k in dir(TestPreregFrozen)
                               if k.startswith("test_")},
                      f"{symbol} is not reachable under unittest collection")

    # NOTE: there is deliberately no mtime "PREREG is older than the code" test.
    # Fixing a typo in the PREREG is legitimate and would fail it, so it
    # punishes the wrong action and proves nothing. The bar comparison above is
    # the real freeze mechanism -- it compares the bars themselves, which is what
    # "frozen before the numbers were seen" has to mean.

    def test_gate0_scope_note_is_recorded(self):
        """Gate 0's row claimed 1,415 sessions; this experiment resolves 1,085
        and the control can only compare what both experiments resolved.

        The bar itself never changed -- only the denominator the row names.
        A correction to a frozen PREREG has to be visible on its face, so the
        disclosure is asserted like any other claim.
        """
        txt = PREREG.read_text(encoding="utf-8")
        row = gate_row(txt, 0)
        self.assertNotIn("on 1,415 sessions", row)
        self.assertIn("1,085", row)
        self.assertIn("Scope note on gate 0", txt)
        self.assertIn("The bar is unchanged", txt)
        self.assertIn("after the full run", txt)

    def test_the_derivation_gate_is_labelled_as_one_in_the_engine(self):
        """Gate 4's bar rests on a PREREG derivation error (spot enters PnL via
        TV1, which falls with moneyness). The engine must say so where a reader
        will see it, not only in the verdict artifact."""
        src = (HERE / "mirror_calendar.py").read_text(encoding="utf-8")
        self.assertIn("DERIVATION ERROR", src)


class TestSignConvention(unittest.TestCase):
    """The credit sign is the whole experiment. A flipped convention would
    report the mirror structure as its own opposite -- e031 would then be
    quoting e030's debit as a credit."""

    @staticmethod
    def _chain() -> pd.DataFrame:
        front, nxt = date(2025, 3, 13), date(2025, 3, 20)
        return pd.DataFrame([
            {"expiry_date": front, "strike": 22500.0, "option_type": "CE", "close": 60.0},
            {"expiry_date": front, "strike": 22500.0, "option_type": "PE", "close": 55.0},
            {"expiry_date": front, "strike": 23000.0, "option_type": "CE", "close": 90.0},
            {"expiry_date": front, "strike": 23000.0, "option_type": "PE", "close": 95.0},
            {"expiry_date": nxt, "strike": 22500.0, "option_type": "CE", "close": 80.0},
            {"expiry_date": nxt, "strike": 22500.0, "option_type": "PE", "close": 75.0},
        ])

    def test_credit_is_back_minus_front_and_positive(self):
        """e030's debit is e031's credit: same two prices, opposite sign."""
        chain = self._chain()
        front, nxt = date(2025, 3, 13), date(2025, 3, 20)
        f = _closes(chain, front, 22500.0)
        b = _closes(chain, nxt, 22500.0)
        credit = (b["CE"] + b["PE"]) - (f["CE"] + f["PE"])
        self.assertAlmostEqual(credit, 155.0 - 115.0, places=6)
        self.assertGreater(credit, 0)  # back richer -> buying front receives credit

    def test_atm_is_the_tightest_straddle(self):
        self.assertEqual(_atm(self._chain(), date(2025, 3, 13)), 22500.0)

    def test_missing_leg_is_none_never_interpolated(self):
        chain = self._chain()
        self.assertIsNone(_closes(chain, date(2025, 4, 10), 22500.0))
        one_side = pd.DataFrame([
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "CE", "close": 80.0},
        ])
        self.assertIsNone(_closes(one_side, date(2025, 3, 20), 22500.0))

    def test_zero_close_is_treated_as_missing(self):
        zero = pd.DataFrame([
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "CE", "close": 0.0},
            {"expiry_date": date(2025, 3, 20), "strike": 22500.0,
             "option_type": "PE", "close": 75.0},
        ])
        self.assertIsNone(_closes(zero, date(2025, 3, 20), 22500.0))


class TestResult(unittest.TestCase):
    """Runs the full store once (class-level) and pins the verdict.

    Costs ~40s: 1,415 partitions, each with an intraday spot lookup for the
    expiry session. That is the price of asserting on the real number rather
    than on a fixture of it.
    """

    @classmethod
    def setUpClass(cls):
        cls.df, cls.metrics = run()
        cls.gates = cls.metrics["gates"]
        cls.good = cls.df[cls.df["eligible"] & cls.df["ok"]].copy()  # noqa: E712

    # ---- gates 0-3: the audit gates, which void unconditionally if they fail

    def test_control_reproduces_e030(self):
        """Gate 0. Two independent implementations of the same entry credit.

        Deliberate duplication, not DRY debt: mirror_calendar.py re-implements
        _chain/_atm/_closes rather than importing e030's, precisely so this
        comparison is between two separate readings of the store. Refactoring
        the loaders into a shared helper would make this gate tautological.
        """
        g = self.gates["0_control_vs_e030"]
        self.assertTrue(g["pass"], g)
        self.assertLess(g["max_abs_diff"], CONTROL_TOL)
        # The control covered every session e031 resolved, not a subset of them.
        self.assertEqual(g["n"], int(self.df["ok"].sum()))
        self.assertGreater(g["n"], 0)

    def test_contract_identity_holds(self):
        g = self.gates["1_contract_identity"]
        self.assertTrue(g["pass"])
        self.assertEqual(g["front_equals_next"], 0)
        self.assertEqual(g["exit_identity_mismatches"], 0)
        self.assertEqual(g["n_resolved"], int(len(self.good)))
        # exit legs re-derive the SAME back expiry we entered short
        self.assertFalse((self.good["front"] == self.good["next"]).any())

    def test_coverage_is_published_per_year(self):
        """Gate 2. The PREREG bar is per year; an aggregate would let 2023's
        weakest year hide behind five stronger ones (s5.14)."""
        g = self.gates["2_coverage_published_first"]
        years = [r["year"] for r in g["per_year"]]
        self.assertEqual(years, [2021, 2022, 2023, 2024, 2025, 2026])
        for r in g["per_year"]:
            self.assertGreaterEqual(
                r["coverage_pct"], COVER_BAR,
                f"{r['year']} coverage {r['coverage_pct']}% below the frozen bar")
            self.assertGreater(r["sessions"], 0)
        self.assertGreaterEqual(g["worst_year_coverage_pct"], COVER_BAR)
        self.assertTrue(g["pass"])

    def test_arithmetic_identity_holds_on_every_survivor(self):
        """Gate 3. PnL == credit - TV1 exactly, and TV1 >= 0 on what survives.

        This is the contract guard: an exit leg fetched from the wrong contract
        breaks the identity, so an identity error is a wrong object, not a tail.
        """
        g = self.gates["3_arithmetic_impossibility"]
        self.assertTrue(g["pass"])
        self.assertLess(g["identity_max_error"], TOL)
        self.assertEqual(g["violations_remaining_in_result"], 0)

        ident = (self.good["credit"].astype(float)
                 - self.good["tv1"].astype(float)
                 - self.good["gross"].astype(float)).abs().max()
        self.assertLess(float(ident), TOL)
        self.assertGreaterEqual(float(self.good["tv1"].astype(float).min()), -TOL)

    # ---- the two disclosed amendments: counted, never absorbed -------------

    def test_the_inconsistent_marks_are_counted_not_silently_dropped(self):
        """Amendment 1. 22 sessions carry a back-leg close below its own
        intrinsic -- a stale last-trade price, not a usable mark. Fail-closed
        means excluded AND counted. A test that only checked the survivors would
        pass whether the exclusion ran or not."""
        raw = self.gates["3_arithmetic_impossibility"][
            "raw_mark_flags_before_exclusion"]
        self.assertGreater(raw, 0, "the 22 bad exit marks are no longer counted")
        self.assertEqual(
            int(self.df["reason"].eq("exit_mark_inconsistent").sum()), raw)
        self.assertFalse(self.df.loc[
            self.df["reason"] == "exit_mark_inconsistent", "ok"].any())
        self.assertIn("amendment_1_inconsistent_exit_marks",
                      self.metrics["post_hoc_diagnosis"])

    def test_gate4_fails_and_the_failure_is_disclosed(self):
        """Amendment 2. Gate 4's frozen bar was derived from a wrong argument:
        spot does not enter the identity, but it enters through TV1, because a
        straddle's time value falls with moneyness.

        The PREREG maps a gate-4 failure to 'AUDIT VOID, quote no number'. The
        verdict overrides that mapping, so the override must be visible in the
        verdict itself rather than only in this file -- a silent reclassification
        is the failure mode the PREREG was written to prevent.
        """
        g = self.gates["4_spot_independence"]
        self.assertFalse(g["pass"])
        self.assertTrue(g["prereg_prediction_was_wrong"])
        self.assertGreater(g["spearman_rho"], RHO_BAR)  # rho measured 0.84

        # What the gate was meant to catch is covered elsewhere, and measured:
        self.assertLess(abs(g["diagnostic_rho_move_vs_credit"]), 0.20)
        self.assertLess(g["diagnostic_rho_move_vs_tv1"], -0.50)

        verdict = self.metrics["verdict"]
        self.assertIn("AUDIT VOID", verdict)          # the mapping being overridden
        self.assertIn("DISCLOSED PREREG AMENDMENT", verdict)  # the override itself
        diag = self.metrics["post_hoc_diagnosis"]
        self.assertIn("amendment_2_gate4_derivation_error", diag)
        self.assertTrue(diag["amendment_2_gate4_derivation_error"].strip())

    # ---- gate 5 and the finding ------------------------------------------

    def test_edge_does_not_survive_friction(self):
        """THE FINDING. The credit is real; the residual time value eats it."""
        g = self.gates["5_edge_survives_friction"]
        self.assertFalse(g["pass"])
        self.assertLess(g["median_net"], 0)
        self.assertLess(g["median_net_2x"], 0)
        self.assertLess(self.metrics["net_after_friction"]["ev_per_trade"], 0)
        self.assertLess(self.metrics["pnl_distribution"]["median_gross"], 0)

    def test_residual_time_value_consumes_the_credit(self):
        """The mechanism, stated as a number: at this tenor the back leg keeps
        slightly more time value on average than the entry credit collects."""
        cv = self.metrics["credit_vs_residual_time_value"]
        self.assertGreater(cv["median_tv1"], cv["median_credit"])
        self.assertGreater(cv["median_credit"], 0)  # the credit itself is real
        self.assertLess(cv["frac_credit_exceeds_tv1"], 0.50)

    def test_the_verdict_is_lead_dead(self):
        self.assertIn("LEAD DEAD", self.metrics["verdict"])
        n_fail = sum(1 for v in self.gates.values() if not v["pass"])
        self.assertEqual(n_fail, self.metrics["gates_failed"])
        self.assertEqual(n_fail, 2)  # gates 4 and 5, no others

    def test_coverage_is_reported_before_the_pnl(self):
        cov = self.metrics["coverage"]
        self.assertEqual(cov["sessions_total"], 1415)
        self.assertEqual(cov["eligible_sessions"], int(self.df["eligible"].sum()))
        self.assertEqual(cov["excluded"], int((~self.df["ok"]).sum()))
        self.assertEqual(cov["per_year"], self.gates["2_coverage_published_first"]["per_year"])

    def test_artifacts_written(self):
        self.assertTrue((ARTIFACTS / "verdict.json").exists())
        self.assertTrue((ARTIFACTS / "session_pnl.csv").exists())
        self.assertTrue((PREREG).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
