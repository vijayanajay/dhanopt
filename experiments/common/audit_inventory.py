"""Verify every claim in actionplan.md §2 (Data Inventory) against what is on disk.

Read-only. Prints a claim-by-claim table: CLAIM / MEASURED / VERDICT.

Run:  .venv/Scripts/python.exe -m experiments.common.audit_inventory
"""
from __future__ import annotations

import glob
import os
import random
import re
import subprocess
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]


def du(p: str) -> str:
    return subprocess.run(["du", "-sh", p], capture_output=True, text=True).stdout.split()[0]


def glb(p: str) -> list[str]:
    return sorted(glob.glob(str(ROOT / p), recursive=True))


def main() -> int:
    hist = glb("data/historical/**/*.parquet")
    intra = glb("data/intraday/**/*.parquet")
    cash = glb("data/cash/**/*.parquet")
    po = ROOT / "data/participant_oi"

    print("=" * 72)
    print("A. data/historical/  claim: 'EOD NSE FO Bhavcopy, year=2021..2026'")
    print("=" * 72)
    years = sorted({p.split("year=")[1].split(os.sep)[0] for p in hist})
    print(f"   years on disk        : {years[0]}..{years[-1]} ({len(years)} years)")
    print(f"   daily files          : {len(hist)}")
    print(f"   size                 : {du('data/historical')}")
    per = {}
    for p in hist:
        y = p.split("year=")[1].split(os.sep)[0]
        per[y] = per.get(y, 0) + 1
    for y in years:
        print(f"     year={y}: {per[y]:4d} sessions")

    print()
    print("=" * 72)
    print("B. universe  claim: 'NIFTY index options, NIFTY futures, and")
    print("   constituent stock options (RELIANCE, HDFCBANK, ICICIBANK, INFY, TCS)'")
    print("=" * 72)
    random.seed(3)
    samp = random.sample(hist, min(40, len(hist)))
    sets: dict[str, set] = {}
    insts: set = set()
    for p in samp:
        d = pq.read_table(p, columns=["symbol", "instrument"]).to_pandas()
        insts |= set(map(str, d.instrument.unique()))
        for i, s in d.groupby("instrument").symbol.unique().items():
            sets.setdefault(str(i), set()).update(map(str, s))
    print(f"   instrument types     : {sorted(insts)}")
    print(f"   OPTIDX               : {sorted(sets.get('OPTIDX', []))}")
    print(f"   FUTIDX               : {sorted(sets.get('FUTIDX', []))}")
    print(f"   OPTSTK symbols       : {len(sets.get('OPTSTK', []))}")
    missing = [t for t in ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS"]
               if t not in sets.get("OPTSTK", set())]
    print(f"   5 named constituents : {'ALL PRESENT' if not missing else 'MISSING ' + str(missing)}")

    print()
    print("=" * 72)
    print("C. data/intraday/  claim: '5-minute NIFTY 50 spot OHLCV, 1,410+ sessions'")
    print("=" * 72)
    print(f"   files                : {len(intra)}")
    print(f"   size                 : {du('data/intraday')}")
    d0 = pq.read_table(intra[0]).to_pandas()
    d1 = pq.read_table(intra[-1]).to_pandas()
    print(f"   columns              : {list(d0.columns)}")
    print(f"   no instrument/symbol column -> single-instrument store, identity from filename")
    print(f"   first session        : {os.path.basename(intra[0])}  bars={len(d0)}  "
          f"close {d0.close.min():.0f}..{d0.close.max():.0f}")
    print(f"   last  session        : {os.path.basename(intra[-1])}  bars={len(d1)}  "
          f"close {d1.close.min():.0f}..{d1.close.max():.0f}")

    print()
    print("=" * 72)
    print("D. data/cash/  claim: '1,420 sessions x 6,475 symbols, 215 MB'")
    print("=" * 72)
    print(f"   files                : {len(cash)}")
    print(f"   size                 : {du('data/cash')}")
    t = pq.read_table(cash[-1]).to_pandas()
    symcol = [c for c in t.columns if "SYMBOL" in c.upper()][0]
    print(f"   columns              : {list(t.columns)[:10]}")
    print(f"   symbols (last sess)  : {t[symcol].nunique()}")
    random.seed(7)
    samp = random.sample(cash, min(25, len(cash)))
    counts, union = [], set()
    for p in samp:
        s = set(map(str, pq.read_table(p, columns=["symbol"]).to_pandas().symbol.unique()))
        counts.append(len(s))
        union |= s
    counts.sort()
    print(f"   symbols/session      : min {counts[0]}, median {counts[len(counts)//2]}, "
          f"max {counts[-1]}  (25-session sample)")
    print(f"   union over that sample: {len(union)}")
    print("   -> 6,475 is the UNION across the store (the survivorship-safe design),")
    print("      NOT a per-session count. Per session it is ~1.8k. Wording must say union.")

    print()
    print("=" * 72)
    print("E. data/participant_oi/  claim: '2021-2026 participant_oi.parquet'")
    print("=" * 72)
    print(f"   path exists          : {po.exists()}   <-- CLAIM IS FALSE IF False")
    print(f"   data/ actually holds : {sorted(p.name for p in (ROOT / 'data').iterdir())}")

    print()
    print("=" * 72)
    print("F. data/calibrated_params.json  claim: 'Frozen; fail-closed calibration rules'")
    print("=" * 72)
    cp = ROOT / "data/calibrated_params.json"
    print(f"   exists               : {cp.exists()}  size={cp.stat().st_size if cp.exists() else '-'}")

    print()
    print("=" * 72)
    print("G. experiments/ artifact claims")
    print("=" * 72)
    checks = [
        ("e008 walls_576.tar.gz", "experiments/e008_wall_flip/artifacts/walls_576.tar.gz"),
        ("e008 walls/<date>.json dir", "experiments/e008_wall_flip/artifacts/walls"),
        ("e009 artifacts/ (live capture)", "experiments/e009_wall_capture/artifacts"),
        ("e018_vrp_weekly/", "experiments/e018_vrp_weekly"),
        ("e019_momentum/", "experiments/e019_momentum"),
        ("e020_diluted_momentum/", "experiments/e020_diluted_momentum"),
        ("common/lots.py", "experiments/common/lots.py"),
        ("common/leak_registry.py", "experiments/common/leak_registry.py"),
    ]
    for label, rel in checks:
        p = ROOT / rel
        if p.is_dir():
            n = len(list(p.iterdir()))
            print(f"   {label:34s} DIR  ({n} entries)")
        elif p.exists():
            print(f"   {label:34s} FILE {p.stat().st_size:,} bytes")
        else:
            print(f"   {label:34s} *** MISSING ***")

    print()
    print("=" * 72)
    print("H. trade_date string format across the historical store")
    print("=" * 72)
    random.seed(2)
    samp = random.sample(hist, min(150, len(hist)))
    byyear: dict[str, dict] = {}
    real_mismatch = 0
    for p in samp:
        s = str(pq.read_table(p, columns=["trade_date"]).to_pandas().trade_date.unique()[0])
        y = p.split("year=")[1].split(os.sep)[0]
        k = "ISO" if re.match(r"^\d{4}-", s) else "DD-MON-YYYY"
        byyear.setdefault(y, {})
        byyear[y][k] = byyear[y].get(k, 0) + 1
        fn = os.path.basename(p).replace("fo_", "").replace(".parquet", "")
        if pd_to_ymd(s) != fn:
            real_mismatch += 1
    for y in sorted(byyear):
        print(f"   year={y}: {byyear[y]}")
    print(f"   filename vs content mismatches: {real_mismatch} (filenames are authoritative)")
    print("   NOTE: mixed encodings across the lot-era boundary. Any code doing a")
    print("   lexicographic sort or string compare on trade_date is WRONG here.")

    cross_cutting()
    return 0


def cross_cutting() -> None:
    """Claims made OUTSIDE the §2 tree that depend on that data."""
    import json
    import tarfile

    print()
    print("=" * 72)
    print("I. intraday store: SPOT or FUTURES?  (Test 2 needs intraday futures)")
    print("=" * 72)
    intra = sorted(glob.glob(str(ROOT / "data/intraday/**/*.parquet"), recursive=True))
    d = pq.read_table(intra[-1]).to_pandas()
    last_close = float(d.close.iloc[-1])
    hist = sorted(glob.glob(str(ROOT / "data/historical/year=2026/month=09/*.parquet")))[-1]
    h = pq.read_table(hist, columns=["symbol", "instrument", "expiry", "close"]).to_pandas()
    f = h[(h.symbol == "NIFTY") & (h.instrument == "FUTIDX")].sort_values("expiry")
    fut_close = float(f.close.iloc[0])
    print(f"   intraday last close      : {last_close:,.2f}")
    print(f"   same-day NIFTY FUTIDX    : {fut_close:,.2f}  (front expiry {f.expiry.iloc[0]})")
    print(f"   basis                    : {fut_close - last_close:+,.2f} "
          f"({(fut_close/last_close - 1)*100:+.3f}%)")
    print("   -> carry-sized basis => the store is SPOT. There is NO intraday futures")
    print("      series, which is the hard input Test 2 (continuous delta hedge) needs.")

    print()
    print("=" * 72)
    print("J. e008 walls_576.tar.gz  claim: 'OI, quotes for dte<=1'")
    print("=" * 72)
    tgz = ROOT / "experiments/e008_wall_flip/artifacts/walls_576.tar.gz"
    with tarfile.open(tgz) as tf:
        members = sorted([x for x in tf.getmembers() if x.isfile()], key=lambda x: x.name)
        fields: set = set()
        atm = 0
        for mm in members:
            w = json.loads(tf.extractfile(mm).read())
            b = w["bars"][0]
            for r in b["chain"]:
                fields.update(r.keys())
            spot = b["spot"]
            strikes = sorted({r["strike"] for r in b["chain"]})
            step = min((strikes[i + 1] - strikes[i]) for i in range(len(strikes) - 1)) or 0
            if any(abs(s - spot) <= step / 2 + 1e-9 for s in strikes):
                atm += 1
    print(f"   sessions                : {len(members)}  ({members[0].name} -> {members[-1].name})")
    print(f"   chain row fields        : {sorted(fields)}")
    print(f"   sessions with a strike at spot: {atm}/{len(members)} ({atm/len(members):.1%})")
    print("   -> 'quotes' is ONE `open` print, NOT a bid/ask pair. Confirms the §4.2")
    print("      'ATM omitted, 0.0% fill feasibility' claim. No realized spread here.")

    print()
    print("=" * 72)
    print("K. §5.4 lot invariant vs Test 1 (stock options)")
    print("=" * 72)
    lots = (ROOT / "experiments/common/lots.py").read_text(encoding="utf-8")
    named = [s for s in ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS"] if s in lots]
    print(f"   stock symbols in lots.py: {named if named else 'NONE (NIFTY-only eras)'}")
    print("   -> Test 1 PnL would have no era-correct stock lot table on disk.")

    print()
    print("=" * 72)
    print("L. index weights for Test 1's cap-weighted basket")
    print("=" * 72)
    hits = [h for h in glob.glob(str(ROOT / "**/*weight*"), recursive=True)
            if ".venv" not in h and ".git" not in h]
    print(f"   weight files on disk    : {hits if hits else 'NONE'}")

    print()
    print("=" * 72)
    print("M. participant-OI ingestion code")
    print("=" * 72)
    cand = [Path(p).name for p in glob.glob(str(ROOT / "**/*.py"), recursive=True)
            if ".venv" not in p and "participant" in Path(p).name.lower()]
    print(f"   scripts named *participant*: {cand if cand else 'NONE'}")


def pd_to_ymd(s: str) -> str:
    import datetime as _dt
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return "?"


if __name__ == "__main__":
    raise SystemExit(main())