"""Struck figures — the numbers that were killed, and where they must say so.

Four convictions voided this repo's best results, and the strike markers ended
up in the ledger while the *numbers* stayed everywhere else: +₹9,40,697 is the
headline of `production_handoff.md` §2–§3, +₹7,43,572 is e011's own README
result block, +₹4,14,721 is a table row in five experiment READMEs. A reader
who opens a README — or worse, the handoff — finds a dead number presented as a
result, which is the same failure the ledger already corrected in one place.

This is `record.py` one level down: the experiment table says *which
experiments* are void; this says *which figures* are, and refuses to let a
document quote one without saying so. Read-only, derived, and deliberately
boring — a grep with a written-down contract, which is what the four convictions
keep asking for.

    python -m experiments.common.struck        # the registry + any bare quotes

**What counts as "saying so."** The repo already has two conventions and this
module only names them, rather than inventing a third:

  * `~~struck~~` on the line — actionplan §1.1's own ledger rows;
  * a status banner in the first few lines that *names the figure* — what
    `production_handoff.md` and actionplan's restatement block do;
  * a strike word on the line or its immediate neighbour ("VOID", "struck",
    "look-ahead artifact", "collapsed to") — the prose form, used throughout
    RETROSPECTIVE §2.

**Scope: `PREREG.md` is exempt, deliberately.** A pre-registration is frozen at
a point in time (invariant §5.16), and the conviction that struck its input
arrived *after* it was written — editing a frozen PREREG to add a strike marker
is the thing §5.16 forbids ("if a PREREG needs an amendment after the run, void
it and write a successor"). Its successor's ledger carries the strike. The
exemption is asserted in tests/test_struck.py so it cannot widen silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Words that mean "this number is dead" when they sit on or beside the figure.
MARKERS: tuple[str, ...] = (
    "struck", "void", "voided", "superseded", "dead", "moot", "invalid",
    "falsified", "not tradeable", "not achievable", "not yet achievable",
    "look-ahead", "lookahead", "artifact", "collapsed", "no longer",
    "expired", "historical", "must not", "not live", "back to research",
)

#: How many lines from the top count as a document's status banner.
BANNER_LINES = 6

#: Files whose whole job is to record what was believed at a frozen moment.
EXEMPT_NAMES: frozenset[str] = frozenset({"PREREG.md"})

_SKIP_PARTS = frozenset({".venv", ".git", "__pycache__", "node_modules", "data"})


@dataclass(frozen=True)
class Struck:
    """One killed claim, and every way it is spelled in prose.

    `figures` holds the alternate spellings because documents write the same
    rupee figure as `+₹7,43,572`, `+7,43,572.25` and (in the ledger) `+₹9.41L`.
    A lookbehind stops `6.4L` matching inside `16.4L`.
    """

    claim: str       # what was claimed, in the words the documents use
    voided_by: str   # which experiment killed it (checked against record.py)
    verdict: str     # what replaced it, in one clause
    figures: tuple[str, ...]

    def pattern(self) -> re.Pattern:
        return re.compile(r"(?<![\d,.])(?:" + "|".join(
            re.escape(f) for f in self.figures) + r")")


#: Every figure this repo has convicted, in conviction order. Adding a row here
#: is the act of striking a number: the next test run says which documents have
#: to say so.
REGISTRY: tuple[Struck, ...] = (
    Struck(
        claim="e005/e006 breach-only book — +₹9,40,697 over 249 trades",
        voided_by="e001 (t-1 audit) and e007 (gate 0, opening-OI walls)",
        verdict="VOID — the wall signal was day-t EOD OI; gate 0 gave 4 trades, −₹309",
        figures=("9,40,697", "940,697", "9.41L"),
    ),
    Struck(
        claim="e005 4-leg condor variant on the same breach days — +₹9,87,124",
        voided_by="e001 (t-1 audit) and e007 (gate 0, opening-OI walls)",
        verdict="VOID — same day-t wall convention; PF 62.6 on 98.8% WR was the tell",
        figures=("9,87,124", "987,124"),
    ),
    Struck(
        claim="e011 true-VRP delta-hedged straddle — +₹7,43,572, Sharpe 2.85, PF 3.99",
        voided_by="e018 (contract identity)",
        verdict="VOID — 0; priced t's contract with t−1's expiry; e015/e016/e017 inherit it",
        figures=("7,43,572", "7,43,572.25"),
    ),
    Struck(
        claim="e013 expiry pin harvest — +₹4,14,721, PF 9.41, DD 5.97%",
        voided_by="e026 (marks were a model), then e028 (the sample never loaded)",
        verdict="DEAD — +₹45,568 at 0.75 pts/leg, −₹29,082 at 2.0, n=129",
        figures=("4,14,721", "4.14L"),
    ),
    Struck(
        claim="e026 real-price restatement of e013 — +₹61,843 on 64 sessions",
        voided_by="e028 (expiry-encoding defect: 356 of 576 sessions returned empty)",
        verdict="SUPERSEDED — the 64 sessions were format-selected; corrected n=129",
        figures=("61,843", "61,842.51"),
    ),
    Struck(
        claim="e015 combined book E011 × E013 — +₹11,58,293, Sharpe 4.14",
        voided_by="e018 (one leg void voids the book)",
        verdict="VOID — 0; only the 10-overlap-day margin breach survives, as a capital fact",
        figures=("11,58,293",),
    ),
    Struck(
        claim="e016 iron-fly wings on e011's signal — −₹1,56,941, DD 101.5%",
        voided_by="e018 (inherits the contract-identity defect)",
        verdict="VOID — 0; the wings finding is untested on a correct contract",
        figures=("1,56,941",),
    ),
    Struck(
        claim="e017 risk budget — \"needs ₹6.4L\"",
        voided_by="e018 (computed on the void book)",
        verdict="VOID — a statement about a bug",
        figures=("6.4L",),
    ),
)


def documents() -> list[Path]:
    """Every markdown document in the repo, minus frozen PREREGs."""
    out = []
    for p in sorted(ROOT.rglob("*.md")):
        if _SKIP_PARTS & set(p.parts):
            continue
        if p.name in EXEMPT_NAMES:
            continue
        out.append(p)
    return out


def _banner_names(struck: Struck, banner_lines: list[str]) -> bool:
    """Does the document's status banner declare *this* figure dead?

    Both halves are required. A line that merely contains the figure is not a
    declaration — otherwise any document shorter than the window would exempt
    its own first figure, which is the loophole a scratch file found on the day
    this rule was written.
    """
    pat = struck.pattern()
    return any(pat.search(line) and any(m in line.lower() for m in MARKERS)
               for line in banner_lines)


def _marked(struck: Struck, lines: list[str], i: int) -> bool:
    """Is the figure on line `i` already declared dead?"""
    if "~~" in lines[i]:
        return True
    if any(m in lines[i].lower() for m in MARKERS):
        return True
    # A neighbouring line carries the marker: markdown table rows and prose
    # sentences both put the verdict in the cell or clause beside the figure.
    for j in (i - 1, i + 1):
        if 0 <= j < len(lines) and any(m in lines[j].lower() for m in MARKERS):
            return True
    # A banner exemption applies only to the figures the banner actually names
    # *and* condemns, so a new dead number cannot ride in on an old status line.
    return _banner_names(struck, lines[:BANNER_LINES])


def bare_quotes() -> list[str]:
    """`path:line` for every struck figure quoted without a strike marker."""
    found: list[str] = []
    for p in documents():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - repo is utf-8
            continue
        lines = text.split("\n")
        rel = p.relative_to(ROOT).as_posix()
        for struck in REGISTRY:
            pat = struck.pattern()
            for i, line in enumerate(lines):
                hit = pat.search(line)
                if hit and not _marked(struck, lines, i):
                    found.append(f"{rel}:{i + 1}  {hit.group(0)}  —  "
                                 f"{line.strip()[:90]}")
    return found


def table() -> str:
    """The canonical quarantine table. Machine-derived; never hand-edit a copy."""
    rows = ["| Claim | Struck by | Verdict | Spellings watched |", "|---|---|---|---|"]
    for s in REGISTRY:
        rows.append(f"| {s.claim} | {s.voided_by} | {s.verdict} | "
                    f"{', '.join(f'`{f}`' for f in s.figures)} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())
    bare = bare_quotes()
    print()
    if not bare:
        print(f"No bare quotes. Every struck figure in {len(documents())} documents "
              "says it is struck.")
    else:
        print(f"{len(bare)} bare quote(s) — a struck figure a reader could take as live:\n")
        for b in bare:
            print("  " + b)
    raise SystemExit(1 if bare else 0)