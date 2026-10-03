"""The record must cover every experiment on disk — and agree with it.

RETROSPECTIVE.md §6 claims to be "the complete record — every experiment, its
honest verdict". It drifted: e030 had a real, verified verdict and no row, the
prose count of experiments was wrong in both directions, and 17 experiments had
no machine-readable verdict at all.

Invariant §5.13 says a data claim is a testable assertion. This applies that to
the record itself, comparing the documents against `experiments.common.record`
— the manifest derived from disk — rather than against a number somebody typed.

Failures this catches:

  * an experiment that ran but has no verdict row — the e030 gap;
  * a row for an experiment that does not exist — e021–e025 are roadmap ids
    that never started, and five empty rows would imply they did;
  * a prose count that no longer matches disk;
  * an experiment with no verdict at all, or one that does not say what it
    concluded in a form a machine can read;
  * a document status cell that contradicts the experiment's own verdict —
    e.g. a run that concluded AUDIT VOID being recorded as a result.

**Scope: RETROSPECTIVE §6 only, deliberately.** actionplan §1.1 is not checked
mechanically, because its Status column answers a *different question*. It is
the Void & Dead Ledger: "VOID" there means the claimed number may not be
quoted. §6's status disposes of the *idea*. e001 is VOID in §1.1 (the +₹9.41L
was built on a leak) and DEAD in §6 (wall-free legs lose, so the hypothesis
dies) — both correct, and a check that demanded agreement would be wrong. This
scope decision is asserted below so it cannot be widened by accident.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from experiments.common.record import experiments, ids, status_of

_STATUSES = frozenset({
    "DEAD", "STRUCK", "SUPERSEDED", "VOID", "MOOT",
    "CLOSED", "SUCCESS", "ELIGIBLE", "INSTRUMENT",
})

ROOT = Path(__file__).resolve().parents[1]
RETROSPECTIVE = ROOT / "RETROSPECTIVE.md"
ACTIONPLAN = ROOT / "actionplan.md"
TEMPLATE = ROOT / "experiments" / "PRE_REGISTRATION_TEMPLATE.md"

ROW_RE = re.compile(r"^\| \*{0,2}(e\d{3})\*{0,2} \|", re.M)
COUNT_RE = re.compile(r"(\d+) of them at this writing")


def section6_rows() -> dict[str, str]:
    """id -> the row's Status cell (last column) in RETROSPECTIVE §6."""
    txt = RETROSPECTIVE.read_text(encoding="utf-8")
    try:
        section = txt.split("## 6. The complete record", 1)[1].split("## 7.", 1)[0]
    except IndexError as exc:  # pragma: no cover - structural break, not drift
        raise AssertionError("RETROSPECTIVE.md has no §6 or §7 heading") from exc
    out: dict[str, str] = {}
    for line in section.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        out[m.group(1)] = cells[-1]
    return out


def recorded_ids() -> set[str]:
    return set(section6_rows())


class TestRecordCoversEveryExperiment(unittest.TestCase):
    def test_every_experiment_directory_has_a_verdict_row(self):
        """The e030 gap, as a failing check rather than an omission."""
        on_disk = ids()
        self.assertTrue(
            on_disk,
            "the manifest found nothing — the scan is broken, not the record")
        missing = sorted(on_disk - recorded_ids())
        self.assertEqual(
            missing, [],
            f"experiments on disk with no §6 verdict row: {missing} — "
            "add a row or state why it has none")

    def test_no_verdict_row_for_an_experiment_that_does_not_exist(self):
        """Guards the opposite error: inventing rows for tests never run."""
        recorded = recorded_ids()
        self.assertTrue(
            recorded,
            "§6 yielded no verdict rows — the section parse is broken, not the record")
        ghosts = sorted(recorded - ids())
        self.assertEqual(
            ghosts, [],
            f"§6 rows with no experiments/ directory: {ghosts} — "
            "a row implies the experiment ran")

    def test_the_stated_count_matches_the_directory_set(self):
        """The prose number is a claim about disk; pin it to disk."""
        txt = RETROSPECTIVE.read_text(encoding="utf-8")
        m = COUNT_RE.search(txt)
        self.assertIsNotNone(
            m, "§6 no longer states 'N of them at this writing'; "
               "either restore the checkable form or update this test")
        self.assertEqual(int(m.group(1)), len(ids()))

    def test_the_struck_count_is_gone(self):
        """'Twenty-eight' was asserted in two places and was wrong."""
        self.assertNotIn("twenty-eight experiments",
                         RETROSPECTIVE.read_text(encoding="utf-8"))


class TestStatusAgreesWithTheRecord(unittest.TestCase):
    """The handwritten Status column must say what the experiment concluded.

    Both sides reduce through record.status_of, so a doc cell that restates the
    same disposition in different words still passes — but a row that calls an
    AUDIT VOID run a result does not.
    """

    def test_every_section6_status_cell_matches_its_verdict(self):
        rows = section6_rows()
        self.assertTrue(rows)
        mismatches = []
        for e in experiments():
            cell = rows.get(e.id)
            if cell is None:
                continue  # covered by the row-existence test
            shown = cell.replace("*", "").strip()
            if not shown.upper().startswith(e.status):
                mismatches.append(f"{e.id}: §6 says {shown!r}, "
                                  f"verdict implies {e.status}")
        self.assertEqual(mismatches, [], "\n".join(mismatches))

    def test_actionplan_ledger_is_deliberately_not_checked(self):
        """§1.1 answers a different question (is the *claim* quotable), so its
        Status column may legitimately differ from §6's. Recorded here so the
        scope cannot silently widen — or silently narrow."""
        txt = (ROOT / "tests" / "test_record.py").read_text(encoding="utf-8")
        self.assertIn("actionplan §1.1 is not checked", txt)
        self.assertIn("§6 only, deliberately", txt)
        self.assertTrue(ACTIONPLAN.exists())


class TestEveryExperimentIsPreRegistered(unittest.TestCase):
    """An ID exists only once its PREREG is frozen — and history is declared,
    not suppressed.

    e021–e025 were reserved on the roadmap for tests that could not start and
    now read as if they ran. e001–e008 and e015 predate the convention and can
    never be pre-registered, so the honest record is a *declaration* by each of
    them, not a list held in this file.
    """

    def test_every_experiment_declares_its_preregistration_status(self):
        unregistered = []
        for e in experiments():
            if e.has_prereg:
                self.assertEqual(e.prereg_status, "frozen", e.id)
            else:
                unregistered.append(e.id)
                self.assertNotEqual(
                    e.prereg_status, "frozen",
                    f"{e.id} has no PREREG.md yet declares itself pre-registered")
                self.assertRegex(
                    e.prereg_status, r"predate",
                    f"{e.id} has no PREREG.md and does not explain why: "
                    f"{e.prereg_status!r}")
        # The unregistered set is allowed to be non-empty — it is history — but
        # it must be small, declared, and shrinkable. Asserting a bound rather
        # than an exact list means a NEW experiment without a PREREG trips it
        # without anyone editing this file.
        self.assertLessEqual(
            len(unregistered), 9,
            f"unregistered experiments grew to {unregistered}; a new experiment "
            "must carry a PREREG")

    def test_the_template_says_an_id_is_assigned_when_the_prereg_is_frozen(self):
        """Stop reserving numbers. The convention is what makes the invariant
        above fair to whoever starts the next experiment."""
        txt = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("An ID is assigned when this file is frozen", txt)
        self.assertIn("Reserve nothing", txt)


class TestManifestIsSelfConsistent(unittest.TestCase):
    def test_every_experiment_is_well_formed(self):
        found = experiments()
        self.assertTrue(found)
        for e in found:  # pragma: no branch - every iteration asserts
            self.assertRegex(e.id, r"^e\d{3}$")
            self.assertRegex(e.slug, r"^[a-z0-9_]+$")
            self.assertTrue(e.path.is_dir(), e.path)
            self.assertEqual(e.id, f"e{e.number:03d}")

    def test_every_verdict_names_its_own_experiment(self):
        """A copy-pasted verdict under the wrong directory is a silent false
        claim about what ran. record.experiments() raises on this."""
        for e in experiments():
            self.assertTrue(e.verdict, f"{e.id} has an empty verdict")

    def test_every_verdict_maps_to_a_status(self):
        """A verdict that does not begin with a known status is an error, not a
        silent None — a new experiment must say what it concluded."""
        seen = {e.status for e in experiments()}
        self.assertTrue(seen)
        self.assertTrue(seen <= _STATUSES, seen)

    def test_an_unmapped_verdict_is_an_error_not_a_guess(self):
        """A verdict that says nothing a machine can read must fail loudly."""
        with self.assertRaises(AssertionError):
            status_of("it went fine, mostly")
        self.assertEqual(status_of("LEAD DEAD — the credit is eaten"), "DEAD")
        self.assertEqual(status_of("AUDIT VOID — control failed"), "VOID")

    def test_the_status_vocabulary_is_small_and_explicit(self):
        self.assertLessEqual(len(_STATUSES), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
