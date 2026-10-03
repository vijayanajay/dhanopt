"""Self-checks for e032. No network; every function takes its data as arguments.

PREREG.md line 4 claims:

    Machine-checked by `test_e032.py::test_prereg_bars_match_the_code`.

That sentence is the thing e031 got wrong, so e032 does not get to get it wrong
again. The symbol is defined at module level under exactly that name so the node
id the PREREG writes resolves under pytest, and re-exposed as a TestCase method
because this repo runs unittest, which collects only TestCase methods.

Three things this suite pins that the ordinary result checks do not:

1. **The verdict mapping has no override clause.** e031's verdict field carried
   a 400-character argument for why its own frozen kill bar should be read as
   something other than what it says. `_verdict` is a pure function precisely so
   that can be tested directly against synthetic gate sets instead of argued in
   prose.

2. **The PREREG's central constraint, as code:** a NEW bar can only void, never
   validate. Whatever 4a and 4b do, a failing gate 5 can never be answered with
   `ELIGIBLE`.

3. **e032 reproduces e031 exactly.** The sample has been seen; the only thing
   e032 adds is a gate set that was defensible when frozen. If the numbers move,
   it is not the same measurement and nothing here may be quoted.

The expected result is a NEGATIVE: LEAD DEAD, with gate 5 the only gate that
fails and no PREREG amendment applied.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from experiments.e031_mirror_calendar.mirror_calendar import (
    CONTROL_TOL,
    COVER_BAR,
    TOL,
)
from experiments.e032_mirror_calendar_recheck.mirror_recheck import (
    ARTIFACTS,
    AUDIT_KEYS,
    TV_SIGN_BAR,
    WRONG_LEG_BAR,
    _pinned,
    _verdict,
    run,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "PREREG.md"
E031_VERDICT = HERE.parents[0] / "e031_mirror_calendar" / "artifacts" / "verdict.json"

# (gate id, the literal the PREREG's own gate row must contain, code constant,
#  the value the PREREG froze). None for bars that are a count or a sign and
#  therefore have no numeric constant to loosen.
BARS = (
    ("0", "1e-9", CONTROL_TOL, 1e-9),
    ("1", "mismatch", None, None),
    ("2", "90%", COVER_BAR, 90.0),
    ("3", "1e-6", TOL, 1e-6),
    ("4a", "0.20", WRONG_LEG_BAR, 0.20),
    ("4b", "< 0", TV_SIGN_BAR, 0.0),
    ("5", "sign-only", None, None),
)

FULL = {k: {"pass": True} for k in AUDIT_KEYS}
FULL["5_edge_survives_friction"] = {"pass": True}


def gate_row(txt: str, n: str) -> str:
    """The PREREG's gates-table row for gate `n`, or raise."""
    for line in txt.splitlines():
        if line.startswith(f"| **{n}** |"):
            return line
    raise AssertionError(f"PREREG gates table has no row for gate {n}")


def test_prereg_bars_match_the_code():
    """The symbol PREREG.md names. See the module docstring.

    A bar loosened in the engine without touching the PREREG is no longer the
    bar that was frozen; a bar in the PREREG the engine does not evaluate is a
    bar nobody runs. Both directions are checked.
    """
    txt = PREREG.read_text(encoding="utf-8")

    for n, needle, constant, frozen in BARS:
        if constant is not None and constant != frozen:
            raise AssertionError(
                f"gate {n}: engine constant {constant!r} != PREREG frozen {frozen!r}")
        row = gate_row(txt, n)
        if needle not in row:
            raise AssertionError(
                f"gate {n}: PREREG row does not contain {needle!r}: {row!r}")

    if "CARRIED" not in txt or "NEW" not in txt:
        raise AssertionError("PREREG does not classify bars as CARRIED / NEW")


class TestPreregFrozen(unittest.TestCase):
    """The PREREG must be frozen BEFORE the code, and must still describe what
    the code actually does. No mtime test: fixing a typo in the PREREG is
    legitimate and would fail it, so it punishes the wrong action and proves
    nothing. The bar comparison is the real freeze mechanism."""

    def test_prereg_bars_match_the_code(self):
        """Same assertion as the module-level function of this name.

        Two entry points on purpose: the PREREG quotes the bare pytest node id
        `test_e032.py::test_prereg_bars_match_the_code`, which only resolves for
        a module-level function, but `python -m unittest` collects only
        TestCase methods. Without this method the claim would be true under
        pytest and silently false here.
        """
        test_prereg_bars_match_the_code()

    def test_prereg_exists_and_declares_every_gate(self):
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("PREREG-frozen", txt)
        for n, *_ in BARS:
            gate_row(txt, n)

    def test_prereg_names_a_test_that_actually_exists(self):
        txt = PREREG.read_text(encoding="utf-8")
        m = re.search(r"`(test_e032\.py)::(\w+)`", txt)
        self.assertIsNotNone(m, "PREREG does not name `test_e032.py::<symbol>`")
        self.assertTrue((HERE / m.group(1)).exists(),
                        f"PREREG names {m.group(1)}, which does not exist")
        symbol = m.group(2)
        self.assertTrue(callable(globals().get(symbol)),
                        f"{m.group(1)} defines no callable {symbol}")
        self.assertIn(symbol, {k for k in dir(TestPreregFrozen)
                               if k.startswith("test_")},
                      f"{symbol} is not reachable under unittest collection")

    def test_prereg_discloses_that_the_sample_was_already_seen(self):
        """The honesty load-bearing in this experiment. A re-preregistered
        re-run that did not say the numbers were known would be worse than
        e031's disclosed amendment -- it would be an undisclosed one."""
        # The PREREG typesets minus with U+2212; normalise so this asserts on
        # the value rather than on which hyphen the author reached for.
        txt = PREREG.read_text(encoding="utf-8").replace("\u2212", "-")
        self.assertIn("The sample has been seen", txt)
        self.assertIn("does not produce new evidence", txt)
        self.assertIn("0.09779", txt)          # rho(move, credit), known
        self.assertIn("-0.65953", txt)         # rho(move, TV1), known
        self.assertIn("-734.78", txt)          # median net, known

    def test_prereg_states_the_no_positive_verdict_constraint(self):
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("No new bar can produce a positive verdict", txt)
        self.assertIn("gate 5 alone", txt)

    def test_the_one_prereg_correction_is_recorded(self):
        """This PREREG was corrected once -- gate 0's pinned-figure count, 30 ->
        36 -- after the engine was written but before any result existed.

        That edit is why this file's mtime postdates mirror_recheck.py, and a
        reader checking freeze order by timestamp would otherwise draw the wrong
        conclusion. Asserting the disclosure is the whole point: s5.2 says a
        correction is recorded in the PREREG, not applied silently, and that
        holds for a benign one exactly as it does for a bar.
        """
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("the one correction made to this file", txt)
        self.assertIn("No bar changed", txt)
        self.assertIn("before the first", txt)
        self.assertIn("postdates `mirror_recheck.py`", txt)
        self.assertIn("mtime test", txt)
        # the gate row now carries the corrected count, not the original one
        self.assertIn("36 at freeze time", gate_row(txt, "0"))
        self.assertNotIn("all 30 pinned figures", txt)

    def test_prereg_forbids_a_fourth_outcome(self):
        """The clause that replaces e031's verdict-string argument."""
        txt = PREREG.read_text(encoding="utf-8")
        self.assertIn("no override clause", txt.lower())
        self.assertIn("void the run and write a successor", txt)


class TestVerdictMapping(unittest.TestCase):
    """The mapping is a pure function so the PREREG's central constraint can be
    tested directly rather than argued for in prose."""

    @staticmethod
    def _gates(g5: bool, g4a: bool = True, g4b: bool = True) -> dict:
        """A gate set: every audit gate passes unless named as failing.

        `g4a`/`g4b` are the PASS state, not a fail flag -- an earlier draft of
        this helper took them the other way round and inverted the constraint
        test, which is a good reminder of why the bars are named constants.
        """
        gates = {k: {"pass": True} for k in AUDIT_KEYS}
        gates["4a_wrong_leg_detector"] = {"pass": g4a}
        gates["4b_time_value_sign"] = {"pass": g4b}
        gates["5_edge_survives_friction"] = {"pass": g5}
        return gates

    def test_audit_pass_and_gate5_fails_is_lead_dead(self):
        self.assertIn("LEAD DEAD", _verdict(self._gates(False)))

    def test_audit_pass_and_gate5_passes_is_eligible(self):
        self.assertIn("ELIGIBLE", _verdict(self._gates(True)))

    def test_any_audit_gate_failing_is_audit_void(self):
        for k in AUDIT_KEYS:
            with self.subTest(gate=k):
                gates = {x: {"pass": x != k} for x in AUDIT_KEYS}
                gates["5_edge_survives_friction"] = {"pass": False}
                v = _verdict(gates)
                self.assertIn("AUDIT VOID", v)
                self.assertIn(k, v)

    def test_a_new_bar_can_never_produce_a_positive_verdict(self):
        """THE CONSTRAINT. 4a and 4b are the NEW, data-informed bars. The PREREG
        admits 4a's threshold was chosen with the result in view and argues that
        this is safe because such a bar may only void, never validate.

        This is that argument, executed across every combination."""
        for g5 in (True, False):
            for a in (True, False):
                for b in (True, False):
                    with self.subTest(g5=g5, a4a_passes=a, a4b_passes=b):
                        v = _verdict(self._gates(g5, g4a=a, g4b=b))
                        if not (a and b):
                            # an audit gate failed: VOID, whatever gate 5 says
                            self.assertIn("AUDIT VOID", v)
                            self.assertNotIn("ELIGIBLE", v)
                        if a and b and not g5:
                            self.assertIn("LEAD DEAD", v)
                        if a and b and g5:
                            self.assertIn("ELIGIBLE", v)

    def test_gate5_is_not_an_audit_gate(self):
        """The structural reason the constraint holds: the only gate that can
        turn DEAD into ELIGIBLE sits outside the audit set."""
        self.assertNotIn("5_edge_survives_friction", AUDIT_KEYS)
        self.assertIn("4a_wrong_leg_detector", AUDIT_KEYS)
        self.assertIn("4b_time_value_sign", AUDIT_KEYS)


class TestResult(unittest.TestCase):
    """Runs the full store once (class-level) and pins the verdict.

    ~5-7 minutes: it re-runs e031's entire 1,415-session walk, because landing
    on the predecessor's number to the decimal is the control (s5.10), not a
    convenience.
    """

    @classmethod
    def setUpClass(cls):
        cls.df, cls.m = run()
        cls.gates = cls.m["gates"]

    def test_control_reproduces_e031_exactly(self):
        """Gate 0. The fresh re-run must equal the recorded artifact, and the
        chain must continue through e031's own control against e030."""
        g = self.gates["0_control_reproduces_predecessor"]
        self.assertTrue(g["pass"], g["drifted"])
        self.assertEqual(g["drifted"], {})
        self.assertTrue(g["chain_e031_vs_e030"])

        # _pinned reads e031's gate names, so the recorded artifact is its
        # input -- this asserts the count against the figures actually pinned
        # in that record, not against e032's own (differently named) gates.
        recorded = json.loads(E031_VERDICT.read_text(encoding="utf-8"))
        self.assertEqual(g["pinned_figures"], len(_pinned(recorded)))
        self.assertEqual(self.m["net_after_friction"], recorded["net_after_friction"])
        self.assertEqual(self.m["pnl_distribution"], recorded["pnl_distribution"])
        self.assertEqual(self.m["credit_vs_residual_time_value"]["median_credit"],
                         recorded["credit_vs_residual_time_value"]["median_credit"])
        self.assertEqual(self.m["net_at_2x_slippage"], recorded["net_at_2x_slippage"])

    def test_contract_identity_holds(self):
        g = self.gates["1_contract_identity"]
        self.assertTrue(g["pass"])
        self.assertEqual(g["front_equals_next"], 0)
        self.assertEqual(g["exit_identity_mismatches"], 0)
        self.assertTrue(g["inherited_exit_path_check_from_e031"])
        self.assertEqual(g["n_resolved"], int((self.df["eligible"] & self.df["ok"]).sum()))

    def test_coverage_is_audited_per_year(self):
        g = self.gates["2_coverage_per_year"]
        self.assertTrue(g["pass"])
        self.assertEqual([r["year"] for r in g["per_year"]],
                         [2021, 2022, 2023, 2024, 2025, 2026])
        for r in g["per_year"]:
            self.assertGreaterEqual(r["coverage_pct"], COVER_BAR,
                                    f"{r['year']} below the frozen bar")
        self.assertGreaterEqual(g["worst_year_coverage_pct"], COVER_BAR)
        self.assertEqual(g["sessions_total"], 1415)

    def test_arithmetic_identity_holds_and_bad_marks_are_counted(self):
        g = self.gates["3_arithmetic_impossibility"]
        self.assertTrue(g["pass"])
        self.assertLess(g["identity_max_error"], TOL)
        self.assertGreaterEqual(g["tv1_min_on_survivors"], -TOL)
        self.assertEqual(g["violations_remaining_in_result"], 0)
        # The 22 stale marks are excluded AND counted -- a check that only
        # inspected survivors would pass whether the exclusion ran or not.
        self.assertGreater(g["raw_mark_flags_before_exclusion"], 0)
        self.assertEqual(g["excluded_mark_still_marked_ok"], 0)

    def test_the_two_new_mechanism_bars(self):
        """4a asks 'did we fetch the right leg?' statistically; 4b asks it as a
        sign imposed by option theory. Neither asks whether the trade is good --
        that is gate 5's question alone."""
        a, b = self.gates["4a_wrong_leg_detector"], self.gates["4b_time_value_sign"]
        self.assertTrue(a["pass"], a)
        self.assertTrue(b["pass"], b)
        self.assertLess(abs(a["spearman_rho"]), WRONG_LEG_BAR)
        self.assertLess(b["spearman_rho"], TV_SIGN_BAR)
        self.assertIn("VOID-ONLY", a["provenance"])
        self.assertIn("no threshold", b["provenance"])

    def test_every_gate_declares_its_provenance(self):
        """No bar may arrive unlabelled: each is CARRIED (frozen before e031's
        full run) or NEW (written with the data in view)."""
        for k, g in self.gates.items():
            with self.subTest(gate=k):
                self.assertIn("provenance", g, f"{k} declares no provenance")
                self.assertTrue(
                    g["provenance"].startswith("CARRIED")
                    or g["provenance"].startswith("NEW"),
                    f"{k} provenance is neither CARRIED nor NEW: {g['provenance']}")
                self.assertIn("bar", g)

    def test_the_expected_verdict_and_no_amendment(self):
        self.assertIn("LEAD DEAD", self.m["verdict"])
        failed = [k for k, g in self.gates.items() if not g["pass"]]
        self.assertEqual(failed, ["5_edge_survives_friction"])
        self.assertEqual(self.m["gates_failed"], 1)
        # The verdict is exactly what the PREREG maps these gates to -- derived,
        # not argued.
        self.assertEqual(self.m["verdict"], _verdict(self.gates))
        s = self.m["prereg_status"]
        self.assertEqual(s["amendments_needed"], 0)
        self.assertFalse(s["override_clause_used"])
        self.assertFalse(s["produces_new_evidence"])
        self.assertTrue(s["sample_already_seen"])

    def test_edge_does_not_survive_friction(self):
        g5 = self.gates["5_edge_survives_friction"]
        self.assertFalse(g5["pass"])
        self.assertLess(g5["median_net"], 0)
        self.assertLess(g5["median_net_2x"], 0)
        cv = self.m["credit_vs_residual_time_value"]
        self.assertGreater(cv["median_tv1"], cv["median_credit"])
        self.assertGreater(cv["median_credit"], 0)
        self.assertLess(self.m["net_after_friction"]["ev_per_trade"], 0)

    def test_artifacts_written(self):
        self.assertTrue((ARTIFACTS / "verdict.json").exists())
        self.assertTrue((ARTIFACTS / "session_pnl.csv").exists())
        self.assertTrue(PREREG.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
