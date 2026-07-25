# Thesis Outline (v4)

**Data Quality and Agentic AI in Operational Decision Support: A Bike-Sharing Case Study**
Benjamin [Surname] · B.Sc. Business with Data Science · Supervisor: Prof. Ciro Russo

---

# PART A — Outline for submission

## 1. Research question and objectives

**Central question.** How does data-quality degradation in a live bike-sharing feed propagate through an operational decision pipeline — raw data → short-horizon forecast → dispatch decision → cost — and how much of the propagated harm can be recovered *without improving the forecasting model itself*?

Data quality, not predictive accuracy, is the independent variable: the forecasting model is deliberately simple and **held fixed**, experiments vary only the input data, and corruption is applied at **serving time only** (training-time corruption out of scope).

**Primary objective.** Quantify each link of that chain per anomaly class and intensity, identifying where the loss concentrates.

**Secondary objectives.** SO1 — characterise the anomalies observed in the live feed over a fixed 5-week window. SO2 — measure how much degradation a rule-based safeguard layer recovers. SO3 — as a final, bounded extension, test whether quality signals change an LLM agent's behaviour on a fixed, objectively scored scenario set.

**Scope triage.** If time runs short: cut SO3 first (demoted to a qualitative demo), then collapse the σ-sweep to its mid value, then reduce intensities from 4 to 2; SO1 and the propagation analysis are never cut.

## 2. Testable hypotheses

- **H1 (Occurrence).** Anomalies occur at measurable, non-negligible rates, unevenly across stations and hours. *Test:* negative-binomial GLM with station and hour effects (rare, overdispersed counts invalidate χ²); unevenness via likelihood-ratio test.
- **H2 (Non-linear, class-dependent propagation).** Decision-flip rate and Δcost grow non-linearly with intensity, differing across classes even at similar mean forecast-error degradation. *Test:* two-way model on Δcost, class × intensity interaction; permutation inference if diagnostics fail at n = 5.
- **H3 (Bounded recoverability, classes 1–5).** The safeguard layer detects most injected anomalies in classes 1–5 and recovers a substantial share of their Δcost. *Test:* bootstrap percentile CI on paired pre/post-safeguard Δcost per class (primary); Wilcoxon signed-rank secondary — at n = 5 its minimum two-sided p is 0.0625, unable to reach α = 0.05, hence CI-first. Class 6 is excluded by construction (~0% recovery is definitional) and reported as the **unrecoverable floor**.
- **H4 (Agent quality-awareness, descriptive).** The quality-aware agent shows fewer unwarranted-confidence responses on corrupted-and-flagged scenarios, without increased inappropriate abstention on clean ones. *Effect sizes with exact binomial CIs only; no significance test is claimed* (24 pairs detect only very large effects). Class 6 excluded (no flag exists; configurations identical).

*Statistical honesty clause (H1–H4).* Power is limited by design; effect sizes with confidence intervals are the primary evidence, significance tests (H1–H3, Holm-corrected, α = 0.05) supporting.

## 3. Case study and data collection

BikeMi Milan (~300 docked stations), official public GBFS feed (`station_information`, `station_status`). **Poll interval 60 s** vs. the source's ~10 s refresh: anomalies ≥ ~2 min are captured, a 10-min interval would alias the short transients under study, and sub-2-min transients are under-observed. Every response is archived immutably with acquisition metadata (timestamp, HTTP status, latency, payload size/hash, feed `last_updated`, station count): **feed staleness stays distinguishable from collection failure**. **Fixed window:** 5 weeks, snapshot date frozen in advance; same-platform companion feeds (Oslo, Bergen, Trondheim) are collected cheaply but not analysed here. **Licence:** NLOD 2.0 (attribution) per BikeMi's open-data page, `Client-Identifier` header required; page archived, attribution string quoted in the appendix. A published historical station-status dataset is the additional clean substrate for injection.

## 4. Anomaly taxonomy

| # | Class | DQ dimension | Cause | Feed-detectable? | Injection parameters |
|---|---|---|---|---|---|
| 1 | Station dropout | Completeness | Registry/backend churn | Yes — absence vs. registry | stations, duration |
| 2 | Frozen counter | Accuracy/Timeliness | Stuck sensor/process | Partial — zero-variance in active hours; `last_reported` stall | station, duration |
| 3 | Stale update | Timeliness | Pipeline delay/caching | Yes — now − `last_reported` | lag Δt, scope |
| 4 | Capacity inconsistency | Consistency | Broken docks, config drift | Yes — bikes + docks vs. capacity | perturbation magnitude |
| 5 | Implausible value jump | Validity | Transmission/parsing fault | Yes — max plausible flow per interval | magnitude, rate |
| 6 | Silent misreporting (bike shown available, unusable) | Accuracy | Undetected defective bike | **No** — injection-only; k and share are unanchored sensitivity dimensions (no ground truth or per-bike proxy); dose–response *shape* reported over a wide sweep, operating point unknown | offset k, share of stations |

**Injection design:** 6 classes × 4 intensities × **5 seeds**, applied at serving time to the clean substrate → per-class dose–response curves for forecast error, decision-flip rate, and Δcost.

## 5. Decision pipeline and decision rule

Pipeline: raw feed → validation/feature layer → forecast → decision rule → intervention list → cost. **Forecast (simple, fixed):** regularised logistic regression predicting P(critical at t+2h) per station — critical = ≤ 2 bikes or ≤ 2 free docks — from availability lags, hour/weekday, basic weather; gradient boosting only as a robustness check. **Decision rule:** dispatch iff P̂ ≥ τ; τ calibrated once on clean validation data, then **frozen** across all experiments so decision changes are attributable to data quality alone. Comparator: reactive policy (intervene once a critical state is observed).

## 6. Cost model

- **C_penalty** (demand side — *foregone revenue*, not operator cost) = Σ critical station-hours × C_miss, with **C_miss = expected failed pickups × (1 − σ) × revenue per ride** (pickup rate from departure rates in comparable non-empty periods; revenue from published BikeMi pricing); **σ (substitution share) swept {0.2, 0.5, 0.8} as illustrative bounds, not derived from ridership data**.
- **C_transit** (supply side — operator cost) = Σ preventive dispatches × C_dispatch (labour + vehicle time per stop).

All parameters swept low/mid/high; the sum is the *economic cost of the policy under stated assumptions*, never operator P&L. Headline metrics: **decision-flip rate**, **Δcost** (per class × intensity), **recovery rate** (classes 1–5), **unrecoverable floor** (class 6).

## 7. Agent comparison (final, limited part — hard-capped)

Same tool-grounded agent, two configurations: **quality-blind** (raw values) vs. **quality-aware** (values + safeguard flags). **8 operator questions × 3 conditions (clean / corrupted / corrupted-and-flagged) = 24 scenarios, fixed in advance.** Criteria: groundedness of every number, warning appropriateness, abstention correctness, recommendation consistency. Protocol adapted from AbstentionBench and AgentAbstain; a controlled feasibility evaluation, not a generalising claim.

## 8. Expected contribution

An anomaly census of a production mobility feed; a quantified propagation analysis from data quality to decisions to cost, with its recoverable vs. unrecoverable share; controlled evidence on whether quality-awareness improves LLM-agent reliability in decision support.

---

# PART B — Internal working annex 

## B1. Collector architecture

```
collector/
├── poll.py        # 60 s fetch loop (requests + tenacity retry/backoff)
├── archive.py     # immutable raw writer: gzip JSON, partitioned by date
├── metadata.py    # acquisition-metadata logger (one row per poll)
└── config.yaml    # feed URL, Client-Identifier, poll interval, snapshot date
```

| Metadata field | Purpose |
|---|---|
| `request_ts` | Local clock time of request |
| `http_status` | 200 vs. 4xx/5xx vs. timeout |
| `response_latency_ms` | Collector-side network health |
| `payload_size_bytes` | Truncation/corruption smoke test |
| `payload_sha256` | Detects byte-identical repeats (frozen upstream cache) |
| `feed_last_updated` | Publisher-level freshness |
| `n_stations_reported` | Per-cycle completeness proxy |

Flat gzip JSON/Parquet queried with pandas/duckdb — no database or queue needed at this volume.

**Redundancy (genuinely independent).** Primary: local cron on the working machine. Secondary: a runner on separate infrastructure (always-on VPS/Raspberry Pi or scheduled cloud job) with its own storage — two cron entries on one laptop are one machine with two alarm clocks. Daily integrity report: gaps > 2 min, station-count drift, hash-repeat streaks, per-runner uptime; archives reconciled at analysis time (union used, divergences logged).

## B2. Licensing verification checklist

1. Archive BikeMi's open-data page (PDF + screenshot, dated).
2. Quote the exact NLOD 2.0 attribution string verbatim in the appendix.
3. Document the `Client-Identifier` value used and why (sanctioned API use, not scraping).
4. No causal claim anywhere about *why* the licence is NLOD 2.0.

## B3. Literature search terms

"data quality" + machine learning + downstream decision cost · data-centric AI evaluation · GBFS / bike-sharing data quality, sensor fault detection · fault injection + time-series forecasting robustness · LLM agent abstention evaluation (AbstentionBench, arXiv 2506.09038; AgentAbstain, arXiv 2607.10059) · calibrated abstention in tool-using agents · cost-sensitive decisions under corrupted inputs · preventive vs. reactive rebalancing / repositioning OR literature · DQ dimensions canon (Wang & Strong; Sebastian-Coleman).
