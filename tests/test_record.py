"""The record must cover every experiment on disk — and nothing else.

RETROSPECTIVE.md §6 claims to be "the complete record — every experiment, its
honest verdict". It drifted: e030 had a real, verified verdict and no row, and
the prose count of experiments was wrong in both directions.

Invariant §5.13 says a data claim is a testable assertion. This applies that to
the record itself, comparing the documents against `experiments.common.record`
— the manifest derived from disk — rather than against a number somebody typed.

Failures this catches:

  * an experiment that ran and produced artifacts but has no verdict row —
    the e030 gap, invisible until someone reads the table against `ls`;
  * a row for an experiment that does not exist — e021–e025 are Phase 7
    roadmap ids that never started, and five empty rows would imply they did;
  * an experiment directory with no PREREG — the e021–e025 problem in reverse,
    a reserved number that has begun to look like work;
  * a prose count that no longer matches disk.

Cheap by construction: no data store, no fixtures, no network. It reads one
markdown file and one directory listing.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from experiments.common.record import Experiment, experiments, ids

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
RETROSPECTIVE = ROOT / "RETROSPECTIVE.md"
TEMPLATE = EXPERIMENTS / "PRE_REGISTRATION_TEMPLATE.md"

ROW_RE = re.compile(r"^\| \*{0,2}(e\d{3})\*{0,2} \|", re.M)
COUNT_RE = re.compile(r"(\d+) of them at this writing")

# Experiments that predate the PREREG convention. Named rather than suppressed:
# the set is a reconciliation, so it fails in BOTH directions — a new experiment
# without a PREREG fails, and adding a PREREG to one of these fails until the
# set is shrunk. e001-e008 and e015 were written before pre-registration was a
# rule here; every experiment from e009 on carries one.
LEGACY_NO_PREREG = frozenset({
    "e001", "e002", "e003", "e004", "e005", "e006", "e007", "e008", "e015",
})


def recorded_ids() -> set[str]:
    """Ids with a row in §6's table — the section's prose is excluded."""
    txt = RETROSPECTIVE.read_text(encoding="utf-8")
    try:
        section = txt.split("## 6. The complete record", 1)[1].split("## 7.", 1)[0]
    except IndexError as exc:  # pragma: no cover - structural break, not drift
        raise AssertionError("RETROSPECTIVE.md has no §6 or §7 heading") from exc
    return set(ROW_RE.findall(section))


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
        stated = int(m.group(1))
        actual = len(ids())
        self.assertEqual(
            stated, actual,
            f"§6 says {stated} experiments, disk has {actual}")

    def test_the_struck_count_is_gone(self):
        """'Twenty-eight' was asserted in two places and was wrong."""
        txt = RETROSPECTIVE.read_text(encoding="utf-8")
        self.assertNotIn("twenty-eight experiments", txt)


class TestEveryExperimentIsPreRegistered(unittest.TestCase):
    """§5.16's upstream rule: an ID exists only once its PREREG is frozen.

    e021–e025 were reserved on the roadmap for tests that could not start and
    now read as if they ran. The fix is not to delete those rows but to make a
    directory without a PREREG impossible to leave behind.
    """

    def test_the_legacy_set_is_exactly_the_unregistered_set(self):
        unregistered = {e.id for e in experiments() if not e.has_prereg}
        self.assertEqual(
            unregistered, set(LEGACY_NO_PREREG),
            "reconcile: a NEW experiment without a PREREG must be added here "
            "deliberately (don't), or given a PREREG; a legacy one that gained "
            "a PREREG should be removed from LEGACY_NO_PREREG")

    def test_the_legacy_set_is_documented_as_a_set_not_a_gap(self):
        """It must be visible that these are historical, not missing."""
        txt = (ROOT / "tests" / "test_record.py").read_text(encoding="utf-8")
        self.assertIn("predate the PREREG convention", txt)

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

    def test_a_verdict_artifact_names_its_own_experiment(self):
        """A copy-pasted verdict under the wrong directory is a silent false
        claim about what ran. record.experiments() raises on this; assert at
        least one verdict exists so the check is exercised rather than idle."""
        with_verdict = [e for e in experiments() if e.has_verdict]
        self.assertTrue(
            with_verdict,
            "no experiment has artifacts/verdict.json — the self-naming check "
            "would be unexercised")
        for e in with_verdict:
            self.assertTrue(e.verdict, f"{e.id} has a verdict.json with no verdict")


if __name__ == "__main__":
    unittest.main(verbosity=2)
