# 1. Introduction

## 1.1 Motivation

Bike-sharing operators move bicycles between stations to keep the system
usable: a station with no bikes cannot serve a pickup, and a station with no
free docks cannot accept a return. These rebalancing decisions are triggered by
a live data feed, not by watching the stations directly. When the feed degrades
(a station drops out, a sensor freezes, a counter reports an implausible value),
the decision pipeline inherits the error, and the operator pays for a mistake
in the data, not in the rule it followed.

Milan's BikeMi system publishes such a feed continuously, in the GBFS format.
Because it is live rather than a pre-cleaned dataset, it shows problems a
benchmark would hide: stations vanishing, counters freezing, inconsistent
capacity figures, bikes reported as available when they are not. This thesis
sets aside the well-covered question of whether a system can recommend where
to send a van (Chapter 2) and asks a narrower one: what happens to the
decision pipeline when its input data is dirty, and how much of that damage a
simple safeguard can recover without touching the model itself.

## 1.2 Research question and objectives

**Research question.** How does data-quality degradation in a live bike-sharing
feed propagate through an operational decision pipeline (raw data → forecast →
dispatch decision → cost), and how much of that harm can be recovered without
improving the forecasting model itself, and, as a secondary question, whether giving a language-model assistant data-quality signals changes its warnings and abstentions on a fixed set of scenarios?

Data quality, not predictive accuracy, is the independent variable. The model is
kept simple and frozen before any corrupted data is scored, and corruption is
applied at serving time only; if the model changed alongside the corruption,
no result could be attributed to data quality alone. The price of this choice
is that every result holds for this particular frozen model and threshold, a
limit Chapter 5 states wherever it matters.

**Primary objective.** Quantify each link of the raw data → forecast → decision
→ cost chain, per anomaly class and intensity, and identify where the loss
concentrates.

**Secondary objectives.**

- **SO1:** Characterise the anomalies actually observed in the live feed.
- **SO2:** Measure how much of the degradation a rule-based safeguard recovers,
  without retraining the model.
- **SO3:** As a bounded, final extension, test whether a tool-grounded
  language-model assistant given explicit data-quality signals warns or
  abstains differently than one without them, on a fixed, objectively scored
  scenario set.

Each objective is tested by one hypothesis fixed in advance (§4.7): H1 answers
SO1, H2 the primary objective, H3 SO2, and H4 SO3. The "agentic AI" of the
title refers to SO3 in a deliberately limited sense, kept as a bounded final step with predefined scenarios and objective scoring so that it complements the core analysis rather than competing with it: a language model that reads the pipeline's
output through a tool interface and returns a decision, a warning, and a
rationale, without planning or acting on the system (§4.6). SO3 is reported as a short, descriptive extension.

## 1.3 Structure

Chapter 2 places the thesis in the literature and names the gap it fills.
Chapter 3 describes the BikeMi case study, the data collection, and the
certified substrate used in the experiments. Chapter 4 sets out the
methodology and the order in which each part was fixed. Chapter 5 reports the
results, discusses them, states the limitations, and concludes.
