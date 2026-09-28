"""Exposure census (thesis §5.1): how many test-window rows each corrupted dataset
actually alters or removes. Read-only over data/injected/; writes
reports/t40_exposure_test_window.csv.

Reference = class6_silent__i0__seed0: Class 6 leaves the feed columns untouched
(src/injection.py:inject_silent_offset), so its num_bikes/num_docks equal the
clean certified substrate. Rows are aligned on (station_id, ts), never by
position, because some injectors re-sort the frame. Test window = periods
50-61 (models/frozen_config.json: 33/15/12 split). Rows include unlabelled
ones: they are not scored, but they feed the lags of scored rows.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INJ = ROOT / "data" / "injected"
OUT = ROOT / "reports" / "t40_exposure_test_window.csv"
KEY = ["station_id", "ts"]
VALS = ["num_bikes_available", "num_docks_available"]


def test_rows(df):
    pid = df["period_id"].astype(str).str.extract(r"(\d+)")[0].astype(int)
    return df[pid >= 50]


def main():
    ref = test_rows(pd.read_parquet(INJ / "class6_silent__i0__seed0.parquet"))
    n_test = len(ref)
    rows = []
    for cls in ["class1_dropout", "class2_frozen", "class3_stale", "class4_capacity", "class5_jump"]:
        for i in range(4):
            for s in range(5):
                c = pd.read_parquet(INJ / f"{cls}__i{i}__seed{s}.parquet", columns=KEY + VALS)
                m = ref[KEY + VALS].merge(c, on=KEY, how="left", suffixes=("", "_c"))
                missing = m["num_bikes_available_c"].isna()
                altered = ~missing & ((m[VALS[0]] != m[VALS[0] + "_c"]) | (m[VALS[1]] != m[VALS[1] + "_c"]))
                rows.append({"class": cls, "intensity_idx": i, "seed": s, "test_rows": n_test,
                             "rows_removed_or_empty": int(missing.sum()), "rows_altered": int(altered.sum())})
    for i in range(4):
        for s in range(5):
            t = test_rows(pd.read_parquet(INJ / f"class6_silent__i{i}__seed{s}.parquet"))
            hit = t["true_available"] != t["num_bikes_available"]
            rows.append({"class": "class6_silent", "intensity_idx": i, "seed": s, "test_rows": n_test,
                         "rows_removed_or_empty": 0, "rows_altered": int(hit.sum()),
                         "stations_affected": int(t.loc[hit, "station_id"].nunique())})
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(out.groupby(["class", "intensity_idx"])[["rows_removed_or_empty", "rows_altered"]].agg(["min", "max"]))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
