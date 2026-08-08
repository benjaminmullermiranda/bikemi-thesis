"""Does last_reported carry per-station information?

If it is identical across all stations in every snapshot, it is a feed-level
batch timestamp and cannot detect per-station staleness (classes 2 and 3).
"""
import gzip, json, glob
from collections import Counter

files = sorted(glob.glob("data/raw/*.json.gz"))
offsets, spread, bad = Counter(), Counter(), 0

for f in files:
    try:
        d = json.load(gzip.open(f, "rt", encoding="utf-8"))
        t = d["last_updated"]
        offs = [t - s["last_reported"] for s in d["data"]["stations"]]
    except Exception:
        bad += 1
        continue
    spread[len(set(offs))] += 1
    offsets.update(offs)

print(f"Snapshots analysed: {len(files)-bad}   (unreadable: {bad})")
print(f"Distinct offset values in whole dataset: {len(offsets)}")
for k, n in offsets.most_common(8):
    print(f"    offset {k:>7} s   ->  {n} station-observations")
print("Distinct offsets WITHIN one snapshot:")
for k, n in sorted(spread.items()):
    print(f"    {k} distinct value(s)  ->  {n} snapshots")
