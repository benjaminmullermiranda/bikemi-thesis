"""Safeguard layer - detectors for anomaly classes 1-5 (docs/thesis_outline.md, taxonomy).

Class 6 (silent misreporting) has NO detector BY DESIGN: it is feed-invisible,
which is exactly why it defines the 'unrecoverable floor' in the thesis.

Detectors 1, 2, 4, 5 take the tidy per-(station_id, ts) frame used elsewhere in
src/ (station_id, ts, num_bikes_available, num_docks_available, ...). Detector 3
is feed-level, not per-station (last_reported is a batch value identical across
all stations here - verified in notebooks/00_last_reported_check.py) and needs a
different, per-poll input: request_ts (collector clock), last_updated (feed's own
clock, embedded in the JSON body), and payload_sha256 - all in data/metadata.csv,
joined against each raw file's last_updated by matching request_ts to filename.
"""
import numpy as np
import pandas as pd


def detect_station_dropout(df, registry):
    """Class 1 (completeness): stations in `registry` absent from the feed window.
    df: tidy frame with a station_id column. registry: iterable of expected ids.
    Returns a Series indexed by station_id, True where that station never appeared."""
    present = set(df["station_id"].unique())
    return pd.Series({sid: sid not in present for sid in registry}, name="dropped")


def detect_frozen_counter(df, window="60min"):
    """Class 2 (accuracy/timeliness): zero variance in both bikes and docks over a
    rolling time window per station - a stuck sensor/process reports the same
    reading repeatedly.

    ponytail: this can't distinguish a real quiet period (station legitimately
    untouched) from a frozen sensor - the outline flags this as an inherent
    limitation of the signal, not something a smarter rule fixes for free.
    Returns df with a `frozen` boolean column appended."""
    df = df.sort_values(["station_id", "ts"]).reset_index(drop=True)
    out = []
    for _, g in df.groupby("station_id", sort=False):
        g = g.set_index("ts")
        bikes_nunique = g["num_bikes_available"].rolling(window).apply(lambda x: x.nunique(), raw=False)
        docks_nunique = g["num_docks_available"].rolling(window).apply(lambda x: x.nunique(), raw=False)
        g = g.reset_index()
        g["frozen"] = ((bikes_nunique == 1) & (docks_nunique == 1)).to_numpy()
        out.append(g)
    return pd.concat(out, ignore_index=True)


def detect_stale_update(feed_df, max_age_s=180):
    """Class 3 (timeliness), feed-level only: now (request_ts) - last_updated beyond
    threshold, OR an identical-payload streak (payload_sha256 repeats the previous
    poll's - the upstream feed hasn't actually changed since the last poll).
    feed_df: one row per poll, columns request_ts, last_updated (tz-aware
    datetimes) and payload_sha256, sorted or not (this function sorts).
    Returns feed_df sorted by request_ts with a `stale` boolean column appended."""
    feed_df = feed_df.sort_values("request_ts").reset_index(drop=True)
    age_s = (feed_df["request_ts"] - feed_df["last_updated"]).dt.total_seconds()
    repeat_hash = feed_df["payload_sha256"] == feed_df["payload_sha256"].shift(1)
    feed_df = feed_df.copy()
    feed_df["stale"] = (age_s > max_age_s) | repeat_hash
    return feed_df


def detect_capacity_inconsistency(df, type_cols):
    """Class 4 (consistency): num_bikes_available should equal the sum of its
    vehicle-type breakdown (e.g. bike + ebike + ebike_with_childseat) - broken
    docks or config drift can make them disagree.

    ponytail: capacity (bikes+docks vs a declared, externally-published station
    capacity) is the OTHER half of this taxonomy entry, but needs the GBFS
    station_information feed, which this project has never collected (only
    station_status). Only the type-sum check is implementable from current data.
    Returns df with an `inconsistent` boolean column appended."""
    df = df.copy()
    df["inconsistent"] = df["num_bikes_available"] != df[list(type_cols)].sum(axis=1)
    return df


def detect_implausible_jump(df, max_flow_per_min=1.0):
    """Class 5 (validity): |delta bikes| beyond plausible flow per interval -
    a physically implausible number of bikes changing at one station between
    two consecutive polls. Returns df with a `jump_flag` boolean column appended."""
    df = df.sort_values(["station_id", "ts"]).reset_index(drop=True)
    grouped = df.groupby("station_id", sort=False)
    delta = (df["num_bikes_available"] - grouped["num_bikes_available"].shift(1)).abs()
    elapsed_min = (df["ts"] - grouped["ts"].shift(1)).dt.total_seconds() / 60
    df = df.copy()
    df["jump_flag"] = delta > (max_flow_per_min * elapsed_min)
    return df


def demo():
    from datetime import datetime, timedelta, timezone

    # --- Class 1: station dropout ---
    df1 = pd.DataFrame({"station_id": ["s1", "s1", "s2"]})
    dropped = detect_station_dropout(df1, registry=["s1", "s2", "s3"])
    assert dropped.to_dict() == {"s1": False, "s2": False, "s3": True}

    # --- Class 2: frozen counter ---
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(100):
        # s_frozen: stuck at (5,10) for the whole window. s_normal: bikes cycle.
        rows.append(("s_frozen", start + timedelta(minutes=i), 5, 10))
        rows.append(("s_normal", start + timedelta(minutes=i), i % 7, 20 - (i % 7)))
    df2 = pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])
    frozen = detect_frozen_counter(df2, window="60min")
    assert frozen[(frozen.station_id == "s_frozen") & (frozen.ts == start + timedelta(minutes=90))]["frozen"].iloc[0]
    assert not frozen[(frozen.station_id == "s_normal") & (frozen.ts == start + timedelta(minutes=90))]["frozen"].iloc[0]

    # --- Class 3: stale feed (feed-level) ---
    feed_df = pd.DataFrame({
        "request_ts": [start, start + timedelta(minutes=1), start + timedelta(minutes=2)],
        "last_updated": [start, start, start + timedelta(minutes=2)],  # 2nd poll: feed didn't update
        "payload_sha256": ["hash_a", "hash_a", "hash_b"],               # 2nd poll: identical payload
    })
    stale = detect_stale_update(feed_df, max_age_s=180)
    assert stale["stale"].tolist() == [False, True, False]

    # --- Class 4: capacity inconsistency (type-sum check) ---
    df4 = pd.DataFrame({
        "num_bikes_available": [5, 5],
        "bike": [3, 3], "ebike": [2, 1], "ebike_with_childseat": [0, 0],  # row 1: 3+1+0=4 != 5
    })
    inconsistent = detect_capacity_inconsistency(df4, type_cols=["bike", "ebike", "ebike_with_childseat"])
    assert inconsistent["inconsistent"].tolist() == [False, True]

    # --- Class 5: implausible jump ---
    # note: a delta-based detector only catches DISCONTINUITIES, not sustained runs -
    # if inject_value_jump corrupts every row independently at rate=1.0, two adjacent
    # corrupted rows can coincidentally land on the same value (zero delta between
    # them), which is correctly NOT flagged. So this is a hand-built single-spike
    # case instead, which is what Class-5 detection is actually meant to catch.
    df5 = pd.DataFrame({
        "station_id": ["s1"] * 6,
        "ts": [start + timedelta(minutes=i) for i in range(6)],
        "num_bikes_available": [10, 10, 18, 10, 10, 10],  # single 8-bike spike at index 2, back to normal at index 3
    })
    flagged = detect_implausible_jump(df5, max_flow_per_min=1.0)
    assert flagged["jump_flag"].tolist() == [False, False, True, True, False, False]

    print("validation.demo: OK")


if __name__ == "__main__":
    demo()
