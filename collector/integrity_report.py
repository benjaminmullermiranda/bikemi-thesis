"""Daily integrity report for the collector.

COVERAGE     = polls logged / polls expected (did we observe?)
SUCCESS RATE = HTTP 200 / polls logged (did the feed answer?)
"""
import csv
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE = Path(__file__).resolve().parents[1]
META = BASE / "data" / "metadata.csv"
COLS = ["ts", "status", "latency_ms", "bytes", "n_stations", "sha16"]
CADENCE_S, GAP_S = 61, 120

def main():
    if not META.exists():
        print("No metadata.csv yet - has the collector run?"); return
    rows = [dict(zip(COLS, r)) for r in csv.reader(open(META, newline="", encoding="utf-8")) if r]
    ok = [r for r in rows if r["status"] == "200"]
    bad = [r for r in rows if r["status"] != "200"]
    ts = [datetime.strptime(r["ts"], "%Y%m%dT%H%M%SZ") for r in rows]
    span = (ts[-1] - ts[0]).total_seconds()
    expected = int(span / CADENCE_S) + 1
    gaps = [(a, round((b - a).total_seconds())) for a, b in zip(ts, ts[1:])
            if (b - a).total_seconds() > GAP_S]
    st = [int(r["n_stations"]) for r in ok if str(r["n_stations"]).isdigit()]
    streak = best = 1
    for a, b in zip(ok, ok[1:]):
        streak = streak + 1 if a["sha16"] == b["sha16"] else 1
        best = max(best, streak)
    print(f"Period        : {ts[0]} -> {ts[-1]} UTC  ({span/3600:.1f} h)")
    print(f"COVERAGE      : {100*len(rows)/expected:.1f}%   ({len(rows)} logged / ~{expected} expected)")
    print(f"Success rate  : {100*len(ok)/len(rows):.1f}%   ({len(ok)} HTTP 200 of {len(rows)} logged)")
    print(f"Errors logged : {len(bad)}")
    if bad:
        kinds = Counter(r["sha16"].split(":")[0] for r in bad)
        for k, n in kinds.most_common():
            print(f"    {n:5}  {k[:70]}")
    print(f"Gaps > 2 min  : {len(gaps)}  |  time lost: {sum(g for _, g in gaps)/3600:.1f} h   (ALL listed below)")
    for t, g in gaps:
        print(f"    {t} UTC  ->  {g:6} s ({g/60:.0f} min)")
    if st: print(f"Stations      : min={min(st)}  max={max(st)}")
    print(f"Longest identical-payload streak: {best}")
    if best >= 3:
        print("  ! >=3 identical payloads in a row -> possible frozen upstream cache")

if __name__ == "__main__":
    main()
