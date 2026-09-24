"""T11: full dose-response analysis. Runs the frozen model+tau (T8/T9) against
all 120 injected datasets (T7), scored on the 12 frozen TEST periods only
(methodology §4.5; 07's test_period_mask), computing per (class, intensity, seed):
decision-flip rate, Delta-cost, and - for classes with a T6 detector - a
safeguard recovery rate. Aggregates to per-class dose-response curves with
bootstrap CIs (docs/thesis_outline.md H2/H3).

Ground truth for cost/flip evaluation is always the certified clean substrate's
own labels (built once, reused for every comparison) - matching T4's original
principle: corruption changes what the model SEES, never the true outcome.

Safeguard recovery strategy (uniform across classes 1/2/4/5, the ones sharing
the tidy per-station frame with their T6 detector): where the detector flags a
row, replace that row's num_bikes_available/num_docks_available with the last
NON-flagged observation for that station (carry-forward), then rebuild features
and rescore. This is the simplest defensible "safeguard" action a real pipeline
could take (don't trust a flagged reading, fall back to the last trusted one) -
not the only possible strategy, but a documented, uniform one applied identically
everywhere so recovery rates are comparable across classes.

Class 3 (stale update) is feed-level - its detector needs request_ts/payload_sha256,
a different data shape than the injected per-station parquet files carry (already
documented in T6/O4-style gap) - excluded from recovery scoring this pass, flip
rate/Delta-cost still computed normally.
Class 6 (silent offset) has NO detector by design - recovery_rate = 0.0,
definitional "unrecoverable floor" per the outline, not computed.
"""
import sys
import json
import glob
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features import build_features, fetch_weather
from src.model import predict_critical
from src.costs import policy_cost
from src.validation import (
    detect_station_dropout, detect_frozen_counter,
    detect_capacity_inconsistency, detect_implausible_jump,
)

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
INJECTED_DIR = Path(__file__).resolve().parents[1] / "data" / "injected"

RECOVERABLE_CLASSES = {"class1_dropout", "class2_frozen", "class4_capacity", "class5_jump"}


def load_frozen():
    model = joblib.load(MODEL_DIR / "frozen_model.joblib")
    config = json.loads((MODEL_DIR / "frozen_config.json").read_text())
    return model, config


def score(model, config, df, weather=None):
    """df -> (features frame with proba/decision columns, using the frozen
    model/tau; rows with any NaN required feature/weather value are dropped).
    weather: pre-fetched DataFrame (recommended - fetch once, reuse across all
    120+ experiments instead of re-hitting the API every call); fetched fresh
    if not given."""
    feature_cols = config["feature_cols"]
    if weather is None:
        weather = fetch_weather(df["ts"].min().strftime("%Y-%m-%d"), df["ts"].max().strftime("%Y-%m-%d"))
    feat = build_features(df, weather=weather).dropna(subset=feature_cols)
    feat["proba"] = predict_critical(model, feat[feature_cols])
    feat["decision"] = feat["proba"] >= config["tau"]
    # float32, not float64: this machine has very little free RAM (confirmed
    # 2026-09-22 - an OOM on the very first merge, allocating 360MiB just to
    # consolidate one score()'s float64 columns at 4.66M-row scale) and score()
    # runs 120+ times per T37 pass. Precision loss is irrelevant here - proba
    # is thresholded against tau, never compared bit-exactly.
    float_cols = feat.select_dtypes(include="float64").columns
    feat[float_cols] = feat[float_cols].astype("float32")
    return feat


def apply_safeguard(corrupted_df, class_name):
    """Returns a 'recovered' df: rows the class's T6 detector flags get their
    bikes/docks values replaced by the last non-flagged observation for that
    station (carry-forward). Returns None for classes with no applicable
    detector in this data shape (class3_stale, class6_silent)."""
    df = corrupted_df.sort_values(["station_id", "ts"]).reset_index(drop=True)

    if class_name == "class1_dropout":
        return None  # rows are REMOVED, not corrupted-in-place - nothing to carry-forward recover
    elif class_name == "class2_frozen":
        # window must be shorter than the shortest injected intensity (5min, GRID_SPEC
        # class2_frozen level 0) or the detector can never fire on it at all: a time-based
        # rolling window still contains pre-freeze variation until the ENTIRE window falls
        # inside the frozen period. Verified: window="60min" flagged 0/5, 0/15, 0/30, 1/60
        # rows across the four intensities (5/15/30/60min) - it could only ever catch the
        # tail of the longest one. window="3min" flags 3/5, 13/15, 28/30, 58/60 - catches
        # all four. Found and fixed during the 2026-08-08 freeze.
        #
        # NOTE (2026-08-08, after re-running with this fix): delta_cost for class2_frozen
        # is STILL exactly 0.0 across all 20 (intensity, seed) combinations - but this is
        # now a real finding, not the old bug. forecast_error IS non-zero after the fix
        # (up to ~2.4e-5), confirming the detector/model do see the frozen counter; but at
        # this magnitude, against tau=0.6 and this model's weak discrimination (test AUC
        # 0.61), the probability shift never crosses the decision threshold - flip_rate=0.0
        # for every row. recovery_rate stays NaN because there is genuinely no cost gap to
        # recover here, not because the detector can't see the corruption anymore. Class 2's
        # near-zero propagation on this substrate is itself informative for H2 (differing
        # class effects), not a defect to chase further.
        flagged = detect_frozen_counter(df, window="3min")["frozen"]
    elif class_name == "class4_capacity":
        flagged = detect_capacity_inconsistency(
            df.assign(bike=df["num_bikes_available"], ebike=0, ebike_with_childseat=0),
            type_cols=["bike", "ebike", "ebike_with_childseat"],
        )["inconsistent"]
    elif class_name == "class5_jump":
        flagged = detect_implausible_jump(df, max_flow_per_min=1.0)["jump_flag"]
    else:
        return None

    recovered = df.copy()
    for col in ["num_bikes_available", "num_docks_available"]:
        recovered.loc[flagged, col] = np.nan
        recovered[col] = recovered.groupby("station_id")[col].ffill()
    recovered = recovered.dropna(subset=["num_bikes_available", "num_docks_available"])
    return recovered


EMPTY_SCORED = pd.DataFrame(columns=["station_id", "ts", "proba", "decision"])


def _cost_accum():
    return {"c_penalty": 0.0, "c_transit": 0.0, "total": 0.0, "n_dispatches": 0}


def _add_cost(accum, cost):
    for k in accum:
        accum[k] += cost[k]


def evaluate_experiment(model, config, clean_feat_cache_dir, period_bounds, exp_path, weather):
    """Processes one period at a time instead of scoring the full ~4.66M-row
    substrate at once (2026-09-22: this machine has very little free RAM - see
    docs/handoff.md - and the whole-substrate approach OOM'd even after
    float32/gc mitigations). Clean features are scored ONCE per period by the
    orchestrator (build_worker_cache -> build_clean_feat_cache) and read back
    from a small per-period parquet here, not recomputed per experiment - the
    120 workers only ever build_features() the corrupted/recovered side.

    This also fixes a second, independent bug: build_features() sorts by
    (station_id, ts), so scoring the WHOLE multi-day substrate at once put a
    station's rows from different, non-adjacent periods next to each other in
    the merged frame - count_dispatch_episodes (src/costs.py) could then
    silently stitch a "dispatch episode" across the multi-day gap between two
    periods, since it only checks station-id adjacency, not time contiguity.
    Processing strictly one period at a time makes that structurally
    impossible: each policy_cost() call only ever sees one period's rows.

    Ground truth for cost/flip evaluation is always the certified clean
    substrate's own labels - matching T4's original principle: corruption
    changes what the model SEES, never the true outcome.
    """
    meta = json.loads(exp_path.with_suffix(".json").read_text())
    class_name = meta["class"]
    corrupted_df = pd.read_parquet(exp_path)

    do_recovery = class_name in RECOVERABLE_CLASSES and class_name != "class1_dropout"

    is_silent = class_name == "class6_silent"
    true_label_lookup = None
    if is_silent:
        # feed-invisible by design: num_bikes_available never changes, so the model's
        # decisions/proba are IDENTICAL to clean - the real cost is hidden, only visible
        # via true_available (the parallel ground-truth column inject_silent_offset adds).
        # Cheap column ops on raw ints, not a build_features() call - fine at full scale.
        HORIZON_STEPS = 120
        cdf = corrupted_df.sort_values(["station_id", "ts"]).reset_index(drop=True)
        cdf["true_critical"] = (cdf["true_available"] <= 2) | (cdf["num_docks_available"] <= 2)
        cdf["true_label"] = cdf.groupby("station_id", sort=False)["true_critical"].shift(-HORIZON_STEPS)
        true_label_lookup = cdf[["station_id", "ts", "true_label"]]
        del cdf

    total_rows = total_flips = n_err = n_corrupted_rows = 0
    sum_abs_err = 0.0
    clean_cost = _cost_accum()
    corrupted_cost = _cost_accum()
    recovered_cost = _cost_accum() if do_recovery else None

    for p in period_bounds.itertuples():
        cache_path = clean_feat_cache_dir / f"{p.period_id}.parquet"
        if not cache_path.exists():
            continue
        clean_feat_p = pd.read_parquet(cache_path)
        if len(clean_feat_p) == 0:
            continue

        corrupted_slice = corrupted_df.loc[(corrupted_df["ts"] >= p.start) & (corrupted_df["ts"] <= p.end)]
        corrupted_feat_p = score(model, config, corrupted_slice, weather=weather) if len(corrupted_slice) else EMPTY_SCORED

        # LEFT join, not inner: class1_dropout REMOVES rows, and an inner join would
        # silently exclude exactly those rows from evaluation - structurally hiding
        # dropout's entire effect (no data -> no dispatch decision is the real,
        # meaningful consequence, not something to drop from the comparison).
        merged = clean_feat_p.merge(
            corrupted_feat_p[["station_id", "ts", "proba", "decision"]],
            on=["station_id", "ts"], suffixes=("_clean", "_corrupted"), how="left",
        )
        if len(merged) == 0:
            continue
        # Score ONLY rows with a real outcome, for EVERY class (fixed 2026-09-24). The last
        # 2h of each period has no label (~54% of rows); policy_cost casts None -> False, so
        # classes 1-5 used to score those rows as "not critical" while class 6 dropped them -
        # Delta-cost and flip_rate were then computed on different row populations per class.
        merged = merged.dropna(subset=["label"])
        if is_silent:
            merged = merged.merge(true_label_lookup, on=["station_id", "ts"], how="left").dropna(subset=["true_label"])
        if len(merged) == 0:
            continue
        missing_in_corrupted = merged["decision_corrupted"].isna()
        merged["decision_corrupted"] = merged["decision_corrupted"].astype(object).fillna(False).astype(bool)
        n_corrupted_rows += int(missing_in_corrupted.sum())

        total_flips += int((merged["decision_clean"] != merged["decision_corrupted"]).sum())
        total_rows += len(merged)
        if (~missing_in_corrupted).any():
            errs = (merged.loc[~missing_in_corrupted, "proba_corrupted"]
                    - merged.loc[~missing_in_corrupted, "proba_clean"]).abs()
            sum_abs_err += float(errs.sum())
            n_err += len(errs)

        # class 6: decisions are identical by design; the corrupted side is scored against
        # the TRUE (pre-offset) availability, the clean side against its own label
        corrupted_truth = merged["true_label"] if is_silent else merged["label"]
        _add_cost(clean_cost, policy_cost(merged["decision_clean"], merged["label"], station_id=merged["station_id"], ts=merged["ts"]))
        _add_cost(corrupted_cost, policy_cost(merged["decision_corrupted"], corrupted_truth, station_id=merged["station_id"], ts=merged["ts"]))

        if do_recovery:
            # safeguard runs per period (fixed 2026-09-24): the carry-forward used to run
            # over the whole multi-day frame, so a flagged first row of a period inherited
            # a value from hours/days earlier (suspected cause of class 2's +165 EUR
            # post-safeguard cost in the 2026-09-24 all-periods run)
            recovered_slice = apply_safeguard(corrupted_slice, class_name) if len(corrupted_slice) else corrupted_slice
            recovered_feat_p = score(model, config, recovered_slice, weather=weather) if len(recovered_slice) else EMPTY_SCORED
            merged_r = merged.merge(
                recovered_feat_p[["station_id", "ts", "decision"]].rename(columns={"decision": "decision_recovered"}),
                on=["station_id", "ts"], how="left",
            )
            merged_r["decision_recovered"] = merged_r["decision_recovered"].astype(object).fillna(merged_r["decision_corrupted"]).astype(bool)
            _add_cost(recovered_cost, policy_cost(merged_r["decision_recovered"], merged_r["label"], station_id=merged_r["station_id"], ts=merged_r["ts"]))

    if total_rows == 0:
        return None

    flip_rate = total_flips / total_rows
    forecast_error = (sum_abs_err / n_err) if n_err else np.nan
    delta_cost = corrupted_cost["total"] - clean_cost["total"]

    recovery_rate = np.nan
    delta_cost_recovered = np.nan  # post-safeguard Delta cost, paired with delta_cost for H3 (T14)
    if do_recovery:
        delta_cost_recovered = recovered_cost["total"] - clean_cost["total"]
        gap = delta_cost
        recovery_rate = np.nan if gap == 0 else (corrupted_cost["total"] - recovered_cost["total"]) / gap
    elif is_silent:
        recovery_rate = 0.0  # unrecoverable floor, definitional (no detector exists by design)

    return {
        "experiment_id": meta["class"] + f"__i{meta['intensity_idx']}__seed{meta['seed']}",
        "class": class_name, "intensity_idx": meta["intensity_idx"], "seed": meta["seed"],
        "n_rows": total_rows, "n_flips": total_flips, "n_rows_missing_in_corrupted": n_corrupted_rows,
        "flip_rate": flip_rate, "forecast_error": forecast_error,
        "n_dispatches_clean": clean_cost["n_dispatches"], "n_dispatches_corrupted": corrupted_cost["n_dispatches"],
        "delta_cost": delta_cost, "delta_cost_recovered": delta_cost_recovered, "recovery_rate": recovery_rate,
    }


TMP_DIR = Path(__file__).resolve().parents[1] / "data" / "tmp"
CLEAN_FEAT_CACHE_DIR = TMP_DIR / "clean_feat_by_period"
PARTIAL_DIR = Path(__file__).resolve().parents[1] / "reports" / "t11_partial"


def _load_period_bounds():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from importlib import import_module
    # same integer period_id convention as 02's certify_multiday_substrate, which
    # names the clean-feature cache files - 07's own "P000" ids never match them
    # (2026-09-23: every worker silently found 0 cached periods and wrote null)
    substrate = import_module("07_multiday_substrate")
    kept = substrate.load_certified_periods()
    bounds = kept[["start", "end"]].reset_index().rename(columns={"index": "period_id"})
    # TEST periods only (methodology §4.5, fixed 2026-09-24): scoring all 62 meant ~80%
    # of every Delta-cost came from periods the model was trained or tau-tuned on
    return bounds[substrate.test_period_mask(bounds, load_frozen()[1])].reset_index(drop=True)


def build_worker_cache():
    """Scores the clean substrate ONCE per period and writes weather to disk,
    so each of the 120 worker subprocesses only ever build_features() the
    corrupted/recovered side - clean features used to be recomputed per
    (experiment, period), i.e. 120x redundant (2026-09-22 finding)."""
    print("Building clean-feature-by-period + weather cache for worker subprocesses...")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("grid", Path(__file__).resolve().parent / "02_generate_injection_grid.py")
    grid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grid)
    raw = grid.load_clean_substrate()
    clean_df, period_bounds = grid.certify_multiday_substrate(raw)  # must match what 02 built data/injected/ from
    period_bounds = period_bounds[period_bounds["period_id"].isin(_load_period_bounds()["period_id"])]  # test only
    weather = fetch_weather(raw["ts"].min().strftime("%Y-%m-%d"), raw["ts"].max().strftime("%Y-%m-%d"))
    del raw
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    weather.to_parquet(TMP_DIR / "weather.parquet", index=False)

    model, config = load_frozen()
    CLEAN_FEAT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    n_cached = 0
    for p in period_bounds.itertuples():
        out_path = CLEAN_FEAT_CACHE_DIR / f"{p.period_id}.parquet"
        if out_path.exists():  # resumable: a prior build_worker_cache() call may have been killed mid-loop
            n_cached += 1
            continue
        clean_slice = clean_df.loc[(clean_df["ts"] >= p.start) & (clean_df["ts"] <= p.end)]
        if len(clean_slice) == 0:
            continue
        clean_feat_p = score(model, config, clean_slice, weather=weather)
        clean_feat_p.to_parquet(out_path, index=False)
        n_cached += 1
    print(f"Cached {n_cached}/{len(period_bounds)} periods' clean features to {CLEAN_FEAT_CACHE_DIR}/ "
          f"+ {len(weather)} weather rows to {TMP_DIR}/weather.parquet")
    # completion marker: main() must be able to tell "cache exists but a prior
    # run was killed mid-build" apart from "cache is actually complete" - a
    # partial cache silently under-scores every experiment via evaluate_experiment's
    # own resumability (missing period files are just skipped), so this can't
    # be a directory-existence check alone.
    (CLEAN_FEAT_CACHE_DIR / "_complete").touch()


def run_worker(experiment_id):
    """Worker mode: evaluate exactly ONE experiment and exit. Run as a
    subprocess (not a function call) so the OS fully reclaims its memory on
    exit - 2026-09-22: even the per-period chunked single-process version
    still hit this machine's ~200MB ceiling via gradual fragmentation across
    thousands of small allocations over the full 120-experiment run, not any
    single big one. One process per experiment is the standard fix."""
    model, config = load_frozen()
    weather = pd.read_parquet(TMP_DIR / "weather.parquet")
    period_bounds = _load_period_bounds()
    exp_path = INJECTED_DIR / f"{experiment_id}.parquet"
    missing = [p for p in period_bounds["period_id"] if not (CLEAN_FEAT_CACHE_DIR / f"{p}.parquet").exists()]
    if missing:
        sys.exit(f"{len(missing)}/{len(period_bounds)} periods have no clean-feature cache file (e.g. {missing[:3]})")
    r = evaluate_experiment(model, config, CLEAN_FEAT_CACHE_DIR, period_bounds, exp_path, weather)
    if r is None:  # exit nonzero so main() reports it and a rerun retries it, instead of saving null as "done"
        sys.exit(f"{experiment_id}: evaluated 0 rows")
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    (PARTIAL_DIR / f"{experiment_id}.json").write_text(json.dumps(r))


def main():
    if not (CLEAN_FEAT_CACHE_DIR / "_complete").exists() or not (TMP_DIR / "weather.parquet").exists():
        build_worker_cache()
    else:
        print(f"Reusing cached clean features/weather from {TMP_DIR}/ (delete that folder to force a rebuild)")

    exp_files = sorted(INJECTED_DIR.glob("*.parquet"))
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nEvaluating {len(exp_files)} experiments, one subprocess each "
          "(resumable - already-completed ones are skipped)...")
    failed = []
    for i, exp_path in enumerate(exp_files):
        exp_id = exp_path.stem
        out_path = PARTIAL_DIR / f"{exp_id}.json"
        if out_path.exists():
            continue
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--experiment", exp_id],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            failed.append(exp_id)
            print(f"  WARNING: {exp_id} subprocess failed (exit {proc.returncode}): {proc.stderr[-500:]}")
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(exp_files)} done")
    if failed:
        print(f"\n{len(failed)} experiment(s) failed and have no result: {failed}")

    results = []
    for exp_path in exp_files:
        out_path = PARTIAL_DIR / f"{exp_path.stem}.json"
        if not out_path.exists():
            continue
        r = json.loads(out_path.read_text())
        if r:
            results.append(r)

    results_df = pd.DataFrame(results)
    reports_dir = Path(__file__).resolve().parents[1] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(reports_dir / "t11_dose_response.csv", index=False)
    print(f"\nSaved {len(results_df)} experiment results to reports/t11_dose_response.csv")

    print("\n=== Per class x intensity: mean flip_rate, delta_cost, recovery_rate (across 5 seeds) ===")
    agg = results_df.groupby(["class", "intensity_idx"]).agg(
        flip_rate=("flip_rate", "mean"), delta_cost=("delta_cost", "mean"),
        recovery_rate=("recovery_rate", "mean"), n=("seed", "count"),
    ).reset_index()
    print(agg.to_string(index=False))

    # per (class, intensity), n=5 seeds each (fixed 2026-09-24): pooling the 4 intensities
    # made the CI measure the spread BETWEEN doses, not sampling error within one - it is
    # the per-condition effect size + CI Russo asked to report as primary evidence.
    # ponytail: percentile bootstrap on n=5 is coarse (few distinct resamples); report
    # the 5 raw values alongside it in the thesis table.
    print("\n=== Bootstrap 95% CI on delta_cost per class x intensity (5 seeds each) ===")
    rng = np.random.default_rng(0)
    bootstrap_rows = []
    for (class_name, intensity_idx), group in results_df.groupby(["class", "intensity_idx"]):
        vals = group["delta_cost"].to_numpy()
        boot_means = [rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(2000)]
        lo, hi = np.percentile(boot_means, [2.5, 97.5])
        bootstrap_rows.append({"class": class_name, "intensity_idx": intensity_idx, "n": len(vals),
                               "mean_delta_cost": vals.mean(), "ci_low": lo, "ci_high": hi})
        print(f"  {class_name:16s} i{intensity_idx} mean={vals.mean():10.2f}  95% CI [{lo:10.2f}, {hi:10.2f}]  (n={len(vals)})")
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(reports_dir / "t11_bootstrap_ci.csv", index=False)

    print("\n=== Per-class recovery rate (mean +/- bootstrap 95% CI, recoverable classes only) ===")
    for class_name in ["class2_frozen", "class4_capacity", "class5_jump"]:
        vals = results_df.loc[results_df["class"] == class_name, "recovery_rate"].dropna().to_numpy()
        if len(vals) == 0:
            print(f"  {class_name:16s} no recoverable (nonzero-delta_cost) experiments in this run")
            continue
        boot_means = [rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(2000)]
        lo, hi = np.percentile(boot_means, [2.5, 97.5])
        print(f"  {class_name:16s} mean={vals.mean():.3f}  95% CI [{lo:.3f}, {hi:.3f}]  (n={len(vals)}/20 had a cost gap to recover)")
    print(f"  {'class6_silent':16s} recovery_rate=0.000 (definitional - no detector exists by design, unrecoverable floor)")

    print("\nGenerating dose-response plot...")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    for class_name, group in agg.groupby("class"):
        ax.plot(group["intensity_idx"], group["delta_cost"].clip(lower=0.01), marker="o", label=class_name)
    ax.set_yscale("log")
    ax.set_xlabel("Intensity level (0=lowest, 3=highest)")
    ax.set_ylabel("Mean Delta cost (EUR, log scale; clipped at 0.01 for negative/zero values)")
    ax.set_title("T11 dose-response: Delta cost by anomaly class and intensity")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(reports_dir / "t11_dose_response_plot.png", dpi=150)
    print(f"Saved plot to reports/t11_dose_response_plot.png")

    return results_df, agg, bootstrap_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default=None,
                         help="worker mode: evaluate this one experiment_id (a data/injected/*.parquet stem) and exit")
    args = parser.parse_args()
    if args.experiment:
        run_worker(args.experiment)
    else:
        main()
