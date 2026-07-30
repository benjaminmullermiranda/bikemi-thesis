"""Feature building for the frozen forecast model:
availability lags, hour/weekday, basic weather. All features use info at time t only.

Weather (Q3, resolved for T8): Milan hourly temperature + precipitation from
Open-Meteo's free historical archive API (no key required). Optional - pass
`weather=None` (default) to get exactly T4's original lag/hour/weekday-only
features; existing callers are unaffected.
"""
import pandas as pd

LAG_STEPS = (1, 2, 5, 15)   # polls back, ~1/2/5/15 min at 60 s poll cadence
HORIZON_STEPS = 120         # +2h ahead at 60 s poll cadence
POLL_SECONDS = 60
GAP_TOLERANCE = 1.5         # invalidate a lag/label if its actual elapsed time exceeds
                            # this multiple of nominal (real collection gaps happen;
                            # shift() is positional and silently ignores them otherwise)

MILAN_LAT, MILAN_LON = 45.4642, 9.1900

FEATURE_COLS = (
    [f"bikes_lag{lag}" for lag in LAG_STEPS]
    + [f"docks_lag{lag}" for lag in LAG_STEPS]
    + ["hour", "weekday"]
)
WEATHER_COLS = ["temp_c", "precip_mm"]


def fetch_weather(start_date, end_date, lat=MILAN_LAT, lon=MILAN_LON):
    """Hourly temperature (C) + precipitation (mm) for Milan, from Open-Meteo's
    free archive API. start_date/end_date: 'YYYY-MM-DD' strings (UTC calendar days).
    Returns a DataFrame with columns hour_ts (tz-aware UTC), temp_c, precip_mm."""
    import requests

    url = (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&hourly=temperature_2m,precipitation&timezone=UTC"
    )
    hourly = requests.get(url, timeout=30).json()["hourly"]
    return pd.DataFrame({
        "hour_ts": pd.to_datetime(hourly["time"], utc=True),
        "temp_c": hourly["temperature_2m"],
        "precip_mm": hourly["precipitation"],
    })


def build_features(df, weather=None):
    """df: tidy long frame, one row per (station_id, ts).
    Required columns: station_id, ts (tz-aware datetime), num_bikes_available, num_docks_available.
    weather: optional DataFrame from fetch_weather() - if given, temp_c/precip_mm
    are joined by hour-truncated timestamp and appended (see WEATHER_COLS).
    Returns a copy with lag_*, hour, weekday, critical, and label columns appended.
    label(t) = critical at t + HORIZON_STEPS (the frozen model's prediction target).

    Lags/label are computed positionally (shift by row count) but then invalidated
    (set to NaN) whenever the actual elapsed time to that row deviates too far from
    the nominal cadence - a collection gap means "lag1" isn't really 1 poll ago."""
    df = df.sort_values(["station_id", "ts"]).reset_index(drop=True)
    df["critical"] = (df["num_bikes_available"] <= 2) | (df["num_docks_available"] <= 2)

    grouped = df.groupby("station_id", sort=False)
    for lag in LAG_STEPS:
        elapsed = (df["ts"] - grouped["ts"].shift(lag)).dt.total_seconds()
        valid = elapsed <= lag * POLL_SECONDS * GAP_TOLERANCE
        df[f"bikes_lag{lag}"] = grouped["num_bikes_available"].shift(lag).where(valid)
        df[f"docks_lag{lag}"] = grouped["num_docks_available"].shift(lag).where(valid)

    df["hour"] = df["ts"].dt.hour
    df["weekday"] = df["ts"].dt.weekday

    if weather is not None:
        df["hour_ts"] = df["ts"].dt.floor("h")
        df = df.merge(weather, on="hour_ts", how="left").drop(columns="hour_ts")

    label_elapsed = (grouped["ts"].shift(-HORIZON_STEPS) - df["ts"]).dt.total_seconds()
    label_valid = label_elapsed <= HORIZON_STEPS * POLL_SECONDS * GAP_TOLERANCE
    df["label"] = grouped["critical"].shift(-HORIZON_STEPS).where(label_valid)
    return df


def demo():
    import pandas as pd
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows, ts = [], start
    for i in range(200):
        rows.append(("s1", ts, max(0, 10 - i % 20), 5 + i % 20))
        ts += timedelta(hours=5) if i == 50 else timedelta(minutes=1)  # one big gap after row 50
    df = pd.DataFrame(rows, columns=["station_id", "ts", "num_bikes_available", "num_docks_available"])
    feat = build_features(df)

    assert list(feat.columns[:2]) == ["station_id", "ts"]
    assert set(FEATURE_COLS).issubset(feat.columns)
    assert feat["bikes_lag1"].isna().sum() == 2            # 1 edge row + 1 row spanning the 5h gap
    assert pd.isna(feat.loc[51, "bikes_lag1"])              # row right after the gap: lag1 invalidated
    assert not pd.isna(feat.loc[100, "bikes_lag1"])         # far from the gap: lag1 still valid
    assert pd.isna(feat.loc[45, "label"])                    # its +2h horizon window crosses the gap
    assert not pd.isna(feat.loc[60, "label"])                 # both row 60 and its horizon (row 180) are post-gap

    # weather join (synthetic, offline - the live fetch_weather() network call is
    # exercised for real in notebooks/03_train_frozen_model.py, not here)
    weather = pd.DataFrame({
        "hour_ts": [start, start + timedelta(hours=5)],
        "temp_c": [20.0, 21.0],
        "precip_mm": [0.0, 0.5],
    })
    feat_w = build_features(df, weather=weather)
    assert set(WEATHER_COLS).issubset(feat_w.columns)
    assert feat_w.loc[0, "temp_c"] == 20.0                    # row 0 (hour 0) gets that hour's weather
    assert feat_w.loc[51, "temp_c"] == 21.0                   # row 51 (hour 5, post-gap) gets hour 5's weather
    assert build_features(df)["label"].equals(feat_w["label"])  # weather doesn't change labels
    print("features.demo: OK")


if __name__ == "__main__":
    demo()
