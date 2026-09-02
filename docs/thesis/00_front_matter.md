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
