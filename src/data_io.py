"""Shared raw-archive loader. Previously duplicated (with the same latent bug)
across notebooks/01, 02, 03, 05 - see git history 2026-08-11/12 for the fix.

Batched: with 10k+ archived polls, one flat Python list of all row-tuples
(~3.4M entries) hits MemoryError on an 8GB machine before pandas ever sees
it - tuple-object overhead alone is ~650-700MB, right at this laptop's free
RAM. Flushing every `batch_size` files into a compact columnar DataFrame
keeps peak memory to one batch's worth of tuples plus the (much smaller)
concatenated column buffers, not the full row count as Python objects.
"""
import sys
import glob
import gzip
import json

import pandas as pd


def load_snapshots(pattern="data/raw/*.json.gz", batch_size=1000):
    batches = []
    rows = []
    seen_last_updated = set()
    corrupt = 0
    files = sorted(glob.glob(pattern))
    for i, f in enumerate(files):
        try:
            d = json.load(gzip.open(f, "rt", encoding="utf-8"))
        except Exception:
            corrupt += 1  # e.g. a truncated write from a crash mid-poll - real, has happened
            continue
        last_updated = d["last_updated"]
        if last_updated in seen_last_updated:
            # upstream feed hadn't updated since the previous poll (a real, naturally
            # occurring stale-feed event) - keep only the first observation of it
            continue
        seen_last_updated.add(last_updated)
        ts = pd.Timestamp(last_updated, unit="s", tz="UTC")
        for s in d["data"]["stations"]:
            # sys.intern: station_id is one of ~320 distinct values repeated across
            # every file - without interning, each row allocates a fresh string object
            rows.append((sys.intern(str(s["station_id"])), ts, s["num_bikes_available"], s["num_docks_available"]))
        if len(rows) >= batch_size * 320 or i == len(files) - 1:
            batches.append(pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"]))
            rows = []
    if corrupt:
        print(f"WARNING: skipped {corrupt} unreadable/corrupt raw file(s)")
    return pd.concat(batches, ignore_index=True, copy=False)
