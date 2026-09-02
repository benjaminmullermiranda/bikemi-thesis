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
