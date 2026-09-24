"""T8: train + freeze the forecast model (Layer 2) properly - feature engineering
including weather (Q3, resolved), fit once on clean data, freeze model + tau, and
SAVE both to disk so T9/T11 reuse this exact frozen pair across the full 120
injection-grid experiments instead of retraining per experiment.

Trains on the multi-day substrate of notebooks/07_multiday_substrate.py: every
daily period long enough to forecast in, each treated as an independent
continuous block (supervisor instruction, 14 September 2026). It replaces both
the old "train on the full gappy collection" input and the single-segment
substrate, which no longer co-exist now that the substrate IS most of the
usable collection.

The split is cut on whole periods, not on rows. A row-level quantile cut can
fall inside a period, and then the last training rows' +2h label horizon lands
in the validation window - exactly the leakage the frozen protocol
(docs/thesis/04_methodology.md §4.2) forbids. Snapping each cut forward to the
end of the period it falls in costs nothing and removes the leak entirely.
"""
import sys
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_io import load_snapshots
from src.features import build_features, fetch_weather, FEATURE_COLS, WEATHER_COLS
from src.model import train_frozen_model, predict_critical
sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module
load_certified_periods = import_module("07_multiday_substrate").load_certified_periods
from src.costs import policy_cost

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"


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

    kept = load_certified_periods()
    print(f"\n{len(kept)} certified daily periods (2026-09-19, Russo-approved) "
          f"({kept['duration_h'].sum():.1f} h over {kept['day'].nunique()} days)")

    all_feature_cols = list(FEATURE_COLS) + list(WEATHER_COLS)
    parts = []
    for i, prd in enumerate(kept.itertuples()):
        seg = raw[(raw["ts"] >= prd.start) & (raw["ts"] <= prd.end)]
        f = build_features(seg, weather=weather).dropna(subset=all_feature_cols + ["label"])
        f["period_id"] = i
        parts.append(f)
    feat = pd.concat(parts, ignore_index=True)
    feat["label"] = feat["label"].astype(bool)
    feat = feat.sort_values("ts")
    print(f"\n{len(feat)} usable rows after dropping NaN lags/weather/label "
          f"({100*len(feat)/len(raw):.1f}% of raw)")

    # Period-aligned chronological split: take the row quantiles, then push each
    # cut forward to the end of whichever period it landed in, so no period is
    # ever split across two sets and no label horizon reaches across a cut.
    period_end = feat.groupby("period_id")["ts"].max().sort_values()

    def snap(q):
        cut = feat["ts"].quantile(q)
        later = period_end[period_end >= cut]
        return later.iloc[0] if len(later) else period_end.iloc[-1]

    cut1, cut2 = snap(0.6), snap(0.8)
    test_end = feat["ts"].max()  # bound the test window explicitly - see below
    train = feat[feat["ts"] <= cut1]
    val = feat[(feat["ts"] > cut1) & (feat["ts"] <= cut2)].sort_values(["station_id", "ts"])
    test = feat[(feat["ts"] > cut2) & (feat["ts"] <= test_end)].sort_values(["station_id", "ts"])
    print(f"train={len(train)} val={len(val)} test={len(test)} "
          f"({train['period_id'].nunique()}/{val['period_id'].nunique()}/"
          f"{test['period_id'].nunique()} periods, period-aligned chronological split)")

    model = train_frozen_model(train[all_feature_cols], train["label"])

    val_proba = predict_critical(model, val[all_feature_cols])
    best_tau, best_cost = 0.5, None
    for tau in np.arange(0.05, 0.96, 0.05):
        cost = policy_cost(val_proba >= tau, val["label"], station_id=val["station_id"], ts=val["ts"])["total"]
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
        "substrate": "multi-day periods, notebooks/07_multiday_substrate.py",
        "periods_train_val_test": [int(train["period_id"].nunique()),
                                   int(val["period_id"].nunique()),
                                   int(test["period_id"].nunique())],
        # train_end/val_end/test_end together are the FROZEN split boundaries.
        # The collector runs continuously, so recomputing quantiles fresh later
        # silently shifts train/val/test membership and the reported test_auc
        # with it (measured: 0.6147 at save time -> 0.6137-0.6140 when
        # recomputed minutes later on a larger collection). Any future script
        # reproducing this split MUST reuse these three saved timestamps
        # (feat.ts <= train_end / (train_end, val_end] / (val_end, test_end])
        # rather than recomputing feat["ts"].quantile([0.6, 0.8]).
        "train_end": str(cut1),
        "val_end": str(cut2),
        "test_end": str(test_end),
        "test_auc": auc,
        "test_corr_bikes_lag1_label": corr,
        "weather_source": "Open-Meteo archive API, Milan (45.4642N, 9.1900E)",
    }, indent=2))
    print(f"\nSaved frozen model + config to {MODEL_DIR}/")
    return auc, best_tau


if __name__ == "__main__":
    main()
