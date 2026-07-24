"""Daily integrity report for the collector.

Summarises collection health from data/metadata.csv:
uptime, errors, gaps > 2 min, station-count drift, identical-payload streaks
(a streak of identical payloads suggests a frozen upstream cache -> RQ1 material).
Run:  python collector/integrity_report.py
"""
import csv
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
META = BASE / "data" / "metadata.csv"
COLS = ["ts", "status", "latency_ms", "bytes", "n_stations", "sha16"]

def main():
    if not META.exists():
        print("No metadata.csv yet - has the collector run?"); return
    rows = [dict(zip(COLS, r)) for r in csv.reader(open(META, newline="")) if r]
    ok = [r for r in rows if r["status"] == "200"]
    err = [r for r in rows if r["status"] != "200"]
    ts = [datetime.strptime(r["ts"], "%Y%m%dT%H%M%SZ") for r in rows]
    gaps = [(a.isoformat(), round((b - a).total_seconds()))
            for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 120]
    st = [int(r["n_stations"]) for r in ok if str(r["n_stations"]).isdigit()]
    streak = best = 1
    for a, b in zip(ok, ok[1:]):
        streak = streak + 1 if a["sha16"] == b["sha16"] else 1
        best = max(best, streak)
    print(f"Period   : {ts[0]} -> {ts[-1]} UTC")
    print(f"Polls    : {len(rows)}  (ok={len(ok)}, errors={len(err)})")
    print(f"Uptime   : {100*len(ok)/len(rows):.1f}%")
    print(f"Gaps>2min: {len(gaps)}  first few: {gaps[:5]}")
    if st: print(f"Stations : min={min(st)}  max={max(st)}")
    print(f"Longest identical-payload streak: {best}")
    if best >= 3:
        print("  ! >=3 identical payloads in a row -> possible frozen upstream cache")

if __name__ == "__main__":
    main()
