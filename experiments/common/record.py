"""The canonical experiment manifest, derived from disk.

Four places restate which experiments exist and what each concluded:
actionplan.md's void-and-dead ledger (§1.1) and execution schedule (§4), and
RETROSPECTIVE.md's complete record (§6) and status list (§7). Each drifts on
its own clock — §6 claimed to be "every experiment, its honest verdict" while
e030 sat there with a real verdict and no row, and the prose count of
experiments was wrong in both directions.

This module answers "what is actually on disk" in one place, so a check can
compare the documents against it rather than against a number somebody typed.
It is deliberately read-only and derived: nothing here is hand-maintained, so
it cannot drift from the thing it describes.

    python -m experiments.common.record     # print the canonical table

Rung 3 of the reuse ladder: the filesystem already knows the answer.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPERIMENTS = ROOT / "experiments"

DIR_RE = re.compile(r"^e(\d{3})_([a-z0-9_]+)$")

# Every verdict string must begin with one of these, which is what gives an
# experiment a status a document can be checked against. Ordered: more specific
# first. A verdict that matches none is an error, not a silent None — a new
# experiment must say what it concluded, and "somewhere in the prose" is not
# saying it. See tests/test_record.py::test_every_verdict_maps_to_a_status.
STATUS_PREFIXES = (
    ("LEAD DEAD", "DEAD"),
    ("DEAD", "DEAD"),
    ("NO SLICE", "DEAD"),
    ("FAIL", "DEAD"),
    ("DOES NOT SURVIVE", "STRUCK"),
    ("PHASE 7.3 STRUCK", "STRUCK"),
    ("STRUCK", "STRUCK"),
    ("SUPERSEDED", "SUPERSEDED"),
    ("AUDIT VOID", "VOID"),
    ("VOID", "VOID"),
    ("MOOT", "MOOT"),
    ("CLOSED", "CLOSED"),
    ("SUCCESS", "SUCCESS"),
    ("ELIGIBLE", "ELIGIBLE"),
    ("INSTRUMENT", "INSTRUMENT"),
)

STATUSES = frozenset(s for _, s in STATUS_PREFIXES)


def status_of(verdict: str) -> str:
    """The canonical status of a verdict string. Raises rather than guessing."""
    head = verdict.strip().upper()
    for prefix, status in STATUS_PREFIXES:
        if head.startswith(prefix):
            return status
    raise AssertionError(
        f"verdict does not begin with a known status: {verdict!r}\n"
        f"known prefixes: {[p for p, _ in STATUS_PREFIXES]}")


@dataclass(frozen=True)
class Experiment:
    """One experiment directory. Every field is read, never remembered."""

    id: str            # "e030"
    number: int        # 30
    slug: str          # "calendar_credit"
    path: Path
    has_prereg: bool   # PREREG.md exists
    prereg: str        # "frozen", or the declared reason there is no PREREG
    verdict: str       # artifacts/verdict.json's `verdict`

    @property
    def status(self) -> str:
        return status_of(self.verdict)

    @property
    def prereg_status(self) -> str:
        """'frozen' when a PREREG.md exists; else the declared reason.

        There is deliberately no hardcoded list of legacy experiments here.
        Whether an experiment was pre-registered is a fact about that
        experiment, so it is declared by that experiment — in its own
        verdict.json — and never remembered centrally.
        """
        return "frozen" if self.has_prereg else self.prereg


def experiments() -> list[Experiment]:
    """Every `experiments/eNNN_slug/` on disk, in id order."""
    out: list[Experiment] = []
    for p in sorted(EXPERIMENTS.iterdir()):
        if not p.is_dir():
            continue
        m = DIR_RE.match(p.name)
        if not m:
            continue
        number, slug = int(m.group(1)), m.group(2)
        verdict_file = p / "artifacts" / "verdict.json"
        if not verdict_file.exists():
            raise AssertionError(
                f"{p.name} has no artifacts/verdict.json — every experiment "
                "must record what it concluded, even if the answer is 'it "
                "pre-dates this file'; see tests/test_record.py")
        try:
            doc = json.loads(verdict_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{verdict_file} is not valid JSON: {exc}") from exc

        # The artifact must name itself. A copy-pasted verdict under the
        # wrong directory is a silent false claim about what ran.
        claimed = doc.get("experiment")
        if claimed != p.name:
            raise AssertionError(
                f"{verdict_file} claims experiment {claimed!r} but lives in "
                f"{p.name!r}")

        verdict = doc.get("verdict")
        if not verdict:
            raise AssertionError(f"{verdict_file} has no `verdict` string")
        prereg = doc.get("prereg")
        if not prereg:
            raise AssertionError(
                f"{verdict_file} has no `prereg` declaration; it must say "
                "'frozen' or why the experiment was not pre-registered")

        out.append(Experiment(
            id=f"e{number:03d}", number=number, slug=slug, path=p,
            has_prereg=(p / "PREREG.md").exists(),
            prereg=prereg, verdict=verdict))
    out.sort(key=lambda e: e.number)
    return out


def ids() -> set[str]:
    return {e.id for e in experiments()}


def table() -> str:
    """The canonical markdown table. Machine-derived; never hand-edit a copy."""
    rows = ["| # | Slug | Status | PREREG | Verdict |",
            "|---|---|---|---|---|"]
    for e in experiments():
        v = e.verdict.replace("|", "\\|")
        rows.append(f"| {e.id} | {e.slug} | {e.status} | {e.prereg_status} | {v} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())
