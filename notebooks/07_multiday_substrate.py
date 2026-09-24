"""T38: multi-day substrate selection and pre-experiment census.

Supersedes the single-segment substrate of notebooks/02_generate_injection_grid.py
(`certify_clean_substrate`), which kept only the longest continuous run in the whole
collection (8.5 h, 9 August). Supervisor instruction of 14 September 2026: use the
~8 h of valid data available on each day and combine all days, with each day treated
as an independent continuous period so that lags and forecast horizons never cross
the gap between consecutive days.

Nothing about the frozen design changes here. The gap rule (no gap over MAX_GAP_S
between consecutive polls), the Class-5 exclusion, and the Class-2 count-but-keep
rule are exactly the ones frozen on 8 August; the only change is that the procedure
now returns every qualifying period instead of the single longest one.

Independence is enforced twice, belt and braces: features are built per period, and
src/features.py additionally invalidates any lag or label whose real elapsed time
exceeds GAP_TOLERANCE x nominal, so a cross-period lag could not survive either way.

Outputs (reports/):
  t38_daily_periods.csv        one row per retained period
  t38_substrate_summary.json   the census numbers reported to the supervisor
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_io import load_snapshots
from src.features import build_features, FEATURE_COLS, LAG_STEPS, HORIZON_STEPS, POLL_SECONDS
from src.validation import detect_implausible_jump, detect_frozen_counter

MAX_GAP_S = 120                      # frozen continuity rule, unchanged
# A period shorter than (longest lag + forecast horizon) cannot yield a single row
# with complete features AND a valid label, so it contributes nothing and is dropped.
MIN_PERIOD_S = (max(LAG_STEPS) + HORIZON_STEPS) * POLL_SECONDS   # 135 min
REPORTS = Path(__file__).resolve().parents[1] / "reports"


def load_certified_periods(path=None):
    """Loads the exact 62-period substrate certified 2026-09-19 and approved by
    Prof. Russo (email received 2026-09-22, replying to
    docs/outbox/2026-09-19_russo_substrate_summary.md) from t38_daily_periods.csv,
    instead of recomputing find_periods() against whatever the collector has
    produced since. The collector kept running past that approval (still active
    as of this loader's introduction) - a fresh recompute would silently grow
    the substrate past the numbers Russo actually reviewed and signed off on
    (confirmed 2026-09-22: 63 periods/255.2h live vs the certified 62/251.5h).
    Re-certifying to a larger substrate is a deliberate future step (get
    Russo's OK on new numbers first), never an accidental side effect of a
    later script just loading more raw files than existed on 2026-09-19."""
    path = Path(path) if path else REPORTS / "t38_daily_periods.csv"
    df = pd.read_csv(path)
    df["start"] = pd.to_datetime(df["start_utc"], utc=True)
    df["end"] = pd.to_datetime(df["end_utc"], utc=True)
    df["day"] = pd.to_datetime(df["day"]).dt.date
    df["retained"] = True
    return df[["period_id", "day", "start", "end", "duration_h", "retained"]]


def test_period_mask(periods, config):
    """True for the frozen TEST periods only: start inside (val_end, test_end]
    of models/frozen_config.json. Methodology §4.5: injection and evaluation
    run on these only - train/val periods are never corrupted or scored.
    On the 2026-09-22 split this is 12 periods (row positions 50-61)."""
    val_end, test_end = pd.Timestamp(config["val_end"]), pd.Timestamp(config["test_end"])
    mask = (periods["start"] > val_end) & (periods["start"] <= test_end)
    n_test = config["periods_train_val_test"][2]
    assert mask.sum() == n_test, f"{mask.sum()} test periods, frozen config says {n_test}"
    return mask


def find_periods(raw, max_gap_s=MAX_GAP_S, min_period_s=MIN_PERIOD_S):
    """Every maximal run of polls with no gap over max_gap_s, long enough to be
    forecastable. Returns a DataFrame of candidate periods with a `retained` flag,
    so dropped ones are counted rather than silently disappearing."""
    ts = pd.Series(np.sort(raw["ts"].unique()))
    gaps_s = ts.diff().dt.total_seconds().to_numpy()[1:]
    breaks = np.flatnonzero(gaps_s > max_gap_s)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [len(ts) - 1]))
    periods = pd.DataFrame({"start": ts.to_numpy()[starts], "end": ts.to_numpy()[ends]})
    periods["duration_h"] = (periods["end"] - periods["start"]).dt.total_seconds() / 3600
    periods["day"] = periods["start"].dt.tz_convert("UTC").dt.date
    periods["retained"] = periods["duration_h"] * 3600 >= min_period_s
    return periods


def critical_station_hours(df):
    """Station-hours spent in critical state. Each observation is credited with the
    real time until that station's next observation inside the same period, capped at
    MAX_GAP_S so a boundary row cannot claim more than one poll interval of exposure.
    Reported alongside the naive count/60 because the two answer the same question
    under different assumptions about what a single poll represents."""
    df = df.sort_values(["period_id", "station_id", "ts"])
    nxt = df.groupby(["period_id", "station_id"], sort=False)["ts"].shift(-1)
    dwell_s = (nxt - df["ts"]).dt.total_seconds().clip(upper=MAX_GAP_S)
    dwell_s = dwell_s.fillna(POLL_SECONDS)          # last row of a period: one nominal interval
    return float(dwell_s[df["critical"].to_numpy()].sum() / 3600)


def critical_episodes(df):
    """Contiguous runs of critical state per (period, station). Counts distinct
    critical situations, which is what "too few critical situations" is really about:
    120 consecutive critical polls at one station is one situation, not 120."""
    df = df.sort_values(["period_id", "station_id", "ts"])
    crit = df["critical"].to_numpy()
    key = (df["period_id"].astype(str) + "|" + df["station_id"].astype(str)).to_numpy()
    new_group = np.concatenate(([True], key[1:] != key[:-1]))
    prev_crit = np.concatenate(([False], crit[:-1]))
    starts = crit & (new_group | ~prev_crit)
    return int(starts.sum())


def main():
    print("Loading raw collection...")
    raw = load_snapshots()
    print("  {:,} station-observations, {:,} distinct polls, {} stations".format(
        len(raw), raw["ts"].nunique(), raw["station_id"].nunique()))

    periods = find_periods(raw)
    kept = periods[periods["retained"]].reset_index(drop=True)
    kept["period_id"] = ["P{:03d}".format(i) for i in range(len(kept))]
    dropped_h = periods.loc[~periods["retained"], "duration_h"].sum()
    print("\n{} continuous segments found; {} retained (>= {:.2f} h), {} too short to "
          "forecast in (their combined length: {:.1f} h)".format(
              len(periods), len(kept), MIN_PERIOD_S / 3600,
              len(periods) - len(kept), dropped_h))

    rows, per_period = [], []
    for p in kept.itertuples():
        seg = raw[(raw["ts"] >= p.start) & (raw["ts"] <= p.end)]

        # Frozen certification rules, applied per period exactly as in notebooks/02.
        jumps = detect_implausible_jump(seg, max_flow_per_min=1.0)
        n_jump = int(jumps["jump_flag"].sum())
        clean = jumps.loc[~jumps["jump_flag"], ["station_id", "ts",
                                                "num_bikes_available", "num_docks_available"]]
        n_frozen = int(detect_frozen_counter(clean, window="60min")["frozen"].sum())

        feat = build_features(clean)
        feat["period_id"] = p.period_id
        forecastable = feat[FEATURE_COLS].notna().all(axis=1) & feat["label"].notna()

        per_period.append({
            "period_id": p.period_id,
            "day": str(p.day),
            "start_utc": str(p.start),
            "end_utc": str(p.end),
            "duration_h": round(p.duration_h, 3),
            "polls": int(seg["ts"].nunique()),
            "stations": int(seg["station_id"].nunique()),
            "observations": int(len(seg)),
            "jump_rows_excluded": n_jump,
            "frozen_rows_flagged_kept": n_frozen,
            "observations_clean": int(len(clean)),
            "observations_forecastable": int(forecastable.sum()),
            "critical_observations": int(feat["critical"].sum()),
            "label_positive": int(feat.loc[forecastable, "label"].sum()),
        })
        rows.append(feat.loc[:, ["period_id", "station_id", "ts", "critical"]])
        print("  {} {} {:5.2f} h  obs={:>7,}  forecastable={:>7,}  crit={:>6,}".format(
            p.period_id, p.day, p.duration_h, len(seg),
            int(forecastable.sum()), int(feat["critical"].sum())))

    allrows = pd.concat(rows, ignore_index=True)
    pp = pd.DataFrame(per_period)
    REPORTS.mkdir(exist_ok=True)
    pp.to_csv(REPORTS / "t38_daily_periods.csv", index=False)

    by_day = pp.groupby("day")["duration_h"].agg(["count", "sum"])
    summary = {
        "generated": str(pd.Timestamp.utcnow()),
        "rule": {"max_gap_s": MAX_GAP_S, "min_period_s": MIN_PERIOD_S,
                 "critical_def": "num_bikes_available <= 2 or num_docks_available <= 2",
                 "horizon_steps": HORIZON_STEPS, "poll_seconds": POLL_SECONDS},
        "collection_window": {"first_poll": str(raw["ts"].min()), "last_poll": str(raw["ts"].max())},
        "segments_found": int(len(periods)),
        "periods_retained": int(len(kept)),
        "periods_dropped_too_short": int(len(periods) - len(kept)),
        "distinct_days": int(pp["day"].nunique()),
        "days_with_multiple_periods": int((by_day["count"] > 1).sum()),
        "duration_h": {"total": round(float(pp["duration_h"].sum()), 2),
                       "mean": round(float(pp["duration_h"].mean()), 2),
                       "median": round(float(pp["duration_h"].median()), 2),
                       "min": round(float(pp["duration_h"].min()), 2),
                       "max": round(float(pp["duration_h"].max()), 2)},
        "per_day_total_h": {"mean": round(float(by_day["sum"].mean()), 2),
                            "min": round(float(by_day["sum"].min()), 2),
                            "max": round(float(by_day["sum"].max()), 2)},
        "observations": int(pp["observations"].sum()),
        "observations_clean": int(pp["observations_clean"].sum()),
        "jump_rows_excluded": int(pp["jump_rows_excluded"].sum()),
        "frozen_rows_flagged_kept": int(pp["frozen_rows_flagged_kept"].sum()),
        "observations_forecastable": int(pp["observations_forecastable"].sum()),
        "critical_observations": int(pp["critical_observations"].sum()),
        "critical_share_of_observations": round(
            float(pp["critical_observations"].sum()) / float(pp["observations_clean"].sum()), 4),
        "critical_station_hours": round(critical_station_hours(allrows), 1),
        "critical_station_hours_naive": round(float(pp["critical_observations"].sum()) / 60, 1),
        "critical_episodes": critical_episodes(allrows),
        "stations_ever_critical": int(allrows.loc[allrows["critical"], "station_id"].nunique()),
        "label_positive": int(pp["label_positive"].sum()),
        "label_positive_rate": round(
            float(pp["label_positive"].sum()) / float(pp["observations_forecastable"].sum()), 4),
    }
    (REPORTS / "t38_substrate_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2))
    print("\nWrote reports/t38_daily_periods.csv and reports/t38_substrate_summary.json")


def demo():
    """Synthetic two-day check: the segmenter must find one period per day, drop a
    stub period, and never let a lag or label cross the overnight gap."""
    start = pd.Timestamp("2026-01-01 08:00", tz="UTC")
    rows = []
    for day in range(2):
        base = start + pd.Timedelta(days=day)
        for i in range(300):                       # 5 h at 60 s
            for sid in ("s1", "s2"):
                rows.append((sid, base + pd.Timedelta(minutes=i), i % 7, 20 - i % 7))
    stub = start + pd.Timedelta(days=2)            # 10 min: below MIN_PERIOD_S
    for i in range(10):
        rows.append(("s1", stub + pd.Timedelta(minutes=i), 3, 17))
    raw = pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available",
                                      "num_docks_available"])

    periods = find_periods(raw)
    assert len(periods) == 3, periods
    assert periods["retained"].tolist() == [True, True, False]

    kept = periods[periods["retained"]].reset_index(drop=True)
    feats = []
    for i, p in enumerate(kept.itertuples()):
        seg = raw[(raw["ts"] >= p.start) & (raw["ts"] <= p.end)]
        f = build_features(seg)
        f["period_id"] = "P{:03d}".format(i)
        feats.append(f)
    allf = pd.concat(feats, ignore_index=True)

    # no lag or label may reference the other day
    for lag in LAG_STEPS:
        first = (allf[allf["period_id"] == "P001"].sort_values(["station_id", "ts"])
                 .groupby("station_id").head(lag))
        assert first["bikes_lag{}".format(lag)].isna().all(), "lag {} crossed the day gap".format(lag)
    last = (allf[allf["period_id"] == "P000"].sort_values(["station_id", "ts"])
            .groupby("station_id").tail(HORIZON_STEPS))
    assert last["label"].isna().all(), "label crossed the day gap"

    sub = allf[["period_id", "station_id", "ts", "critical"]]
    ch = critical_station_hours(sub)
    assert 0 < ch < len(allf) / 60, ch
    assert critical_episodes(sub) > 0
    print("07_multiday_substrate.demo: OK")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
