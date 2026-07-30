"""Controlled fault injectors - anomaly classes 1-6, applied at SERVING TIME only
to the pre-certified clean substrate (6 classes x 4 intensities x 5 seeds).
"""
import numpy as np

def inject_station_dropout(df, stations, duration, seed):    raise NotImplementedError
def inject_frozen_counter(df, station, duration, seed):      raise NotImplementedError
def inject_stale_update(df, lag_s, scope, seed):             raise NotImplementedError
def inject_capacity_inconsistency(df, magnitude, seed):      raise NotImplementedError


def inject_value_jump(df, magnitude, rate, seed):
    """Class 5 (validity): at a `rate` fraction of rows, replace num_bikes_available
    with an implausible +/-magnitude jump, clipped to [0, capacity]. num_docks_available
    is adjusted to keep bikes+docks = capacity (capacity itself is never corrupted)."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    hit = rng.random(len(out)) < rate
    jump = rng.choice([-1, 1], size=len(out)) * magnitude
    capacity = out["num_bikes_available"] + out["num_docks_available"]
    jumped_bikes = (out["num_bikes_available"] + jump).clip(lower=0)
    jumped_bikes = np.minimum(jumped_bikes, capacity)
    out.loc[hit, "num_bikes_available"] = jumped_bikes[hit]
    out.loc[hit, "num_docks_available"] = (capacity - out["num_bikes_available"])[hit]
    return out


def inject_silent_offset(df, offset_k, share, seed):
    """Class 6: feed-invisible by design; parameters are unanchored sensitivity dims."""
    raise NotImplementedError


def demo():
    import pandas as pd

    df = pd.DataFrame({
        "num_bikes_available": [10, 5, 0, 20],
        "num_docks_available": [10, 15, 20, 0],
    })
    out = inject_value_jump(df, magnitude=100, rate=1.0, seed=0)
    capacity = df["num_bikes_available"] + df["num_docks_available"]
    out_capacity = out["num_bikes_available"] + out["num_docks_available"]
    assert (out_capacity == capacity).all()             # capacity conserved
    assert (out["num_bikes_available"] >= 0).all()
    assert (out["num_bikes_available"] <= capacity).all()
    assert (out["num_bikes_available"] != df["num_bikes_available"]).any()  # something changed
    print("injection.demo: OK")


if __name__ == "__main__":
    demo()
