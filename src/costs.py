"""Cost model and propagation metrics (T10, Q6 resolved).

C_penalty = sum(critical station-hours) * C_miss,  C_miss = failed_pickups * (1-sigma) * revenue
C_transit = sum(preventive dispatches) * C_dispatch
Headline metrics: decision_flip_rate, delta_cost (per class x intensity), recovery_rate.

Every parameter below is swept low/mid/high (docs/thesis_outline.md §7), not a
single guessed constant. Sourcing, per parameter:

- revenue_per_ride: BikeMi's real published usage tariffs (bikemi.com/compra,
  fetched 2026-07-30). Classic bike is FREE for the first 30 min, then EUR 0.50
  per additional 30-min block up to the 2h max. Most short trips generate ZERO
  direct usage revenue - "low"=0.0 reflects that reality rather than assuming
  every ride is billable; "mid"=0.50 (one increment over); "high"=1.50 (a
  longer ride, several increments, or an e-bike trip).
- pickup_rate_per_hour: this project's OWN collected data. Computed as
  departures (net bike-count decreases) per station-hour, restricted to hours
  a station was never critical (17,706 of 20,800 station-hours qualified) -
  median=1.0, mean=1.94, p75=3.0. Matches the outline's own suggested sourcing
  ("pickup rate from departure rates in comparable non-empty periods").
- c_dispatch: NOT publicly sourced. Searched bike-share rebalancing literature;
  found none isolating a per-stop EUR figure (transportation costs are
  reported per-km, not per-stop; Denver B-Cycle's $1.50/trip figure, the one
  concrete number found, is a TOTAL marginal cost across rebalancing+support+
  wear+fees combined, from a 2016 US system - not isolable or transferable to
  2026 Milan). Documented estimate only: a ~15-20 min stop's van+driver cost
  under Milan urban logistics rates.
- sigma (substitution share): per docs/thesis_outline.md §7's own stated sweep.
"""
import numpy as np
import pandas as pd

POLL_INTERVAL_HOURS = 60 / 3600   # 60 s poll cadence -> hours per row

REVENUE_PER_RIDE_SCENARIOS = {"low": 0.0, "mid": 0.50, "high": 1.50}       # EUR/ride, sourced
PICKUP_RATE_PER_HOUR_SCENARIOS = {"low": 1.0, "mid": 1.94, "high": 3.0}    # sourced from own data
C_DISPATCH_SCENARIOS = {"low": 10.0, "mid": 15.0, "high": 25.0}            # EUR/dispatch, estimate
SIGMA_SCENARIOS = {"low": 0.2, "mid": 0.5, "high": 0.8}                    # per outline §7

# module-level defaults = mid scenario, kept for backward compatibility with
# existing callers that don't pass explicit cost parameters
REVENUE_PER_RIDE = REVENUE_PER_RIDE_SCENARIOS["mid"]
C_DISPATCH = C_DISPATCH_SCENARIOS["mid"]
PICKUP_RATE_PER_HOUR = PICKUP_RATE_PER_HOUR_SCENARIOS["mid"]


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


def count_dispatch_episodes(decisions, station_id, ts=None, max_gap_s=120):
    """A preventive dispatch is a physical visit, not a per-poll charge: count
    contiguous True-runs per station as ONE dispatch each. `decisions` and
    `station_id` must be aligned and each station's rows already in chronological
    order (not necessarily adjacent to other stations' rows).
    ts (optional, aligned timestamps): a run also breaks where consecutive rows are
    more than max_gap_s apart (the frozen 120 s continuity rule) - without it, the
    last row of one period and the first row of the next period (days later) merge
    into one "episode" whenever both are True (fixed 2026-09-24)."""
    decisions = np.asarray(decisions, dtype=bool)
    station_id = np.asarray(station_id)
    _assert_contiguous_stations(station_id)
    same_station_as_prev = station_id == np.roll(station_id, 1)
    if ts is not None:
        t = pd.to_datetime(pd.Series(np.asarray(ts))).astype("int64").to_numpy()
        same_station_as_prev &= np.abs(t - np.roll(t, 1)) <= max_gap_s * 1_000_000_000
    prev_decision = np.roll(decisions, 1)
    starts_episode = decisions & ~(same_station_as_prev & prev_decision)
    starts_episode[0] = decisions[0]
    return int(starts_episode.sum())


def policy_cost(decisions, critical, station_id=None, ts=None, sigma=0.5,
                 revenue_per_ride=REVENUE_PER_RIDE, pickup_rate_per_hour=PICKUP_RATE_PER_HOUR,
                 c_dispatch=C_DISPATCH):
    """decisions, critical: same-length boolean arrays (or pandas Series), one entry
    per (station, t) row. If station_id is given (rows chronological per station),
    C_transit counts dispatch EPISODES, not raw dispatch-flagged rows. Without it,
    falls back to one dispatch per True row (only correct if each row is already
    one discrete decision, e.g. already de-duplicated per episode upstream).
    sigma/revenue_per_ride/pickup_rate_per_hour/c_dispatch default to the "mid"
    scenario (see *_SCENARIOS dicts above) - pass a scenario's value explicitly
    (or use sweep_costs()) to run low/high sensitivity analysis.
    Returns {c_penalty, c_transit, total, n_dispatches}."""
    decisions = np.asarray(decisions, dtype=bool)
    critical = np.asarray(critical, dtype=bool)
    missed_station_hours = (critical & ~decisions).sum() * POLL_INTERVAL_HOURS
    c_penalty = missed_station_hours * pickup_rate_per_hour * (1 - sigma) * revenue_per_ride
    n_dispatches = count_dispatch_episodes(decisions, station_id, ts) if station_id is not None else int(decisions.sum())
    c_transit = n_dispatches * c_dispatch
    return {"c_penalty": c_penalty, "c_transit": c_transit, "total": c_penalty + c_transit, "n_dispatches": n_dispatches}


def sweep_costs(decisions, critical, station_id=None):
    """Runs policy_cost across every combination of the four scenario dicts
    (3^4 = 81 combinations) - "a single net cost number, sweepable across
    scenarios" (T10's done-when). Returns a list of dicts, each the scenario
    labels plus policy_cost's own output."""
    results = []
    for sigma_label, sigma in SIGMA_SCENARIOS.items():
        for rev_label, revenue in REVENUE_PER_RIDE_SCENARIOS.items():
            for pick_label, pickup in PICKUP_RATE_PER_HOUR_SCENARIOS.items():
                for disp_label, dispatch in C_DISPATCH_SCENARIOS.items():
                    cost = policy_cost(decisions, critical, station_id=station_id, sigma=sigma,
                                        revenue_per_ride=revenue, pickup_rate_per_hour=pickup,
                                        c_dispatch=dispatch)
                    results.append({
                        "sigma": sigma_label, "revenue_per_ride": rev_label,
                        "pickup_rate_per_hour": pick_label, "c_dispatch": disp_label,
                        **cost,
                    })
    return results


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

    # a multi-day gap inside one station's rows splits the episode (period stitching bug)
    ts = pd.to_datetime(["2026-09-01 10:00", "2026-09-01 10:01", "2026-09-05 10:00", "2026-09-05 10:01"], utc=True)
    assert count_dispatch_episodes([True, True, True, True], station_id) == 1
    assert count_dispatch_episodes([True, True, True, True], station_id, ts) == 2

    flipped = decision_flip_rate(decisions, np.array([True, True, False, True]))
    assert flipped == 0.25                              # 1 of 4 rows flipped

    # unsorted station_id (s1 appears in two separate blocks) must raise, not silently miscount
    bad_station_id = np.array(["s1", "s2", "s1", "s2"])
    try:
        count_dispatch_episodes(np.array([True, True, True, True]), bad_station_id)
        raise AssertionError("expected ValueError on non-contiguous station_id")
    except ValueError:
        pass

    # sweep_costs: 3^4 = 81 scenario combinations, monotonic in the expected direction
    results = sweep_costs(episode_decisions, critical, station_id=station_id)
    assert len(results) == 81
    low_everything = next(r for r in results if r["sigma"] == "high" and r["revenue_per_ride"] == "low"
                           and r["pickup_rate_per_hour"] == "low" and r["c_dispatch"] == "low")
    high_everything = next(r for r in results if r["sigma"] == "low" and r["revenue_per_ride"] == "high"
                            and r["pickup_rate_per_hour"] == "high" and r["c_dispatch"] == "high")
    assert low_everything["total"] < high_everything["total"]  # cheapest scenario combo < priciest
    assert low_everything["revenue_per_ride"] == "low" and low_everything["c_penalty"] == 0.0  # revenue=0 -> zero penalty

    print("costs.demo: OK")


if __name__ == "__main__":
    demo()
