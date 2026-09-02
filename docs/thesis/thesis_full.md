<!-- TODO before submission: Student ID and Academic Year below are placeholders, not verified facts. -->

# Data Quality and Agentic AI in Operational Decision Support: A Bike-Sharing Case Study

**Student:** Benjamin Antonio Muller Miranda
**Student ID:** [TODO — insert matriculation number]
**Degree Programme:** B.Sc. Business with Data Science
**Supervisor:** Prof. Ciro Russo
**Academic Year:** [TODO — confirm format, e.g. 2025/2026]

---

## Abstract

<!-- TODO: "Main findings" cannot be written until collection closes and the
     pipeline is re-run on final data (per supervisor's instruction: results,
     discussion, and conclusions wait for the data). The paragraph below covers
     topic, objective, and methodology only; a findings sentence must be added
     once results exist, and the word count re-checked against the 150-200
     word limit after that addition. -->

<!-- TODO: AI use statement required here per guideline point 7 — the actual
     policy text for point 7 has not yet been supplied. Do not submit this
     abstract without it. -->

Bike-sharing systems depend on live data feeds to trigger rebalancing decisions,
but those feeds are prone to quality issues such as station dropouts, frozen
counters, and inconsistent capacity values, exactly the conditions under which
a rebalancing decision has the most to lose. This thesis studies how data-quality
degradation in Milan's BikeMi live feed propagates through an operational
decision pipeline, from raw data to a short-horizon forecast, a dispatch
decision, and its operational cost, and how much of that harm a simple,
rule-based safeguard can recover without retraining the forecasting model. Using
a continuously collected BikeMi dataset as the injection substrate, six anomaly
classes are injected at controlled intensities into a certified clean segment of
the feed, and their effect is traced through a frozen forecasting model, a
frozen decision threshold, and an explicit cost model swept across low/mid/high
parameter assumptions. [Main findings: to be added once collection closes and
the frozen pipeline is re-run against the final dataset.]

[AI use statement: to be added per guideline point 7.]

## Contents

1. Introduction
2. Related Work
3. Data and Case Study
4. Methodology
5. Results, Discussion, and Conclusion *(pending collection close)*
References

---

# 1. Introduction

## 1.1 Motivation

Bike-sharing operators rebalance bicycles between stations to keep the system
usable: a station with no bikes cannot serve a pickup, and one with no free docks
cannot accept a return. These decisions are triggered by a live data feed, not by
directly observing the stations. When that feed is degraded (a station drops
out, a sensor freezes, a counter reports an implausible value), the decision
pipeline inherits the error, and the operator pays for a mistake in the data, not
in the rule it followed.

Milan's BikeMi system publishes such a feed continuously, in the GBFS format.
Because it is live rather than a static, pre-cleaned dataset, it shows quality
issues a benchmark dataset would not: stations disappearing, frozen counters,
inconsistent capacity, bicycles reported available when they are not. These are
exactly the conditions where a rebalancing decision has the most to lose.

This thesis does not ask whether a system can recommend where to send a van, a
well-covered question (Chapter 2). It asks a narrower one: what happens to the
decision pipeline when its input data is not clean, and how much of the damage a
simple safeguard can recover without touching the model itself.

## 1.2 Research question and objectives

**Research question.** How does data-quality degradation in a live bike-sharing
feed propagate through an operational decision pipeline (raw data → forecast →
dispatch decision → cost), and how much of that harm can be recovered without
improving the forecasting model itself?

Data quality, not predictive accuracy, is the independent variable. The model is
kept simple and frozen before any corrupted data is examined; only the input data
varies, and corruption is applied at serving time only. This isolates the effect:
if the model changed alongside the corruption, no result could be attributed to
data quality alone.

**Primary objective.** Quantify each link of the raw-data → forecast → decision →
cost chain, per anomaly class and intensity, and identify where the loss
concentrates.

**Secondary objectives.**
- **SO1**: Characterise the anomalies actually observed in the live feed over
  the collection window.
- **SO2**: Measure how much of the degradation a rule-based safeguard layer
  recovers, without retraining the model.
- **SO3**: As a bounded, final extension, test whether an AI agent given
  explicit data-quality signals behaves differently (warns, or abstains) than one
  without them, on a fixed, objectively scored scenario set.

**Scope triage**, fixed in advance: if time runs short, SO3 is cut first. SO1 and
the core propagation analysis are never cut. They are the thesis's central
contribution.

SO3 is descoped for this submission: the university's length requirement for a
quantitative Bachelor's thesis leaves limited room beyond the core propagation
analysis, and SO3 was pre-registered as the first item to cut under exactly
this scenario. Its full protocol (§4.6) remains specified as future work.

## 1.3 Structure

Chapter 2 positions the thesis against the literature and states the gap it
fills. Chapter 3 describes the BikeMi case study and the data collected.
Chapter 4 specifies the frozen methodology (taxonomy, injection design, decision
pipeline, cost model, and analysis plan), fixed before any injected data was
examined. Results, discussion, and conclusions follow once collection closes and
the pipeline is re-run against the final dataset; they are out of scope here by
design.

---

# 2. Related Work

This chapter reviews the literature behind the thesis's central framing: that
data-quality degradation should be traced to its downstream, decision-level cost,
not just to model accuracy. It also covers the literature behind the bounded
agent extension in §4.6, and closes with the gap this thesis fills.

*Full bibliographic details (volume, pages, DOIs) still need a final
verification pass before submission.*

**Data-quality propagation.** Sambasivan et al. (2021, CHI), *"Data Cascades in
High-Stakes AI,"* name and document compounding, downstream consequences of
upstream data-quality issues, the closest precedent for this thesis's
propagation chain (raw data → forecast → decision → cost). Where they document
cascades qualitatively across many deployments, this thesis instruments one
pipeline end to end and quantifies the cascade in monetary terms, under
controlled, repeatable corruption.

**Production data validation.** Breck et al. (2019, SysML/MLSys), *"Data
Validation for Machine Learning"* (TFDV), and Schelter et al. (2018, VLDB),
*"Automating Large-Scale Data Quality Verification"* (Deequ), establish that data
quality can be checked declaratively and continuously at serving time, not only
once at training time. The per-class detectors built for the BikeMi feed
(`src/validation.py`) instantiate the same paradigm for a domain neither paper
addresses.

**Leakage.** Kapoor and Narayanan (2023, *Patterns*), *"Leakage and the
Reproducibility Crisis in ML-based Science,"* show how undetected leakage has
inflated reported performance across empirical ML research. This motivates the
thesis's leakage protocol (§4.2): chronological splits, a model trained once and
frozen, and corruption signals never used as features.

**Production data management.** Polyzotis et al. (2017, SIGMOD), *"Data
Management Challenges in Production Machine Learning,"* frame the broader
collection-to-monitoring problem this thesis's acquisition-to-decision chain sits
inside.

**Bike-sharing decisions vs. forecasts.** Gammelli et al. (2022, *Transp. Res.
Part C* 138), show that predictive and prescriptive performance can diverge in
bike-sharing inventory management: a forecast that scores well can still produce
a poor decision. This supports treating decision- and cost-level outcomes, not
forecast accuracy, as this thesis's primary measure (§1.2), including under
degraded data, which they do not consider.

**Systematic quality perturbation.** Mohammed et al. (2025, *Information Systems*
132; preprint Budach et al., arXiv:2207.14529) perturb data-quality dimensions
systematically and measure the resulting change in model metrics, but stop
there. No work surveyed here continues the chain into an explicit cost function
evaluated under a frozen decision rule; that continuation is this thesis's
specific contribution.

**Quality-aware agents.** SmartFlow (arXiv:2601.00868) and RideAgent
(arXiv:2505.06608) place a grounded LLM downstream of an optimiser in fleet
operations, but neither tests behaviour under degraded input, the condition
this thesis's pre-registered but descoped agent extension (§4.6) targeted. Its
evaluation protocol (groundedness, warning appropriateness, abstention
correctness, recommendation consistency) is adapted from two abstention
benchmarks, AbstentionBench (arXiv:2506.09038) and AgentAbstain
(arXiv:2607.10059), narrowed to one domain and one manipulation rather than
proposed as a new general benchmark.

**The gap.** Data-quality cascades and declarative validation (above) are
established separately from bike-sharing's predictive/prescriptive divide and
from quality-aware agents in fleet operations. No work joins all three: a
per-class fault injection on a live feed's own data, carried through a frozen
decision rule into an explicit cost. Agent quality-awareness was pre-registered
as a bounded final extension (§4.6) but is descoped for this thesis; the
propagation chain itself is this thesis's contribution.

---

# 3. Data and Case Study

## 3.1 The BikeMi feed

BikeMi is Milan's public docked bike-sharing system (320 stations observed). It
publishes real-time station state (bikes available, docks available,
installed/renting/returning status) through a GBFS feed, refreshed at the source
roughly every 10 seconds. This project polls it every 60 seconds: frequent
enough to reliably capture anomalies lasting about two minutes or longer, while
keeping an unattended, long-running collector sustainable. Sub-two-minute
transients remain under-observed by construction.

## 3.2 Licensing

The feed is published under Italy's NLOD 2.0 open-data licence, which permits
redistribution and derivative use with attribution. Before collection began, per
the supervisor's instruction, this was verified by archiving BikeMi's open-data
page and the licence text itself (`docs/evidence/`), recording the required
attribution string for the appendix, and documenting the `Client-Identifier`
header used to identify this project as a sanctioned API consumer, not a
scraper.

## 3.3 Acquisition architecture

Because a live feed's history cannot be recovered retroactively, the collector
(`collector/poll.py`) was built and started before any other part of the
project. It runs a continuous 60-second loop: fetch, archive the raw payload as
gzip JSON, and log acquisition metadata (timestamp, HTTP status, latency,
payload size and hash, feed-declared `last_updated`, and station count),
independent of whether the fetch succeeded. Recording the feed's own
`last_updated` alongside the collector's request time is what keeps feed-level
staleness (the publisher not refreshing) distinguishable from collection failure
(this project not reaching the feed).

A single in-cycle retry recovers transient network blips without masking a real
outage; a failure that survives both attempts is logged as before. Because the
GitHub repository is version history, not a backup, the raw archive is
additionally copied off-machine on a schedule.

## 3.4 Collection window and coverage

The window opened 24 July 2026 and continues to the collection-close date. As of
the latest check: 653.1 hours running, 22,609 of ~38,543 expected polls logged
(58.7% coverage), of which 14,270 (63.1%) succeeded; the rest are logged
errors (mostly connection failures), not silent gaps. Coverage and success rate
are reported separately because an attempted-and-failed poll still tells the
collector something a genuine gap does not.

## 3.5 Known limitations

Two causes account for most gaps, both diagnosed from collector logs. First, the
collector's laptop is not kept on power overnight and suspends when its battery
drains. This was confirmed via Windows power-event logs and is accepted as a
fixed constraint for the rest of the window. Second, intermittent DNS failures
on the mobile-hotspot connection were traced to the hotspot's own DNS proxy and
mitigated with a public resolver and a wider retry backoff (2s→16s).

Class 4's full detector (§4.1) needs the feed's `station_information` endpoint
(capacity, coordinates), only collected from 8 August onward, reported as
partial-period coverage, not a resolved gap. Two corrupted raw snapshots are
excluded from analysis and counted, not silently dropped.

## 3.6 The certified injection substrate

Because collection gaps are collector-side, not random, injecting faults into
the full, gappy collection risks landing an anomaly inside a real gap and
measuring nothing. The injection substrate is instead the **longest continuous
run with no gap over 120 seconds** in the collection: the project's own data,
not an external dataset. This is an interim, monitored figure: 8.5 hours
(9 August, 10:15–18:46 UTC), unchanged for over three weeks despite continued
collection and the mitigations in §3.5. The remaining dominant cause (overnight
power loss, §3.5) was not addressable, so no further growth is expected. It will
be recomputed once, by the same procedure, at collection close, and that final
figure, not this interim one, is what the results chapter uses.

---

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

---

# 5. Results, Discussion, and Conclusion

*Pending collection close. Per the supervisor's instruction (2026-08-11),
results, discussion, and conclusions wait for the final dataset — see §3.6 for
the certified-substrate figure this chapter will use, and §4.7 for the
pre-registered analysis plan it will follow without deviation.*

---

# References

<!-- STATUS: skeleton only, not submission-ready. Every entry below is missing
     at least one required APA field (full author list, exact title, pages,
     and/or DOI) that is not stated anywhere in the current chapter text. I am
     not fabricating author names, titles, or DOIs I cannot verify — filling
     these gaps requires pulling up each source (five were sent directly by
     Prof. Russo by email on 2026-08-05; the rest were found independently).
     Every entry here is cited somewhere in Chapters 1-4; nothing appears here
     that isn't cited in the text, and vice versa, per the university's
     citation rule (§1). Do not submit until every [VERIFY] tag below is
     resolved against the original source. -->

Breck, E., et al. (2019). Data validation for machine learning. *Proceedings of
  SysML/MLSys 2019.* [VERIFY: full author list, page range]

Budach, L., et al. (2022). The effects of data quality on machine learning
  performance (preprint). *arXiv:2207.14529.* [VERIFY: full author list; check
  whether the published version (Mohammed et al., 2025, *Information Systems*,
  132) should be cited instead of, or alongside, this preprint]

Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in
  ML-based science. *Patterns, 4*(9). [VERIFY: page range, DOI]

Polyzotis, N., et al. (2017). Data management challenges in production
  machine learning. *Proceedings of the 2017 ACM International Conference on
  Management of Data (SIGMOD '17).* [VERIFY: full author list, page range]

Sambasivan, N., et al. (2021). "Everyone wants to do the model work, not the
  data work": Data cascades in high-stakes AI. *Proceedings of the 2021 CHI
  Conference on Human Factors in Computing Systems.* [VERIFY: full author
  list, exact title, page range, DOI]

Schelter, S., et al. (2018). Automating large-scale data quality
  verification. *Proceedings of the VLDB Endowment, 11*(12). [VERIFY: full
  author list, page range]

Gammelli, D., et al. (2022). [Title not yet confirmed in source text].
  *Transportation Research Part C: Emerging Technologies, 138.* [VERIFY: exact
  title, full author list, page range, DOI]

[AbstentionBench] (2025 or 2026). [Author(s) and exact title not yet confirmed].
  *arXiv:2506.09038.* [VERIFY: authors, title]

[AgentAbstain] (2026). [Author(s) and exact title not yet confirmed].
  *arXiv:2607.10059.* [VERIFY: authors, title]

[RideAgent] (2025). [Author(s) and exact title not yet confirmed].
  *arXiv:2505.06608.* [VERIFY: authors, title]

[SmartFlow] (2026). [Author(s) and exact title not yet confirmed].
  *arXiv:2601.00868.* [VERIFY: authors, title]
