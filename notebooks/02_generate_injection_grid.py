"""T7: full fault injection framework - 6 classes x 4 intensities x 5 seeds
(120 corrupted datasets), reproducible from seed.

Substrate: notebooks/07_multiday_substrate.py's daily periods (supervisor
instruction, 14 September 2026), not the single-longest-block substrate this
file used before (certify_clean_substrate, kept below for the pre-2026-09-14
record and because certify_multiday_substrate reuses its detector-based
exclusion logic per period). Classes 1/2/3/4 place a randomly-timed window
inside the substrate (duration up to 1h); on a single continuous block that
window can never miss real data, but on the concatenated multi-day substrate
a naive random placement can straddle a multi-hour/day gap between periods
and silently draw a diluted, seed-dependent fraction of its nominal duration
- exactly the "RNG placement noise masquerading as intensity variance" problem
already fixed once for Class 4's drift_start (see docs/design_freeze.md §1).
certify_multiday_substrate + the period-confinement in generate_one fixes this
the same way: each windowed experiment is confined to one seeded-random period,
never spanning the gap to the next. Classes 5/6 have no window (rate/share
only) and are unaffected, so they still act on the full concatenated substrate.

Each corrupted dataset is saved as parquet (small, one file per experiment) with
an NLOD-required modification label in its own sidecar metadata - never presented
as observed BikeMi data.
"""
import sys
import json
import glob
import gzip
from pathlib import Path
from importlib import import_module

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.injection import (
    inject_station_dropout, inject_frozen_counter, inject_stale_update,
    inject_capacity_inconsistency, inject_value_jump, inject_silent_offset,
)

SEEDS = [0, 1, 2, 3, 4]

# classes whose injector places a bounded time WINDOW rather than acting
# row-by-row/station-by-station globally - these are the ones that need
# per-experiment period confinement on the multi-day substrate.
WINDOWED_CLASSES = {"class1_dropout", "class2_frozen", "class3_stale", "class4_capacity"}

GRID_SPEC = {
    "class1_dropout": {
        # durations sized for the certified substrate (6.2h, see certify_clean_substrate):
        # 1h max leaves headroom for 5 independently-placed seeds without heavy overlap
        "injector": inject_station_dropout,
        "intensities": [
            {"stations": 1, "duration": "5min"},
            {"stations": 1, "duration": "15min"},
            {"stations": 3, "duration": "30min"},
            {"stations": 5, "duration": "1h"},
        ],
    },
    "class2_frozen": {
        "injector": inject_frozen_counter,
        "intensities": [
            {"station": None, "duration": "5min"},
            {"station": None, "duration": "15min"},
            {"station": None, "duration": "30min"},
            {"station": None, "duration": "1h"},
        ],
    },
    "class3_stale": {
        "injector": inject_stale_update,
        "intensities": [
            {"lag_s": 60, "scope": None},
            {"lag_s": 300, "scope": None},
            {"lag_s": 900, "scope": None},
            {"lag_s": 3600, "scope": None},
        ],
    },
    "class4_capacity": {
        "injector": inject_capacity_inconsistency,
        "intensities": [{"magnitude": m} for m in (2, 5, 10, 20)],
    },
    "class5_jump": {
        "injector": inject_value_jump,
        "intensities": [{"magnitude": m, "rate": 0.05} for m in (2, 5, 10, 20)],
    },
    "class6_silent": {
        "injector": inject_silent_offset,
        "intensities": [{"offset_k": k, "share": 0.05} for k in (1, 2, 4, 8)],
    },
}


def load_clean_substrate(pattern="data/raw/*.json.gz"):
    from src.data_io import load_snapshots
    return load_snapshots(pattern)


def certify_clean_substrate(raw, max_gap_s=120):
    """docs/thesis_outline.md §4: the injection substrate is the longest
    continuous high-coverage segment of the collection, not the full (gappy)
    collection - concretely motivated by generate_one() producing zero-effect
    dropout injections when a randomly chosen window landed inside a real gap.

    Finds the longest run of polls with no gap > max_gap_s between consecutive
    polls, then excludes rows the Class-5 detector flags as implausible jumps
    (the one detector with a low, credible natural false-positive rate - ~1.6%
    on the full collection). Class 2/4 natural-anomaly counts are reported but
    NOT excluded: detect_frozen_counter's high natural flag rate (O3, ~45%) makes
    blind exclusion too aggressive without first resolving that calibration
    question, and Class 4's declared-capacity half is structurally unimplementable
    (O4, no station_information feed collected) - both flagged, not silently
    swept away."""
    from src.validation import detect_implausible_jump, detect_frozen_counter

    ts_sorted = sorted(raw["ts"].unique())
    segments, seg_start, prev = [], ts_sorted[0], ts_sorted[0]
    for t in ts_sorted[1:]:
        if (t - prev).total_seconds() > max_gap_s:
            segments.append((seg_start, prev))
            seg_start = t
        prev = t
    segments.append((seg_start, prev))
    best_start, best_end = max(segments, key=lambda se: (se[1] - se[0]).total_seconds())

    segment = raw[(raw["ts"] >= best_start) & (raw["ts"] <= best_end)].reset_index(drop=True)
    print(f"Longest continuous segment: {best_start} -> {best_end} "
          f"({(best_end - best_start).total_seconds() / 3600:.1f}h, {len(segment)} rows, "
          f"{len(segments)} total segments found)")

    jumps = detect_implausible_jump(segment, max_flow_per_min=1.0)
    n_jump = int(jumps["jump_flag"].sum())
    frozen = detect_frozen_counter(segment, window="60min")
    n_frozen = int(frozen["frozen"].sum())
    print(f"Natural anomalies in segment: {n_jump} implausible-jump rows (excluded), "
          f"{n_frozen} frozen-counter rows (counted only, NOT excluded - see O3)")

    clean = jumps.loc[~jumps["jump_flag"], ["station_id", "ts", "num_bikes_available", "num_docks_available"]]
    return clean.reset_index(drop=True)


def certify_multiday_substrate(raw, max_gap_s=120):
    """Multi-day analogue of certify_clean_substrate: uses
    notebooks/07_multiday_substrate.py:load_certified_periods() - the exact
    62-period, 251.5h substrate certified 2026-09-19 and approved by Russo -
    instead of recomputing periods against whatever the (still-running)
    collector has produced since. Same per-segment exclusion rule as the old
    single-block substrate (Class-5 implausible-jump rows excluded, Class-2
    natural frozen rate counted only - see certify_clean_substrate's
    docstring for why), just run once per period and concatenated.

    Returns (clean, period_bounds): `clean` has a `period_id` column so
    generate_one can confine a windowed injection to one period's rows;
    `period_bounds` is a DataFrame of (period_id, start, end) used to pick a
    valid injection start/duration without straddling the gap to the next
    period."""
    from src.validation import detect_implausible_jump, detect_frozen_counter
    load_certified_periods = import_module("07_multiday_substrate").load_certified_periods

    kept = load_certified_periods()

    clean_parts, n_jump_total, n_frozen_total = [], 0, 0
    for i, prd in enumerate(kept.itertuples()):
        seg = raw[(raw["ts"] >= prd.start) & (raw["ts"] <= prd.end)].reset_index(drop=True)
        jumps = detect_implausible_jump(seg, max_flow_per_min=1.0)
        n_jump_total += int(jumps["jump_flag"].sum())
        frozen = detect_frozen_counter(seg, window="60min")
        n_frozen_total += int(frozen["frozen"].sum())
        c = jumps.loc[~jumps["jump_flag"], ["station_id", "ts", "num_bikes_available", "num_docks_available"]].copy()
        c["period_id"] = i
        clean_parts.append(c)
    clean = pd.concat(clean_parts, ignore_index=True)
    print(f"Multi-day substrate: {len(kept)} periods, {kept['duration_h'].sum():.1f}h total, "
          f"{len(clean)} clean rows, {clean['station_id'].nunique()} stations. "
          f"Natural anomalies: {n_jump_total} implausible-jump rows (excluded), "
          f"{n_frozen_total} frozen-counter rows (counted only, NOT excluded - see O3).")

    period_bounds = kept[["start", "end"]].reset_index().rename(columns={"index": "period_id"})
    return clean.reset_index(drop=True), period_bounds


def generate_one(clean, class_name, intensity_idx, seed, period_bounds=None):
    spec = GRID_SPEC[class_name]
    params = dict(spec["intensities"][intensity_idx])

    if class_name not in WINDOWED_CLASSES or period_bounds is None:
        return spec["injector"](clean, **params, seed=seed)

    # confine this experiment's window to ONE seeded-random period, so it
    # never straddles the gap to the next day (see module docstring)
    rng = np.random.default_rng(seed)
    p = period_bounds.iloc[rng.integers(0, len(period_bounds))]

    if class_name == "class3_stale":
        # inject_stale_update already supports a (start, end) scope; also
        # pull the end in by lag_s so freeze_until can't reach past the
        # period boundary (its own affected_ts search uses the FULL
        # timeline, not just this period's rows - see verification below)
        params["scope"] = (p["start"], p["end"] - pd.Timedelta(seconds=params["lag_s"]))
        return spec["injector"](clean, **params, seed=seed)

    period_mask = (clean["ts"] >= p["start"]) & (clean["ts"] <= p["end"])
    period_df = clean.loc[period_mask].reset_index(drop=True)
    rest = clean.loc[~period_mask].reset_index(drop=True)
    corrupted_period = spec["injector"](period_df, **params, seed=seed)
    return pd.concat([rest, corrupted_period], ignore_index=True)


def run_full_grid(clean, period_bounds=None, out_dir=None):
    """Runs all 120 (class x intensity x seed) combinations. If out_dir is given,
    saves each corrupted dataset as parquet + an NLOD-labelled JSON sidecar;
    always returns a summary DataFrame (one row per experiment) regardless."""
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for class_name, spec in GRID_SPEC.items():
        for intensity_idx, params in enumerate(spec["intensities"]):
            for seed in SEEDS:
                corrupted = generate_one(clean, class_name, intensity_idx, seed, period_bounds)
                if len(corrupted) != len(clean):
                    rows_changed = len(clean) - len(corrupted)
                elif "true_available" in corrupted.columns:
                    # class 6: num_bikes_available is UNCHANGED by design (feed-invisible);
                    # the real signal is true_available, a parallel cost-model-only column
                    rows_changed = int((corrupted["true_available"].values
                                         != corrupted["num_bikes_available"].values).sum())
                else:
                    # keyed merge, not a positional array compare: classes 2/4's injectors
                    # internally re-sort their output by (station_id, ts), so `corrupted`'s
                    # row order no longer matches `clean`'s period-block order - a positional
                    # compare here silently diffs unrelated rows (found 2026-09-22: inflated
                    # "rows changed" up to 2.3M/4.66M for a single-station 1h window). This is
                    # a diagnostic count only (04_dose_response_analysis.py's real scoring
                    # already merges on (station_id, ts) throughout, unaffected).
                    m = clean[["station_id", "ts", "num_bikes_available"]].merge(
                        corrupted[["station_id", "ts", "num_bikes_available"]],
                        on=["station_id", "ts"], suffixes=("_clean", "_corrupt"))
                    rows_changed = int((m["num_bikes_available_clean"] != m["num_bikes_available_corrupt"]).sum())
                exp_id = f"{class_name}__i{intensity_idx}__seed{seed}"
                if out_dir is not None:
                    corrupted.to_parquet(out_dir / f"{exp_id}.parquet", index=False)
                    (out_dir / f"{exp_id}.json").write_text(json.dumps({
                        "class": class_name, "intensity_idx": intensity_idx,
                        "params": params, "seed": seed,
                        "data_status": "SYNTHETIC - modified from observed BikeMi data per NLOD 2.0; "
                                       "never to be reported as observed data",
                        "rows_clean": len(clean), "rows_corrupted": len(corrupted),
                    }, indent=2, default=str))
                summary.append({
                    "experiment_id": exp_id, "class": class_name,
                    "intensity_idx": intensity_idx, "params": params, "seed": seed,
                    "n_rows_clean": len(clean), "n_rows_corrupted": len(corrupted),
                    "rows_changed_or_removed": rows_changed,
                })
    return pd.DataFrame(summary)


def main():
    print("Loading raw collection...")
    raw = load_clean_substrate()
    print(f"{len(raw)} rows, {raw['station_id'].nunique()} stations")

    print("\nCertifying multi-day injection substrate (daily periods, Russo 2026-09-14)...")
    clean, period_bounds = certify_multiday_substrate(raw)
    print(f"Certified substrate: {len(clean)} rows, {clean['station_id'].nunique()} stations, "
          f"{len(period_bounds)} periods")

    # windowed classes (1-4) pick their period from the TEST periods only (methodology
    # §4.5; fixed 2026-09-24 - they used to pick from all 62, so most windows landed in
    # train/val periods the model was fit/tuned on). Classes 5/6 still corrupt the whole
    # substrate; 04 only ever scores the test periods, so the rest is never read.
    config = json.loads((Path(__file__).resolve().parents[1] / "models" / "frozen_config.json").read_text())
    period_bounds = period_bounds[import_module("07_multiday_substrate").test_period_mask(period_bounds, config)]
    print(f"Injection windows confined to {len(period_bounds)} test periods")

    print("\nGenerating full 6 x 4 x 5 = 120 experiment grid...")
    summary = run_full_grid(clean, period_bounds, out_dir="data/injected")
    print(f"Generated {len(summary)} corrupted datasets (expected 120).")
    print(summary.groupby("class")["rows_changed_or_removed"].agg(["min", "median", "max"]))

    # reproducibility check: same (class, intensity, seed) must give identical output
    a = generate_one(clean, "class5_jump", 0, seed=3, period_bounds=period_bounds)
    b = generate_one(clean, "class5_jump", 0, seed=3, period_bounds=period_bounds)
    assert a.equals(b), "same seed must reproduce identically"
    print("\nReproducibility check (same class/intensity/seed twice): OK")

    # period-confinement check: classes 1/2/4 are confined by construction
    # (their injector only ever sees the period-sliced rows). Class 3 is the
    # one residual risk - it reads clean's FULL timeline internally, bounded
    # only by the scope this session narrowed by lag_s - so verify directly:
    # every row it actually changed must sit inside a single period.
    bounds_list = list(period_bounds.itertuples())
    clean_sorted = clean.sort_values(["station_id", "ts"]).reset_index(drop=True)
    for intensity_idx in range(len(GRID_SPEC["class3_stale"]["intensities"])):
        corrupted = generate_one(clean, "class3_stale", intensity_idx, seed=1, period_bounds=period_bounds)
        changed = corrupted["num_bikes_available"].values != clean_sorted["num_bikes_available"].values
        if not changed.any():
            continue
        touched_ts = corrupted.loc[changed, "ts"]
        in_one_period = any((touched_ts.min() >= b.start) and (touched_ts.max() <= b.end) for b in bounds_list)
        assert in_one_period, f"class3_stale intensity {intensity_idx} leaked across a period gap"
    print("Period-confinement check (class3_stale never crosses a day gap): OK")


if __name__ == "__main__":
    main()
