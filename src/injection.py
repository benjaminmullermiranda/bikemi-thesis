"""Controlled fault injectors - anomaly classes 1-6, applied at SERVING TIME only
to the pre-certified clean substrate (6 classes x 4 intensities x 5 seeds).
"""

def inject_station_dropout(df, stations, duration, seed):    raise NotImplementedError
def inject_frozen_counter(df, station, duration, seed):      raise NotImplementedError
def inject_stale_update(df, lag_s, scope, seed):             raise NotImplementedError
def inject_capacity_inconsistency(df, magnitude, seed):      raise NotImplementedError
def inject_value_jump(df, magnitude, rate, seed):            raise NotImplementedError
def inject_silent_offset(df, offset_k, share, seed):
    """Class 6: feed-invisible by design; parameters are unanchored sensitivity dims."""
    raise NotImplementedError
