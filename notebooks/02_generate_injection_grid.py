"""T7: full fault injection framework - 6 classes x 4 intensities x 5 seeds
(120 corrupted datasets), reproducible from seed.

ponytail: the substrate here is the FULL loaded collection, not yet the
outline's formally pre-certified "longest continuous high-coverage segment"
(docs/thesis_outline.md §4) - that substrate-selection step (find the segment,
run it through every src/validation.py detector, exclude and COUNT natural
anomalies) is separate prerequisite work, not yet built. Known simplification,
flagged here rather than silently assumed - upgrade path: build that selection
step, then point GRID's `clean` input at its output instead of the raw load.

Each corrupted dataset is saved as parquet (small, one file per experiment) with
an NLOD-required modification label in its own sidecar metadata - never presented
as observed BikeMi data.
"""
import sys
import json
import glob
import gzip
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.injection import (
    inject_station_dropout, inject_frozen_counter, inject_stale_update,
    inject_capacity_inconsistency, inject_value_jump, inject_silent_offset,
)

SEEDS = [0, 1, 2, 3, 4]

GRID_SPEC = {
    "class1_dropout": {
        "injector": inject_station_dropout,
        "intensities": [
            {"stations": 1, "duration": "10min"},
            {"stations": 1, "duration": "30min"},
            {"stations": 3, "duration": "1h"},
            {"stations": 5, "duration": "3h"},
        ],
    },
    "class2_frozen": {
        "injector": inject_frozen_counter,
        "intensities": [
            {"station": None, "duration": "10min"},
            {"station": None, "duration": "30min"},
            {"station": None, "duration": "1h"},
            {"station": None, "duration": "3h"},
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
    rows, seen, corrupt = [], set(), 0
    for f in sorted(glob.glob(pattern)):
        try:
            d = json.load(gzip.open(f, "rt", encoding="utf-8"))
        except Exception:
            corrupt += 1
            continue
        lu = d["last_updated"]
        if lu in seen:
            continue
        seen.add(lu)
        ts = pd.Timestamp(lu, unit="s", tz="UTC")
        for s in d["data"]["stations"]:
            rows.append((s["station_id"], ts, s["num_bikes_available"], s["num_docks_available"]))
    if corrupt:
        print(f"WARNING: skipped {corrupt} unreadable/corrupt raw file(s)")
    return pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])


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


def generate_one(clean, class_name, intensity_idx, seed):
    spec = GRID_SPEC[class_name]
    params = spec["intensities"][intensity_idx]
    return spec["injector"](clean, **params, seed=seed)


def run_full_grid(clean, out_dir=None):
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
                corrupted = generate_one(clean, class_name, intensity_idx, seed)
                if len(corrupted) != len(clean):
                    rows_changed = len(clean) - len(corrupted)
                elif "true_available" in corrupted.columns:
                    # class 6: num_bikes_available is UNCHANGED by design (feed-invisible);
                    # the real signal is true_available, a parallel cost-model-only column
                    rows_changed = int((corrupted["true_available"].values
                                         != corrupted["num_bikes_available"].values).sum())
                else:
                    rows_changed = int((corrupted["num_bikes_available"].values
                                         != clean["num_bikes_available"].values).sum())
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

    print("\nCertifying injection substrate (longest continuous high-coverage segment)...")
    clean = certify_clean_substrate(raw)
    print(f"Certified substrate: {len(clean)} rows, {clean['station_id'].nunique()} stations")

    print("\nGenerating full 6 x 4 x 5 = 120 experiment grid...")
    summary = run_full_grid(clean, out_dir="data/injected")
    print(f"Generated {len(summary)} corrupted datasets (expected 120).")
    print(summary.groupby("class")["rows_changed_or_removed"].agg(["min", "median", "max"]))

    # reproducibility check: same (class, intensity, seed) must give identical output
    a = generate_one(clean, "class5_jump", 0, seed=3)
    b = generate_one(clean, "class5_jump", 0, seed=3)
    assert a.equals(b), "same seed must reproduce identically"
    print("\nReproducibility check (same class/intensity/seed twice): OK")


if __name__ == "__main__":
    main()
