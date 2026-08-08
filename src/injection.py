"""Controlled fault injectors - anomaly classes 1-6, applied at SERVING TIME only
to the pre-certified clean substrate (6 classes x 4 intensities x 5 seeds).

Every injector returns just the corrupted DataFrame (same convention as the
existing inject_value_jump) - never a separate log. Ground truth for scoring
detection/recovery later always comes from diffing the corrupted df against the
clean df the harness already has on hand (row presence for dropout, value
equality elsewhere), not from a side-channel the injector reports about itself.
"""
import numpy as np
import pandas as pd


def inject_station_dropout(df, stations, duration, seed):
    """Class 1 (completeness): station(s) vanish from the feed for `duration`
    (any pandas-parseable offset, e.g. '2h'), simulating registry/backend churn.
    `stations`: int (sample that many stations via `seed`) or a list of station_ids.
    Returns df with the affected rows REMOVED (fewer rows, not NaN'd)."""
    rng = np.random.default_rng(seed)
    duration = pd.Timedelta(duration)
    out = df.copy()
    all_stations = out["station_id"].unique()
    targets = rng.choice(all_stations, size=stations, replace=False) if isinstance(stations, int) else list(stations)
    t_min, t_max = out["ts"].min(), out["ts"].max()
    drop_mask = pd.Series(False, index=out.index)
    for sid in targets:
        max_start = t_max - duration
        start = t_min if max_start <= t_min else t_min + pd.Timedelta(
            seconds=rng.uniform(0, (max_start - t_min).total_seconds()))
        end = start + duration
        drop_mask |= (out["station_id"] == sid) & (out["ts"] >= start) & (out["ts"] <= end)
    return out[~drop_mask].reset_index(drop=True)


def inject_frozen_counter(df, station, duration, seed):
    """Class 2 (accuracy/timeliness): one station's reading gets stuck at a single
    value for `duration` (stuck sensor/process) instead of reflecting real changes.
    `station`: a station_id, or None to pick one at random via `seed`."""
    rng = np.random.default_rng(seed)
    duration = pd.Timedelta(duration)
    out = df.copy().sort_values(["station_id", "ts"]).reset_index(drop=True)
    if station is None:
        station = rng.choice(out["station_id"].unique())
    station_ts = out.loc[out["station_id"] == station, "ts"]
    t_min, t_max = station_ts.min(), station_ts.max()
    max_start = t_max - duration
    start = t_min if max_start <= t_min else t_min + pd.Timedelta(
        seconds=rng.uniform(0, (max_start - t_min).total_seconds()))
    end = start + duration
    window_mask = (out["station_id"] == station) & (out["ts"] >= start) & (out["ts"] <= end)
    if window_mask.any():
        first_idx = out[window_mask].index[0]
        out.loc[window_mask, "num_bikes_available"] = out.loc[first_idx, "num_bikes_available"]
        out.loc[window_mask, "num_docks_available"] = out.loc[first_idx, "num_docks_available"]
    return out


def inject_stale_update(df, lag_s, scope, seed):
    """Class 3 (timeliness), feed-level (per docs/thesis_outline.md: last_reported
    is a batch value, not per-station) - simulates the upstream feed not updating
    for `lag_s` seconds: every poll in that window repeats the last real snapshot's
    values across ALL stations (an identical-payload streak), instead of the real
    (different) values a genuinely-updating feed would have reported.
    `scope`: optional (start, end) tz-aware Timestamp tuple restricting where in
    the timeline the stale window may be chosen; None = anywhere in df's span."""
    rng = np.random.default_rng(seed)
    out = df.copy().sort_values(["station_id", "ts"]).reset_index(drop=True)
    all_ts = sorted(out["ts"].unique())
    candidate_ts = all_ts if scope is None else [t for t in all_ts if scope[0] <= t <= scope[1]]
    if len(candidate_ts) < 2:
        return out
    freeze_from = candidate_ts[rng.integers(0, len(candidate_ts) - 1)]
    freeze_until = freeze_from + pd.Timedelta(seconds=lag_s)
    snapshot = out[out["ts"] == freeze_from].set_index("station_id")
    affected_ts = [t for t in all_ts if freeze_from < t <= freeze_until]
    for t in affected_ts:
        mask = out["ts"] == t
        sids = out.loc[mask, "station_id"]
        out.loc[mask, "num_bikes_available"] = sids.map(snapshot["num_bikes_available"]).values
        out.loc[mask, "num_docks_available"] = sids.map(snapshot["num_docks_available"]).values
    return out


def inject_capacity_inconsistency(df, magnitude, seed, min_effect_duration="30min"):
    """Class 4 (consistency): simulates a broken dock / config drift. Unlike
    Class 2's transient frozen sensor, a physical fault doesn't self-heal: from a
    randomly chosen point onward, ONE randomly chosen station's num_bikes_available
    is persistently offset by `magnitude` WITHOUT compensating num_docks_available,
    breaking the bikes+docks=capacity invariant for the rest of the window.

    drift_start is bounded so at least min_effect_duration of trailing data remains
    (default 30min - the midpoint of Classes 1/2's own 5/15/30/60min intensity scale,
    not a freshly invented number) so the drift always affects a meaningful,
    comparable-across-seeds window - found 2026-08-08: without this bound, a seed
    could draw drift_start at/near the station's LAST timestamp, giving a
    near-zero-row (sometimes zero-row) "corrupted" run purely from where the RNG
    landed, not from the intensity - seed-to-seed placement noise masquerading as
    intensity variance in the class x intensity effect H2 depends on. An absolute
    duration (vs. a fraction of substrate length, tried first) keeps the guarantee
    meaningful regardless of how long the certified substrate ends up being."""
    rng = np.random.default_rng(seed)
    out = df.copy().sort_values(["station_id", "ts"]).reset_index(drop=True)
    station = rng.choice(out["station_id"].unique())
    station_ts = sorted(out.loc[out["station_id"] == station, "ts"].unique())
    min_effect_duration = pd.Timedelta(min_effect_duration)
    latest_allowed = station_ts[-1] - min_effect_duration
    eligible = [t for t in station_ts if t <= latest_allowed]
    candidates = eligible if eligible else station_ts[:1]
    drift_start = candidates[rng.integers(0, len(candidates))]
    mask = (out["station_id"] == station) & (out["ts"] >= drift_start)
    out.loc[mask, "num_bikes_available"] = (out.loc[mask, "num_bikes_available"] + magnitude).clip(lower=0)
    return out


def inject_value_jump(df, magnitude, rate, seed):
    """Class 5 (validity): at a `rate` fraction of rows, replace num_bikes_available
    with an implausible +/-magnitude jump, clipped to [0, capacity]. num_docks_available
    is adjusted to keep bikes+docks = capacity (capacity itself is never corrupted)."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    hit = rng.random(len(out)) < rate
    jump = rng.choice([-1, 1], size=len(out)) * magnitude
    capacity = out["num_bikes_available"] + out["num_docks_available"]
    jumped_bikes = (out["num_bikes_available"] + jump).clip(lower=0)
    jumped_bikes = np.minimum(jumped_bikes, capacity)
    out.loc[hit, "num_bikes_available"] = jumped_bikes[hit]
    out.loc[hit, "num_docks_available"] = (capacity - out["num_bikes_available"])[hit]
    return out


def inject_silent_offset(df, offset_k, share, seed):
    """Class 6: feed-invisible by design; parameters are unanchored sensitivity dims.
    num_bikes_available is left UNCHANGED - that's the whole point: nothing in the
    feed reveals this fault (a bike shows as available but is actually unusable).
    A parallel `true_available` column is added, offset down by `offset_k` at a
    `share` fraction of stations. Only the cost layer should ever read
    `true_available` (to compute real missed-pickup consequences) - the forecast
    model and every detector in src/validation.py must keep seeing the unchanged
    num_bikes_available, or this stops being feed-invisible by construction."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    all_stations = out["station_id"].unique()
    n_affected = max(1, int(round(share * len(all_stations))))
    affected = rng.choice(all_stations, size=n_affected, replace=False)
    out["true_available"] = out["num_bikes_available"]
    mask = out["station_id"].isin(affected)
    out.loc[mask, "true_available"] = (out.loc[mask, "true_available"] - offset_k).clip(lower=0)
    return out


def _make_synthetic(n_stations=3, n_polls=60):
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for s in range(n_stations):
        sid = f"s{s+1}"
        for i in range(n_polls):
            rows.append((sid, start + timedelta(minutes=i), 5 + (i + s) % 10, 15 - (i + s) % 10))
    return pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])


def demo():
    df = pd.DataFrame({
        "num_bikes_available": [10, 5, 0, 20],
        "num_docks_available": [10, 15, 20, 0],
    })
    out = inject_value_jump(df, magnitude=100, rate=1.0, seed=0)
    capacity = df["num_bikes_available"] + df["num_docks_available"]
    out_capacity = out["num_bikes_available"] + out["num_docks_available"]
    assert (out_capacity == capacity).all()             # capacity conserved
    assert (out["num_bikes_available"] >= 0).all()
    assert (out["num_bikes_available"] <= capacity).all()
    assert (out["num_bikes_available"] != df["num_bikes_available"]).any()  # something changed

    # --- Class 1: station dropout ---
    clean = _make_synthetic()
    dropped = inject_station_dropout(clean, stations=1, duration="10min", seed=0)
    assert len(dropped) < len(clean)                                  # rows genuinely removed
    # exactly 1 station lost rows, the others kept all of theirs
    counts_before = clean["station_id"].value_counts()
    counts_after = dropped["station_id"].value_counts().reindex(counts_before.index, fill_value=0)
    changed = counts_before != counts_after
    assert changed.sum() == 1                                          # exactly one station affected

    # --- Class 2: frozen counter ---
    frozen = inject_frozen_counter(clean, station="s1", duration="10min", seed=0)
    s1_clean = clean[clean["station_id"] == "s1"].reset_index(drop=True)
    s1_frozen = frozen[frozen["station_id"] == "s1"].reset_index(drop=True)
    changed = s1_clean["num_bikes_available"] != s1_frozen["num_bikes_available"]
    assert changed.any()                                                # something froze
    assert s1_frozen.loc[changed, "num_bikes_available"].nunique() == 1  # frozen window is a single constant value
    other_unchanged = frozen[frozen["station_id"] != "s1"].reset_index(drop=True)
    clean_others = clean[clean["station_id"] != "s1"].reset_index(drop=True)
    assert other_unchanged.equals(clean_others)                        # other stations untouched

    # --- Class 3: stale update (feed-level - affects ALL stations identically) ---
    stale = inject_stale_update(clean, lag_s=120, scope=None, seed=0)
    changed_rows = (stale["num_bikes_available"] != clean["num_bikes_available"]).sum()
    assert changed_rows > 0                                            # something froze
    # within the stale window, every affected timestamp's per-station value must
    # equal SOME earlier real snapshot's value (repeated, not invented)
    diff_ts = stale.loc[stale["num_bikes_available"] != clean["num_bikes_available"], "ts"].unique()
    assert len(diff_ts) >= 1

    # --- Class 4: capacity inconsistency (persistent drift, not transient) ---
    drifted = inject_capacity_inconsistency(clean, magnitude=5, seed=0)
    cap_before = clean["num_bikes_available"] + clean["num_docks_available"]
    cap_after = drifted["num_bikes_available"] + drifted["num_docks_available"]
    broken = (cap_after != cap_before)
    assert broken.any()                                                # some rows now break capacity
    assert drifted.loc[broken, "station_id"].nunique() == 1            # exactly one station affected

    # --- Class 6: silent offset (feed-invisible - num_bikes_available NEVER changes) ---
    silent = inject_silent_offset(clean, offset_k=2, share=0.34, seed=0)
    assert (silent["num_bikes_available"] == clean["num_bikes_available"]).all()  # untouched, by design
    assert (silent["true_available"] <= silent["num_bikes_available"]).all()
    assert (silent["true_available"] != silent["num_bikes_available"]).any()      # at least one station affected

    print("injection.demo: OK")


if __name__ == "__main__":
    demo()
