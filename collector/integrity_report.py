"""Daily integrity report for the collector.

Two DISTINCT metrics, deliberately separated:
  COVERAGE     = polls logged / polls expected in the period (did we observe?)
  SUCCESS RATE = HTTP 200 / polls logged (did the feed answer?)
Reporting only the second one would hide collection outages entirely.
"""
import csv
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
META = BASE / "data" / "metadata.csv"
COLS = ["ts", "status", "latency_ms", "bytes", "n_stations", "sha16"]
CADENCE_S = 61
GAP_THRESHOLD_S = 120

def main():
    if not META.exists():
        print("No metadata.csv yet - has the collector run?"); return
    rows = [dict(zip(COLS, r)) for r in csv.reader(open(META, newline="")) if r]
    ok = [r for r in rows if r["status"] == "200"]
    ts = [datetime.strptime(r["ts"], "%Y%m%dT%H%M%SZ") for r in rows]
    span_s = (ts[-1] - ts[0]).total_seconds()
    expected = int(span_s / CADENCE_S) + 1
    gaps = [(a, round((b - a).total_seconds()))
            for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > GAP_THRESHOLD_S]
    lost_s = sum(g for _, g in gaps)
    st = [int(r["n_stations"]) for r in ok if str(r["n_stations"]).isdigit()]
    streak = best = 1
    for a, b in zip(ok, ok[1:]):
        streak = streak + 1 if a["sha16"] == b["sha16"] else 1
        best = max(best, streak)
    print(f"Period        : {ts[0]} -> {ts[-1]} UTC  ({span_s/3600:.1f} h)")
    print(f"COVERAGE      : {100*len(rows)/expected:.1f}%   ({len(rows)} polls logged / ~{expected} expected)")
    print(f"Success rate  : {100*len(ok)/len(rows):.1f}%   ({len(ok)} HTTP 200 of {len(rows)} logged)")
    print(f"Errors logged : {len(rows)-len(ok)}")
    print(f"Gaps > 2 min  : {len(gaps)}  |  time lost in gaps: {lost_s/3600:.1f} h")
    for t, g in gaps[:8]:
        print(f"    {t} UTC  ->  {g} s ({g/60:.0f} min)")
    if st: print(f"Stations      : min={min(st)}  max={max(st)}")
    print(f"Longest identical-payload streak: {best}")
    if best >= 3:
        print("  ! >=3 identical payloads in a row -> possible frozen upstream cache")

if __name__ == "__main__":
    main()
