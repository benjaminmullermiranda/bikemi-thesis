# 4. Methodology

This chapter specifies the design frozen on 8 August 2026, per the supervisor's
instruction to fix the injection design, cost parameterisation, model, and
threshold before any injected data is examined. Everything here is procedure,
decided in advance; there are no results. The few numbers marked "current
interim value" were computed once, before the freeze, by the exact procedure
being frozen; they will be recomputed once more at collection close, and only
that final recomputation is reported as a result.

## 4.1 Anomaly taxonomy

| # | Class | Dimension | Cause | Detectable? | Injection parameters |
|---|---|---|---|---|---|
| 1 | Station dropout | Completeness | Registry/backend churn | Yes: station absent vs. registry | stations, duration |
| 2 | Frozen counter | Accuracy | Stuck sensor/process | Yes: zero variance over a rolling window | station, duration |
| 3 | Stale feed | Timeliness | Pipeline delay/caching | Yes, feed-level only: `last_updated` is a single value shared by all 320 stations, so per-station staleness isn't observable | lag Δt, scope |
| 4 | Count inconsistency | Consistency | Broken docks, config drift | Partially: bikes vs. sum by vehicle type; the capacity-vs-declared half needs `station_information`, only partly collected (§3.5) | magnitude |
| 5 | Implausible jump | Validity | Transmission/parsing fault | Yes: flow rate exceeding a plausible max | magnitude, rate |
| 6 | Silent misreporting | Accuracy | Undetected defective bike | No: no field distinguishes it from a genuine available bike; injection-only | offset, share |

Each detectable class has a detector in `src/validation.py`, used both to
certify the substrate as clean (§3.6) and, in §4.4, as the safeguard evaluated
for recovery.

## 4.2 Injection design and leakage protocol

Faults are injected at serving time only, into the certified substrate, never at
training time. The grid crosses 6 classes × 4 intensities × 5 seeds = 120
corrupted datasets:

| Class | Intensity levels |
|---|---|
| 1 Dropout | 1 station/5 min · 1/15 min · 3/30 min · 5/1 h |
| 2 Frozen | 5 min · 15 min · 30 min · 1 h |
| 3 Stale | lag 60 s · 300 s · 900 s · 3600 s |
| 4 Capacity | magnitude 2 · 5 · 10 · 20 |
| 5 Jump | magnitude 2 · 5 · 10 · 20 (rate 0.05) |
| 6 Silent | offset k = 1 · 2 · 4 · 8 (share 0.05) |

Ceilings are sized to the substrate length available when the grid was fixed
(30 July), before any dose-response result existed, and are not revised based on
later results. Every corrupted dataset carries an explicit modification label
(NLOD §5–6): synthetic data is never presented as observed BikeMi data.

Three leakage safeguards are fixed in advance, following Kapoor & Narayanan
(2023, §2): chronological splits only, never shuffled; the model trained once on
clean data and frozen; and corruption signals never used as model features.

## 4.3 Decision pipeline

Pipeline: raw feed → validation/feature layer → forecast → decision rule →
intervention list → cost.

**Critical state:** ≤2 bikes or ≤2 free docks, 2 hours ahead. A type-level
definition and thresholds of 1/3 are scoped as robustness variants, not
substitutes.

**Forecast:** a regularised logistic regression predicting P(critical, 2h ahead)
from lagged availability, hour, weekday, and basic weather. Kept deliberately
simple: the thesis studies how data quality affects the pipeline, not how well
it forecasts. A gradient-boosted model is a robustness check only, not the
primary forecaster. Lags spanning a real collection gap are invalidated, not
silently treated as short.

**Decision rule:** dispatch iff P̂ ≥ τ. τ is calibrated once, on validation data
only, minimising total cost (§4.5) under the mid cost profile, then frozen, so
any change in decisions under corrupted data is attributable to data quality
alone. A reactive policy (act only once critical state is observed) is the
comparator.

## 4.4 Safeguard and recovery layer

Where a detector flags a row (classes 1, 2, 4, 5), the safeguard replaces it with
the last non-flagged observation for that station (carry-forward), then
re-scores the decision, testing SO2 (§1.2). Class 1 has nothing to carry
forward (rows are removed, not corrupted in place); Class 3's detector is
feed-level, a different shape than the injected files; Class 6 has no detector
by design, so its recovery is definitionally zero, reported as the unrecoverable
floor, not a missing measurement.

## 4.5 Model, cost model, and threshold (frozen)

The model (`src/features.py`, `src/model.py`) is trained on the full,
gap-tolerant collection (not the smaller substrate, which is reserved for
injection), with a chronological split (train ≤60th percentile, validation
(60–80th], test (80th–end], never shuffled), saved once to
`models/frozen_config.json` so it cannot silently redraw later against a larger
collection.

Cost has two components: **C_penalty** (demand side) = critical station-hours ×
expected failed pickups × (1−σ) × revenue per ride; **C_transit** (supply side) =
preventive dispatches × cost per stop. All four parameters are swept low/mid/high
(81 combinations), so results are reported as ranges, not a single point
estimate:

| Parameter | Low | Mid | High | Source |
|---|---|---|---|---|
| Revenue/ride (EUR) | 0.00 | 0.50 | 1.50 | BikeMi's published tariffs |
| Pickup rate (per station-hour) | 1.0 | 1.94 | 3.0 | This project's own collected data |
| Cost/dispatch (EUR) | 10.0 | 15.0 | 25.0 | Documented estimate: no published figure found; based on typical Milan van-and-driver stop rates |
| σ (substitution share) | 0.2 | 0.5 | 0.8 | Illustrative sweep, not derived from ridership data |

`c_dispatch` is the one unsourced parameter; the mitigation is sweeping it
rather than fixing a point value.

Two numbers here (the split boundaries and τ) were computed once, on 30 July,
before the freeze, on a partial collection. They are current interim values,
produced by the frozen procedure, and will be recomputed exactly once more at
collection close; that single recomputation, not a comparison of candidates,
becomes the final number.

## 4.6 Agent comparison (descoped)

SO3 was pre-registered as a bounded extension: a single tool-grounded agent
evaluated quality-blind (raw values only) vs. quality-aware (values plus
safeguard flags), across eight fixed operator questions × three conditions
(clean / corrupted / corrupted-and-flagged), scored on groundedness, warning
appropriateness, abstention correctness, and recommendation consistency
(protocol adapted from AbstentionBench and AgentAbstain, §2). Per the scope
triage (§1.2), it was cut first, and is not run or reported in this thesis;
the full protocol remains specified in the project repository as future work.

## 4.7 Hypotheses and analysis plan

Fixed in advance, per the supervisor's instruction, so no test is chosen after
seeing results. H1–H2 use Holm-corrected α = 0.05; given limited power at this
scale, effect sizes with confidence intervals are the primary evidence
throughout.

- **H1 (Occurrence).** Anomalies occur at non-negligible, uneven rates across
  stations and hours. *Test:* negative-binomial GLM (rare, overdispersed counts
  rule out χ²), likelihood-ratio test for unevenness.
- **H2 (Non-linear, class-dependent propagation).** Decision-flip rate and Δcost
  grow non-linearly with intensity and differ by class. *Test:* class ×
  intensity interaction model on Δcost; permutation test if diagnostics fail at
  n=5.
- **H3 (Bounded recoverability, classes 1–5).** The safeguard recovers a
  substantial share of Δcost. *Test:* bootstrap CI on paired pre/post Δcost
  (primary; at n=5, Wilcoxon's minimum p of 0.0625 cannot reach α=0.05 alone).
  Class 6 excluded by construction, reported as the unrecoverable floor.

H4 (agent quality-awareness) was pre-registered alongside SO3 (§4.6) and is
descoped for the same reason; it is not tested in this thesis.

This plan, with the frozen injection design, pipeline, and cost model above, is
the full pre-registered specification the results chapter will be evaluated
against once the collection window closes.
