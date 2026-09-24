"""Shared raw-archive loader. Previously duplicated (with the same latent bug)
across notebooks/01, 02, 03, 05 - see git history 2026-08-11/12 for the fix.

Batched: with 10k+ archived polls, one flat Python list of all row-tuples
(~3.4M entries) hits MemoryError on an 8GB machine before pandas ever sees
it - tuple-object overhead alone is ~650-700MB, right at this laptop's free
RAM. Flushing every `batch_size` files into a compact columnar DataFrame
keeps peak memory to one batch's worth of tuples plus the (much smaller)
concatenated column buffers, not the full row count as Python objects.

2026-09-22: the collector kept running past the 2026-08-11 fix's working
size (10-16k files) to 24k+, and batching alone wasn't enough anymore -
each flushed batch was still four Python-object columns (interned str,
Timestamp, int, int), and ALL batches stay resident until the final concat,
so peak memory still scaled with the FULL collection, not one batch. Each
batch is now downcast to compact dtypes (category/datetime64/int16) right
after construction - same values, ~10x smaller in memory - which is what
actually bounds peak memory as the collection keeps growing.
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
            batch_df = pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])
            batch_df["station_id"] = batch_df["station_id"].astype("category")
            batch_df["ts"] = pd.to_datetime(batch_df["ts"], utc=True)
            batch_df["num_bikes_available"] = pd.to_numeric(batch_df["num_bikes_available"], downcast="integer")
            batch_df["num_docks_available"] = pd.to_numeric(batch_df["num_docks_available"], downcast="integer")
            batches.append(batch_df)
            rows = []
    if corrupt:
        print(f"WARNING: skipped {corrupt} unreadable/corrupt raw file(s)")
    return pd.concat(batches, ignore_index=True, copy=False)


def demo():
    """Verifies the dtype downcast (category/datetime64/int) preserves values
    and that batching (batch_size=1, forcing 2 flushes) doesn't drop/duplicate
    rows or misalign the (station_id, ts) -> value mapping."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        polls = [
            (1700000000, [(1, 5, 10), (2, 3, 12)]),
            (1700000060, [(1, 4, 11), (2, 3, 12)]),
        ]
        for i, (last_updated, stations) in enumerate(polls):
            payload = {
                "last_updated": last_updated,
                "data": {"stations": [
                    {"station_id": sid, "num_bikes_available": b, "num_docks_available": k}
                    for sid, b, k in stations
                ]},
            }
            with gzip.open(os.path.join(d, f"{i}.json.gz"), "wt", encoding="utf-8") as f:
                json.dump(payload, f)

        df = load_snapshots(pattern=os.path.join(d, "*.json.gz"), batch_size=1)
        assert len(df) == 4
        assert str(df["station_id"].dtype) == "category"
        assert str(df["ts"].dtype).startswith("datetime64")
        assert df["num_bikes_available"].dtype.kind == "i" and df["num_docks_available"].dtype.kind == "i"
        row = df[(df["station_id"] == "1") & (df["ts"] == pd.Timestamp(1700000060, unit="s", tz="UTC"))]
        assert row["num_bikes_available"].iloc[0] == 4 and row["num_docks_available"].iloc[0] == 11
    print("data_io.demo: OK")


if __name__ == "__main__":
    demo()
