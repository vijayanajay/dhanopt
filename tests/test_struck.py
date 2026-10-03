"""A struck figure may not be quoted as a live result, in any document.

The Void & Dead ledger struck the repo's best numbers in one place and left
them standing everywhere else. `production_handoff.md` — the one file a reader
opens to decide whether to trade — carried +₹9,40,697 as its §2 headline and
still described gate 0 as something that "must" be run, three weeks after gate 0
failed and two convictions after the successor book was killed. e011's own README
still presented +₹7,43,572 as a result.

`experiments.common.struck` is the registry and the scan; this file is what makes
it load-bearing. Invariant §5.16's own test: *what would this number be if my
hypothesis were false?* Same question here — *if this registry were empty, what
would the documents say?* They would say a dead number is a result, which is
why the registry's integrity is asserted rather than assumed.

Failures this catches:

  * a document quoting a struck figure bare — the four convictions' actual
    failure mode, spread over ~13 markdown files before this check existed;
  * a registry entry pointing at a conviction that does not exist on disk;
  * the scan quietly vacuous (a detector that matches nothing passes), and the
    banner exemption leaking to figures the banner does not name;
  * the handoff re-acquiring a pending validation whose gate already resolved.

**Scope: `PREREG.md` is exempt, deliberately.** A pre-registration is frozen
before its run (invariant §5.16) and the conviction that struck its input arrived
afterwards; editing a frozen PREREG to add a strike marker is what §5.16 forbids.
Its successor's ledger carries the strike. Asserted below so it cannot widen.
"""
from __future__ import annotations

import unittest

from experiments.common.record import ids
from experiments.common.struck import (
    BANNER_LINES,
    EXEMPT_NAMES,
    REGISTRY,
    Struck,
    _marked,
    bare_quotes,
    documents,
)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "production_handoff.md"

_EXP_RE = __import__("re").compile(r"\be(\d{3})\b")


def entry_for(figure: str) -> Struck:
    for s in REGISTRY:
        if figure in s.figures:
            return s
    raise AssertionError(f"{figure} is not in the registry")  # pragma: no cover


class TestTheRegistryIsHonest(unittest.TestCase):
    def test_every_entry_names_a_conviction_that_exists(self):
        """A quarantine pointing at a conviction nobody can read is decoration."""
        on_disk = ids()
        self.assertTrue(on_disk, "the record found nothing — this test is broken")
        for s in REGISTRY:
            self.assertTrue(s.claim, s)
            self.assertTrue(s.verdict, s)
            self.assertTrue(s.figures, s)
            named = _EXP_RE.findall(s.voided_by)
            self.assertTrue(named, f"{s.claim}: names no experiment")
            for n in named:
                self.assertIn(f"e{n}", on_disk, f"{s.claim} -> e{n} does not exist")

    def test_no_figure_is_registered_twice(self):
        """Two entries watching one figure means two verdicts for one number."""
        seen: dict[str, str] = {}
        for s in REGISTRY:
            for f in s.figures:
                self.assertNotIn(f, seen, f"{f} claimed by both {seen.get(f)} and {s.claim}")
                seen[f] = s.claim

    def test_the_scan_covers_the_repo_not_a_handful_of_files(self):
        """A registry that matches three documents is not a quarantine."""
        docs = documents()
        self.assertGreater(len(docs), 20, f"only {len(docs)} documents scanned")
        self.assertIn(ROOT / "production_handoff.md", docs)
        self.assertIn(ROOT / "experiments" / "e011_vrp_delta_hedge" / "README.md", docs)


class TestTheScannerDetectsWhatItClaims(unittest.TestCase):
    """A guard that cannot fail is not a guard.

    Every assertion below is a claim about the *detector*, written before any
    document was edited — otherwise "no bare quotes" could mean the scan matches
    nothing at all, which is exactly the bug this file's sibling caught on its
    first run (a banner regex built from a string's characters).
    """

    def test_a_bare_quote_is_bare(self):
        breach = entry_for("940,697")
        self.assertFalse(_marked(breach, ["| Net | +₹940,697 |"], 0))
        self.assertFalse(_marked(breach, ["so the book made +₹940,697"], 0))

    def test_a_strikethrough_marks_it(self):
        breach = entry_for("940,697")
        self.assertTrue(_marked(breach, ["| Net | ~~+₹940,697~~ |"], 0))

    def test_a_marker_on_the_line_or_beside_it_marks_it(self):
        breach = entry_for("940,697")
        self.assertTrue(_marked(breach, ["| VOID | +₹940,697 |"], 0))
        self.assertTrue(_marked(breach, ["| Net | +₹940,697 |", "VOID"], 0))
        self.assertTrue(_marked(breach, ["**STRUCK**", "The book made +₹940,697."], 1))

    def test_a_banner_covers_only_the_figures_it_names(self):
        """The loophole a blank `any(...)` opens: one dead figure's status line
        must not silently excuse a different dead figure in the same file."""
        condor = entry_for("987,124")          # a different entry from 940,697
        other = ["> ⚠ STRUCK: the +940,697 breach book is dead.",
                 "", "| Net | +₹9,87,124 |"]
        self.assertFalse(_marked(condor, other, 2))
        named = ["> ⚠ STRUCK: +987,124 is dead.", "", "| Net | +₹9,87,124 |"]
        self.assertTrue(_marked(condor, named, 2))

    def test_a_short_document_does_not_exempt_its_own_first_figure(self):
        """The loophole a scratch file found: in a file shorter than the window,
        the figure's own line *is* the banner, and must not count as a
        declaration."""
        breach = entry_for("940,697")
        short = ["# Note", "", "The book made +₹940,697 and it is great."]
        self.assertFalse(_marked(breach, short, 2))

    def test_the_banner_window_is_bounded(self):
        """A status line far below the top is not a banner."""
        breach = entry_for("940,697")
        late = [""] * BANNER_LINES + ["> ⚠ +940,697 is struck.", "", "| Net | +₹940,697 |"]
        self.assertFalse(_marked(breach, late, len(late) - 1))
        early = ["> ⚠ +940,697 is struck."] + [""] * BANNER_LINES + ["| Net | +₹940,697 |"]
        self.assertTrue(_marked(breach, early, len(early) - 1))

    def test_every_entry_matches_each_of_its_own_spellings(self):
        for s in REGISTRY:
            pat = s.pattern()
            for f in s.figures:
                self.assertTrue(pat.search(f"total was +₹{f} net"),
                                f"{s.claim} does not match its own spelling {f}")


class TestNoDocumentQuotesAStruckFigureAsLive(unittest.TestCase):
    def test_no_bare_quotes_anywhere(self):
        bare = bare_quotes()
        self.assertEqual(
            bare, [],
            "a struck figure a reader could take for a live result:\n  "
            + "\n  ".join(bare))

    def test_frozen_preregs_are_the_only_exemption(self):
        """Asserted so the exemption cannot widen to the documents it protects."""
        self.assertEqual(EXEMPT_NAMES, frozenset({"PREREG.md"}))
        txt = (ROOT / "tests" / "test_struck.py").read_text(encoding="utf-8")
        self.assertIn("`PREREG.md` is exempt", txt)
        scanned = {p.name for p in documents()}
        self.assertNotIn("PREREG.md", scanned)

    def test_a_prereg_is_actually_exempt_from_the_scan(self):
        """Otherwise the exemption above is a claim with no behaviour behind it."""
        prereg = ROOT / "experiments" / "e026_realmark_audit" / "PREREG.md"
        self.assertTrue(prereg.exists())
        self.assertNotIn(prereg, documents())


class TestTheHandoffResolvesWhatItDeclaredPending(unittest.TestCase):
    """The specific stale condition found by this quarantine.

    `production_handoff.md` told the reader to wait for gate 0 before believing
    +₹9,40,697, three weeks after gate 0 failed, and offered the intraday
    wall-flip as "the only surviving lead" two experiments before e008 killed it
    on observability. A pending condition whose gate resolved is worse than no
    condition: it reads as work still to do.
    """

    def setUp(self):
        self.txt = HANDOFF.read_text(encoding="utf-8")

    def test_no_stale_pending_wall_source_bullet(self):
        self.assertNotIn("can be treated as achievable", self.txt)
        self.assertIn("resolved, not pending", self.txt)

    def test_the_paper_gate_is_marked_expired_not_pending(self):
        self.assertIn("EXPIRED 2026-10-01", self.txt)
        self.assertNotIn("2. **Paper-trade the gate (instrumented).** `paper_trade.py`", self.txt)

    def test_the_capital_plan_is_marked_void(self):
        self.assertIn("⚠ VOID — do not scale.", self.txt)

    def test_the_surviving_lead_is_closed_with_its_verdict(self):
        self.assertNotIn("(the only surviving lead)", self.txt)
        self.assertIn("DEAD on observability", self.txt)

    def test_the_handoff_names_every_dead_figure_it_carries(self):
        for fig in ("940,697", "987,124", "4,14,721", "7,43,572"):
            self.assertIn(fig, self.txt.split("\n\n")[0] + "\n" +
                          "\n".join(self.txt.split("\n")[:12]),
                          f"the handoff's banner does not name {fig}")


if __name__ == "__main__":
    unittest.main(verbosity=2)