"""T4 proof-of-concept: raw -> predict -> decide -> cost, end-to-end, on one
anomaly class (5: implausible value jump) at one intensity, on the data
collected so far. This is a go/no-go checkpoint, not the frozen T6-T11
methodology: chronological train/val/test split, tau calibrated once on
clean validation data (cost-minimisation), model + tau frozen, then the
SAME frozen pipeline is re-run on class-5-corrupted test-window features.

Ground truth for cost/flip-rate evaluation is always the TRUE (uncorrupted)
future critical state - injection corrupts what the model SEES (recent
lag features), never the outcome being predicted.
"""
import gzip
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features import build_features, FEATURE_COLS
from src.model import train_frozen_model, predict_critical
from src.injection import inject_value_jump
from src.costs import policy_cost, decision_flip_rate

INJECTION_MAGNITUDE = 10   # bikes, one intensity level for this POC
INJECTION_RATE = 0.05      # fraction of test-window rows hit
INJECTION_SEED = 1


def load_snapshots(pattern="data/raw/*.json.gz"):
    rows = []
    seen_last_updated = set()
    for f in sorted(glob.glob(pattern)):
        try:
            d = json.load(gzip.open(f, "rt", encoding="utf-8"))
        except Exception:
            continue
        last_updated = d["last_updated"]
        if last_updated in seen_last_updated:
            # upstream feed hadn't updated since the previous poll (a real, naturally
            # occurring stale-feed event) - keep only the first observation of it
            continue
        seen_last_updated.add(last_updated)
        ts = pd.Timestamp(last_updated, unit="s", tz="UTC")
        for s in d["data"]["stations"]:
            rows.append((s["station_id"], ts, s["num_bikes_available"], s["num_docks_available"]))
    return pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])


def main():
    print("Loading raw snapshots...")
    raw = load_snapshots()
    print(f"{len(raw)} rows, {raw['station_id'].nunique()} stations, "
          f"{raw['ts'].min()} to {raw['ts'].max()}")

    feat = build_features(raw).dropna(subset=list(FEATURE_COLS) + ["label"])
    feat["label"] = feat["label"].astype(bool)
    feat = feat.sort_values("ts")

    cut1, cut2 = feat["ts"].quantile([0.6, 0.8])
    train = feat[feat["ts"] <= cut1]
    # dispatch-episode counting needs each station's rows in chronological order
    val = feat[(feat["ts"] > cut1) & (feat["ts"] <= cut2)].sort_values(["station_id", "ts"])
    test = feat[feat["ts"] > cut2].sort_values(["station_id", "ts"])
    print(f"train={len(train)} val={len(val)} test={len(test)} rows (chronological split)")

    model = train_frozen_model(train[FEATURE_COLS], train["label"])

    # tau: cost-minimisation grid search on clean validation data, then frozen (Q4)
    val_proba = predict_critical(model, val[FEATURE_COLS])
    best_tau, best_cost = 0.5, None
    for tau in np.arange(0.05, 0.96, 0.05):
        cost = policy_cost(val_proba >= tau, val["label"], station_id=val["station_id"])["total"]
        if best_cost is None or cost < best_cost:
            best_tau, best_cost = tau, cost
    print(f"Frozen tau = {best_tau:.2f} (validation cost {best_cost:.2f})")

    # corrupt only the test window's current values (class 5), rebuild lag features
    test_start = test["ts"].min()
    corrupted_raw = pd.concat([
        raw[raw["ts"] < test_start],
        inject_value_jump(raw[raw["ts"] >= test_start], INJECTION_MAGNITUDE, INJECTION_RATE, INJECTION_SEED),
    ])
    corrupted_feat = build_features(corrupted_raw)[["station_id", "ts"] + list(FEATURE_COLS)]

    merged = test.merge(corrupted_feat, on=["station_id", "ts"], suffixes=("", "_corrupted"))
    merged = merged.sort_values(["station_id", "ts"])
    corrupted_cols = [f"{c}_corrupted" for c in FEATURE_COLS]

    clean_proba = predict_critical(model, merged[FEATURE_COLS])
    corrupted_X = merged[corrupted_cols].rename(columns=dict(zip(corrupted_cols, FEATURE_COLS)))
    corrupted_proba = predict_critical(model, corrupted_X)
    clean_decisions = clean_proba >= best_tau
    corrupted_decisions = corrupted_proba >= best_tau

    clean_cost = policy_cost(clean_decisions, merged["label"], station_id=merged["station_id"])
    corrupted_cost = policy_cost(corrupted_decisions, merged["label"], station_id=merged["station_id"])
    flip_rate = decision_flip_rate(clean_decisions, corrupted_decisions)
    n_flips = int((clean_decisions != corrupted_decisions).sum())
    delta_cost = corrupted_cost["total"] - clean_cost["total"]

    print(f"\nClean cost:     {clean_cost}")
    print(f"Corrupted cost: {corrupted_cost}  (class 5, magnitude={INJECTION_MAGNITUDE}, rate={INJECTION_RATE})")
    print(f"Decision-flip rate: {flip_rate:.6f}  ({n_flips} / {len(merged)} rows)")
    print(f"Delta cost: {delta_cost:.2f}")

    if best_tau >= 0.8:
        print(
            "\nNOTE: the cost-minimising tau converged to 'never dispatch' given the "
            "current placeholder cost constants (C_DISPATCH dominates total foregone "
            "revenue at this window's scale) - a real Q6/T10 finding, not a pipeline bug. "
            "Diagnostic run at a fixed non-degenerate tau=0.5, to confirm the chain "
            "still propagates corruption into decisions correctly:"
        )
        diag_tau = 0.5
        diag_clean = predict_critical(model, merged[FEATURE_COLS]) >= diag_tau
        diag_corrupted = predict_critical(model, corrupted_X) >= diag_tau
        diag_clean_cost = policy_cost(diag_clean, merged["label"], station_id=merged["station_id"])
        diag_corrupted_cost = policy_cost(diag_corrupted, merged["label"], station_id=merged["station_id"])
        diag_flip = decision_flip_rate(diag_clean, diag_corrupted)
        diag_n_flips = int((diag_clean != diag_corrupted).sum())
        print(f"  tau={diag_tau}: clean={diag_clean_cost}")
        print(f"  tau={diag_tau}: corrupted={diag_corrupted_cost}")
        print(f"  tau={diag_tau}: flip_rate={diag_flip:.6f} ({diag_n_flips} / {len(merged)} rows) "
              f"delta_cost={diag_corrupted_cost['total'] - diag_clean_cost['total']:.2f}")

    return delta_cost


if __name__ == "__main__":
    main()
