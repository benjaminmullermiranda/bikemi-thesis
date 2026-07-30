"""Cost model and propagation metrics.

C_penalty = sum(critical station-hours) * C_miss,  C_miss = failed_pickups * (1-sigma) * revenue
C_transit = sum(preventive dispatches) * C_dispatch
Headline metrics: decision_flip_rate, delta_cost (per class x intensity), recovery_rate.

ponytail: REVENUE_PER_RIDE / C_DISPATCH / PICKUP_RATE_PER_HOUR are placeholders for the
T4 proof-of-concept - replace with real BikeMi tariff/dispatch figures in T10 (open
question Q6, docs/thesis_execution_plan). Swapping these three constants is all T10 needs
to change; nothing downstream depends on their values being final.
"""
import numpy as np

POLL_INTERVAL_HOURS = 60 / 3600   # 60 s poll cadence -> hours per row
REVENUE_PER_RIDE = 1.50            # EUR, placeholder
C_DISPATCH = 15.0                  # EUR per preventive dispatch, placeholder
PICKUP_RATE_PER_HOUR = 0.5         # expected failed pickups per missed critical station-hour, placeholder


def _assert_contiguous_stations(station_id):
    """Cheap guard against count_dispatch_episodes' ordering assumption: each
    station's rows must form one contiguous block, else the roll-based adjacency
    check below silently miscounts episodes. Doesn't (can't, without a ts array)
    verify chronological order *within* a station - that's still the caller's job."""
    seen, start = set(), 0
    boundaries = list(np.flatnonzero(station_id[1:] != station_id[:-1]) + 1) + [len(station_id)]
    for end in boundaries:
        sid = station_id[start]
        if sid in seen:
            raise ValueError(
                f"count_dispatch_episodes: station {sid!r} appears in more than one "
                "block - input must be sorted by (station_id, ts) or episode counts will be wrong."
            )
        seen.add(sid)
        start = end


def count_dispatch_episodes(decisions, station_id):
    """A preventive dispatch is a physical visit, not a per-poll charge: count
    contiguous True-runs per station as ONE dispatch each. `decisions` and
    `station_id` must be aligned and each station's rows already in chronological
    order (not necessarily adjacent to other stations' rows)."""
    decisions = np.asarray(decisions, dtype=bool)
    station_id = np.asarray(station_id)
    _assert_contiguous_stations(station_id)
    same_station_as_prev = station_id == np.roll(station_id, 1)
    prev_decision = np.roll(decisions, 1)
    starts_episode = decisions & ~(same_station_as_prev & prev_decision)
    starts_episode[0] = decisions[0]
    return int(starts_episode.sum())


def policy_cost(decisions, critical, station_id=None, sigma=0.5):
    """decisions, critical: same-length boolean arrays (or pandas Series), one entry
    per (station, t) row. If station_id is given (rows chronological per station),
    C_transit counts dispatch EPISODES, not raw dispatch-flagged rows. Without it,
    falls back to one dispatch per True row (only correct if each row is already
    one discrete decision, e.g. already de-duplicated per episode upstream).
    Returns {c_penalty, c_transit, total, n_dispatches}."""
    decisions = np.asarray(decisions, dtype=bool)
    critical = np.asarray(critical, dtype=bool)
    missed_station_hours = (critical & ~decisions).sum() * POLL_INTERVAL_HOURS
    c_penalty = missed_station_hours * PICKUP_RATE_PER_HOUR * (1 - sigma) * REVENUE_PER_RIDE
    n_dispatches = count_dispatch_episodes(decisions, station_id) if station_id is not None else int(decisions.sum())
    c_transit = n_dispatches * C_DISPATCH
    return {"c_penalty": c_penalty, "c_transit": c_transit, "total": c_penalty + c_transit, "n_dispatches": n_dispatches}


def decision_flip_rate(decisions_clean, decisions_corrupted):
    a = np.asarray(decisions_clean, dtype=bool)
    b = np.asarray(decisions_corrupted, dtype=bool)
    return float((a != b).mean())


def demo():
    decisions = np.array([True, False, False, True])
    critical = np.array([True, True, False, False])
    cost = policy_cost(decisions, critical)
    assert cost["c_transit"] == 2 * C_DISPATCH        # 2 dispatch-flagged rows, no station_id given
    assert cost["c_penalty"] > 0                       # 1 missed critical row

    # same 4 rows, but 2 of them are one contiguous episode at the same station
    episode_decisions = np.array([True, True, False, True])
    station_id = np.array(["s1", "s1", "s1", "s1"])
    episode_cost = policy_cost(episode_decisions, critical, station_id=station_id)
    assert episode_cost["n_dispatches"] == 2            # [True,True] run + [True] run = 2 episodes, not 3 rows

    flipped = decision_flip_rate(decisions, np.array([True, True, False, True]))
    assert flipped == 0.25                              # 1 of 4 rows flipped

    # unsorted station_id (s1 appears in two separate blocks) must raise, not silently miscount
    bad_station_id = np.array(["s1", "s2", "s1", "s2"])
    try:
        count_dispatch_episodes(np.array([True, True, True, True]), bad_station_id)
        raise AssertionError("expected ValueError on non-contiguous station_id")
    except ValueError:
        pass

    print("costs.demo: OK")


if __name__ == "__main__":
    demo()
