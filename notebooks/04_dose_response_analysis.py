"""T11: full dose-response analysis. Runs the frozen model+tau (T8/T9) against
all 120 injected datasets (T7), computing per (class, intensity, seed):
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
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features import build_features, fetch_weather
from src.model import predict_critical
from src.costs import policy_cost, decision_flip_rate
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


def evaluate_experiment(model, config, clean_feat, exp_path, weather):
    meta = json.loads(exp_path.with_suffix(".json").read_text())
    class_name = meta["class"]
    corrupted_df = pd.read_parquet(exp_path)

    corrupted_feat = score(model, config, corrupted_df, weather=weather)
    # LEFT join, not inner: class1_dropout REMOVES rows, and an inner join would
    # silently exclude exactly those rows from evaluation - structurally hiding
    # dropout's entire effect (no data -> no dispatch decision is the real,
    # meaningful consequence, not something to drop from the comparison).
    merged = clean_feat.merge(
        corrupted_feat[["station_id", "ts", "proba", "decision"]],
        on=["station_id", "ts"], suffixes=("_clean", "_corrupted"), how="left",
    )
    if len(merged) == 0:
        return None
    missing_in_corrupted = merged["decision_corrupted"].isna()
    merged["decision_corrupted"] = merged["decision_corrupted"].astype(object).fillna(False).astype(bool)  # no data -> no dispatch possible

    clean_cost = policy_cost(merged["decision_clean"], merged["label"], station_id=merged["station_id"])
    flip_rate = decision_flip_rate(merged["decision_clean"], merged["decision_corrupted"])
    # forecast_error only meaningful where a corrupted probability actually exists
    forecast_error = float((merged.loc[~missing_in_corrupted, "proba_corrupted"]
                             - merged.loc[~missing_in_corrupted, "proba_clean"]).abs().mean())

    if class_name == "class6_silent":
        # feed-invisible by design: num_bikes_available never changes, so the model's
        # decisions/proba are IDENTICAL to clean (flip_rate/forecast_error are correctly
        # 0, not a bug) - the real cost is hidden, only visible via true_available (the
        # parallel ground-truth column inject_silent_offset adds). Build a "true_label"
        # the same way build_features builds label, but from true_available instead of
        # num_bikes_available, then cost the SAME (deceived) decisions against reality.
        HORIZON_STEPS = 120
        cdf = corrupted_df.sort_values(["station_id", "ts"]).reset_index(drop=True)
        cdf["true_critical"] = (cdf["true_available"] <= 2) | (cdf["num_docks_available"] <= 2)
        cdf["true_label"] = cdf.groupby("station_id", sort=False)["true_critical"].shift(-HORIZON_STEPS)
        merged = merged.merge(cdf[["station_id", "ts", "true_label"]], on=["station_id", "ts"], how="left")
        merged = merged.dropna(subset=["true_label"])
        corrupted_cost = policy_cost(merged["decision_corrupted"], merged["true_label"], station_id=merged["station_id"])
        clean_cost = policy_cost(merged["decision_clean"], merged["label"], station_id=merged["station_id"])
    else:
        corrupted_cost = policy_cost(merged["decision_corrupted"], merged["label"], station_id=merged["station_id"])

    delta_cost = corrupted_cost["total"] - clean_cost["total"]

    recovery_rate = np.nan
    delta_cost_recovered = np.nan  # post-safeguard Delta cost, paired with delta_cost for H3 (T14)
    if class_name in RECOVERABLE_CLASSES and class_name != "class1_dropout":
        recovered_df = apply_safeguard(corrupted_df, class_name)
        recovered_feat = score(model, config, recovered_df, weather=weather)
        merged_r = merged.merge(
            recovered_feat[["station_id", "ts", "decision"]].rename(columns={"decision": "decision_recovered"}),
            on=["station_id", "ts"], how="left",
        )
        merged_r["decision_recovered"] = merged_r["decision_recovered"].astype(object).fillna(merged_r["decision_corrupted"]).astype(bool)
        recovered_cost = policy_cost(merged_r["decision_recovered"], merged_r["label"], station_id=merged_r["station_id"])
        delta_cost_recovered = recovered_cost["total"] - clean_cost["total"]
        gap = corrupted_cost["total"] - clean_cost["total"]
        recovery_rate = np.nan if gap == 0 else (corrupted_cost["total"] - recovered_cost["total"]) / gap
    elif class_name == "class6_silent":
        recovery_rate = 0.0  # unrecoverable floor, definitional (no detector exists by design)

    return {
        "experiment_id": meta["class"] + f"__i{meta['intensity_idx']}__seed{meta['seed']}",
        "class": class_name, "intensity_idx": meta["intensity_idx"], "seed": meta["seed"],
        "n_rows": len(merged), "flip_rate": flip_rate, "forecast_error": forecast_error,
        "delta_cost": delta_cost, "delta_cost_recovered": delta_cost_recovered, "recovery_rate": recovery_rate,
    }


def main():
    print("Loading frozen model + config...")
    model, config = load_frozen()

    print("Loading clean substrate and scoring it once (reference for every comparison)...")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("grid", Path(__file__).resolve().parent / "02_generate_injection_grid.py")
    grid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grid)
    raw = grid.load_clean_substrate()
    clean_df = grid.certify_clean_substrate(raw)
    weather = fetch_weather(raw["ts"].min().strftime("%Y-%m-%d"), raw["ts"].max().strftime("%Y-%m-%d"))
    clean_feat = score(model, config, clean_df, weather=weather)
    print(f"Clean substrate scored: {len(clean_feat)} rows")

    exp_files = sorted(INJECTED_DIR.glob("*.parquet"))
    print(f"\nEvaluating {len(exp_files)} experiments...")
    results = []
    for i, exp_path in enumerate(exp_files):
        r = evaluate_experiment(model, config, clean_feat, exp_path, weather)
        if r is not None:
            results.append(r)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(exp_files)} done")

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

    print("\n=== Per-class bootstrap 95% CI on delta_cost (pooled across 4 intensities x 5 seeds = 20 draws) ===")
    rng = np.random.default_rng(0)
    bootstrap_rows = []
    for class_name, group in results_df.groupby("class"):
        vals = group["delta_cost"].to_numpy()
        boot_means = [rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(2000)]
        lo, hi = np.percentile(boot_means, [2.5, 97.5])
        bootstrap_rows.append({"class": class_name, "mean_delta_cost": vals.mean(), "ci_low": lo, "ci_high": hi})
        print(f"  {class_name:16s} mean={vals.mean():10.2f}  95% CI [{lo:10.2f}, {hi:10.2f}]  (n={len(vals)})")
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
    main()
