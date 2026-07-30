"""T8: train + freeze the forecast model (Layer 2) properly - feature engineering
including weather (Q3, resolved), fit once on clean data, freeze model + tau, and
SAVE both to disk so T9/T11 reuse this exact frozen pair across the full 120
injection-grid experiments instead of retraining per experiment.

Trains on the FULL collection (gap-tolerant, per src/features.py), not the T7
certified 6.2h substrate - that smaller substrate is specifically for injection
(docs/thesis_outline.md §4); the frozen model should see as much real, varied
operating condition as possible.
"""
import sys
import glob
import gzip
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.features import build_features, fetch_weather, FEATURE_COLS, WEATHER_COLS
from src.model import train_frozen_model, predict_critical
from src.costs import policy_cost

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"


def load_snapshots(pattern="data/raw/*.json.gz"):
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


def main():
    print("Loading raw collection...")
    raw = load_snapshots()
    print(f"{len(raw)} rows, {raw['station_id'].nunique()} stations, "
          f"{raw['ts'].min()} to {raw['ts'].max()}")

    print("\nFetching weather (Milan, Open-Meteo archive API)...")
    start_date = raw["ts"].min().strftime("%Y-%m-%d")
    end_date = raw["ts"].max().strftime("%Y-%m-%d")
    weather = fetch_weather(start_date, end_date)
    print(f"{len(weather)} hourly weather rows, {start_date} to {end_date}")

    all_feature_cols = list(FEATURE_COLS) + list(WEATHER_COLS)
    feat = build_features(raw, weather=weather).dropna(subset=all_feature_cols + ["label"])
    feat["label"] = feat["label"].astype(bool)
    feat = feat.sort_values("ts")
    print(f"\n{len(feat)} usable rows after dropping NaN lags/weather/label "
          f"({100*len(feat)/len(raw):.1f}% of raw)")

    cut1, cut2 = feat["ts"].quantile([0.6, 0.8])
    train = feat[feat["ts"] <= cut1]
    val = feat[(feat["ts"] > cut1) & (feat["ts"] <= cut2)].sort_values(["station_id", "ts"])
    test = feat[feat["ts"] > cut2].sort_values(["station_id", "ts"])
    print(f"train={len(train)} val={len(val)} test={len(test)} (chronological split)")

    model = train_frozen_model(train[all_feature_cols], train["label"])

    val_proba = predict_critical(model, val[all_feature_cols])
    best_tau, best_cost = 0.5, None
    for tau in np.arange(0.05, 0.96, 0.05):
        cost = policy_cost(val_proba >= tau, val["label"], station_id=val["station_id"])["total"]
        if best_cost is None or cost < best_cost:
            best_tau, best_cost = float(tau), cost
    print(f"\nFrozen tau = {best_tau:.2f} (validation cost {best_cost:.2f})")

    test_proba = predict_critical(model, test[all_feature_cols])
    auc = roc_auc_score(test["label"], test_proba)
    corr = np.corrcoef(test["bikes_lag1"], test["label"].astype(int))[0, 1]
    print(f"\nHeld-out test AUC: {auc:.4f}  (0.5=none, 1.0=perfect)")
    print(f"corr(bikes_lag1, label): {corr:.4f}")

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / "frozen_model.joblib")
    (MODEL_DIR / "frozen_config.json").write_text(json.dumps({
        "tau": best_tau,
        "feature_cols": all_feature_cols,
        "trained_on_rows": len(train),
        "train_end": str(cut1),
        "val_end": str(cut2),
        "test_auc": auc,
        "test_corr_bikes_lag1_label": corr,
        "weather_source": "Open-Meteo archive API, Milan (45.4642N, 9.1900E)",
    }, indent=2))
    print(f"\nSaved frozen model + config to {MODEL_DIR}/")
    return auc, best_tau


if __name__ == "__main__":
    main()
