"""Safeguard layer - detectors for anomaly classes 1-5 (docs/thesis_outline.md, taxonomy).

Class 6 (silent misreporting) has NO detector BY DESIGN: it is feed-invisible,
which is exactly why it defines the 'unrecoverable floor' in the thesis.
Each detector takes a tidy DataFrame of observations and returns boolean flags.
"""

def detect_station_dropout(df, registry):
    """Class 1 (completeness): stations in `registry` absent from the feed window."""
    raise NotImplementedError

def detect_frozen_counter(df, window="60min"):
    """Class 2 (accuracy/timeliness): zero variance in active hours + stalled last_reported."""
    raise NotImplementedError

def detect_stale_update(df, max_age_s=180):
    """Class 3 (timeliness): now - last_reported beyond threshold."""
    raise NotImplementedError

def detect_capacity_inconsistency(df, capacities):
    """Class 4 (consistency): bikes + docks vs declared capacity rules."""
    raise NotImplementedError

def detect_implausible_jump(df, max_flow_per_min=1.0):
    """Class 5 (validity): |delta bikes| beyond plausible flow per interval."""
    raise NotImplementedError
