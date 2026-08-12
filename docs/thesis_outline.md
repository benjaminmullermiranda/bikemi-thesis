# Data Quality and Agentic AI in Operational Decision Support: A Bike-Sharing Case Study
Benjamin Antonio Muller Miranda · B.Sc. Business with Data Science · Supervisor: Prof. Ciro Russo

## 1. Research question and objectives

**Central question.** How does data-quality degradation in a live bike-sharing feed propagate through an operational decision pipeline — raw data → short-horizon forecast → dispatch decision → cost — and how much of the propagated harm can be recovered *without improving the forecasting model itself*?

Data quality, not predictive accuracy, is the independent variable: the forecasting model is simple and frozen, experiments vary only input data, and corruption is applied at serving time only (training-time corruption out of scope).

**Primary objective.** Quantify each link of that chain per anomaly class and intensity, identifying where the loss concentrates.

**Secondary objectives.** SO1 — characterise anomalies observed in the live feed over a fixed 5-week window. SO2 — measure how much degradation a rule-based safeguard layer recovers. SO3 — as a final, bounded extension, test whether quality signals change an LLM agent's behaviour on a fixed, objectively scored scenario set (§8).

**Scope triage.** If time runs short, SO3 is cut first, then the σ-sweep collapses to its mid value; SO1 and the propagation analysis are never cut.

## 2. Positioning (preliminary)

Sambasivan et al. (2021, CHI, "Data Cascades in High-Stakes AI") name and characterise compounding, downstream consequences of upstream data-quality issues — the closest conceptual precedent for this thesis's central propagation framing (raw data → forecast → decision → cost). Two lines of production data-quality infrastructure motivate the validation-layer design in §6: schema- and constraint-based serving-time checking (Breck et al. 2019, SysML/MLSys, TFDV; Schelter et al. 2018, VLDB, Deequ) establish that data quality can be verified declaratively and continuously in a live pipeline, which is the paradigm `src/validation.py`'s per-class detectors instantiate for the BikeMi feed. Polyzotis et al. (2017, SIGMOD, "Data Management Challenges in Production Machine Learning") frame the broader production-ML data-management problem this thesis's acquisition-to-decision chain sits inside. Kapoor & Narayanan (2023, Patterns, "Leakage and the Reproducibility Crisis in ML-based Science") document how undetected leakage inflates reported ML performance across empirical research, directly motivating the chronological-split, train-once-then-freeze leakage protocol in §5.

Gammelli et al. (2022, *Transp. Res. Part C* 138:103571) show that predictive and prescriptive performance diverge in bike-sharing inventory decisions. Mohammed et al. (2025, *Information Systems* 132:102549; preprint Budach et al., arXiv:2207.14529) perturb data-quality dimensions systematically but stop at model metrics. Neither continues into an explicit cost function under a frozen decision rule — the gap this thesis targets. SmartFlow (arXiv:2601.00868) and RideAgent (arXiv:2505.06608) already place a grounded LLM downstream of an optimiser in fleet operations, but neither evaluates agent behaviour under *degraded* input, which is where SO3 is scoped.

## 3. Testable hypotheses

- **H1 (Occurrence).** Anomalies occur at measurable, non-negligible rates, unevenly across stations and hours. *Test:* negative-binomial GLM (station + hour effects; rare, overdispersed counts invalidate χ²); likelihood-ratio test for unevenness.
- **H2 (Non-linear, class-dependent propagation).** Decision-flip rate and Δcost grow non-linearly with intensity, differing across classes even at similar mean forecast-error degradation. *Test:* two-way model on Δcost, class × intensity interaction; permutation inference if diagnostics fail at n = 5.
- **H3 (Bounded recoverability, classes 1–5).** The safeguard layer detects most injected anomalies in classes 1–5 and recovers a substantial share of their Δcost. *Test:* bootstrap percentile CI on paired pre/post-safeguard Δcost per class (primary); Wilcoxon signed-rank secondary — at n = 5 its minimum two-sided p is 0.0625, unable to reach α = 0.05, hence CI-first. Class 6 excluded by construction (~0% recovery is definitional) and reported as the **unrecoverable floor**.
- **H4 (Agent quality-awareness, descriptive).** The quality-aware agent shows fewer unwarranted-confidence responses on corrupted-and-flagged scenarios, without increased inappropriate abstention on clean ones. Effect sizes with exact binomial CIs only; no significance test claimed (24 pairs detect only very large effects).

*Power note (H1–H4).* Power is limited by design; effect sizes with confidence intervals are the primary evidence; significance tests (H1–H2, Holm-corrected, α = 0.05) are supporting.

## 4. Case study, collection and injection substrate

BikeMi Milan (320 docked stations observed), public GBFS feed, NLOD 2.0 licence, `Client-Identifier` header required; licence page archived, attribution quoted in the appendix. Poll interval 60 s (source refresh ~10 s): captures anomalies ≥ ~2 min; sub-2-min transients remain under-observed. Every response is archived immutably with acquisition metadata (timestamp, HTTP status, latency, payload size/hash, feed `last_updated`, station count), so **feed staleness stays distinguishable from collection failure**. Collection window 24 July – 28 August 2026, snapshot date frozen in advance; coverage (polls logged / expected) is reported alongside feed success rate, as the two measure different things.

**Injection substrate: the project's own BikeMi collection**, not an external historical dataset — identical schema to the studied system (removing any cross-system transfer assumption), verified licence, and all fields the taxonomy requires. Since observed collection gaps are collector-side and correlated with machine state rather than random, the substrate is the **longest continuous high-coverage segment** of the window, not the full collection; excluded periods are reported. Cleanliness is pre-certified by passing the segment through the §6 validation layer, natural anomalies excluded and counted.

## 5. Anomaly taxonomy

| # | Class | DQ dimension | Cause | Detectable? | Injection parameters |
|---|---|---|---|---|---|
| 1 | Station dropout | Completeness | Registry/backend churn | Yes — absence vs. registry | stations, duration |
| 2 | Frozen counter | Accuracy | Stuck sensor/process | Yes — zero variance in active hours | station, duration |
| 3 | Stale feed | Timeliness | Pipeline delay/caching | Yes, **feed-level only**: now − `last_updated` and identical-payload streaks. Not per-station: `last_reported` was measured as a batch value, identical across all 320 stations in each of 765 snapshots, so per-station staleness is unobservable here | lag Δt, scope |
| 4 | Count inconsistency | Consistency | Broken docks, config drift | Yes — bikes + docks vs. capacity; `num_bikes_available` vs. sum of `vehicle_types_available` | perturbation magnitude |
| 5 | Implausible value jump | Validity | Transmission/parsing fault | Yes — max plausible flow per interval | magnitude, rate |
| 6 | Silent misreporting (bike shown available, unusable) | Accuracy | Undetected defective bike | **No** — injection-only; k and share are unanchored sensitivity dimensions (no ground truth or per-bike proxy); dose–response shape reported over a wide sweep | offset k, share |

**Injection design:** 6 classes × 4 intensities × 5 seeds, at serving time on the pre-certified substrate → per-class dose–response curves for forecast error, decision-flip rate, and Δcost.

**Leakage protocol.** Chronological splits only, never shuffled. The model is trained once on clean pre-injection data and frozen; injected-fault labels and corruption indicators are never features. Per NLOD §5–§6, all synthetic data is labelled as modified and never reported as observed BikeMi data.

## 6. Decision pipeline and decision rule

Pipeline: raw feed → validation/feature layer → forecast → decision rule → intervention list → cost. **Forecast (simple, frozen):** regularised logistic regression predicting P(critical at t+2h) per station from availability lags, hour/weekday, basic weather; gradient boosting only as a robustness check. **Critical state:** ≤ 2 bikes or ≤ 2 free docks on `num_bikes_available` (aggregate over bike / e-bike / e-bike-with-childseat); since the fleet is heterogeneous, a type-level definition is reported as a robustness variant, as are thresholds of 1 and 3. **Decision rule:** dispatch iff P̂ ≥ τ; τ calibrated once on clean validation data, then frozen across all experiments, so decision changes are attributable to data quality alone. Comparator: reactive policy (intervene once a critical state is observed).

## 7. Cost model

- **C_penalty** (demand side — foregone revenue) = Σ critical station-hours × C_miss, with **C_miss = expected failed pickups × (1 − σ) × revenue per ride** (pickup rate from departure rates in comparable non-empty periods; revenue from published BikeMi pricing); **σ swept {0.2, 0.5, 0.8}**, illustrative bounds, not derived from ridership data.
- **C_transit** (supply side — operator cost) = Σ preventive dispatches × C_dispatch (labour + vehicle time per stop).

All parameters swept low/mid/high; the sum is the economic cost of the policy under stated assumptions, never operator P&L. Headline metrics: decision-flip rate, Δcost (per class × intensity), recovery rate (classes 1–5), unrecoverable floor (class 6).

## 8. Agent comparison (final, limited — hard-capped)

Same tool-grounded agent, two configurations: quality-blind (raw values) vs. quality-aware (values + safeguard flags). 8 operator questions × 3 conditions (clean / corrupted / corrupted-and-flagged) = 24 scenarios, fixed in advance. Criteria: groundedness of every number, warning appropriateness, abstention correctness, recommendation consistency. Protocol adapted from AbstentionBench and AgentAbstain; a controlled feasibility evaluation, not a generalising claim.

---

# Internal working annex

## A1. Collector architecture

```
collector/
├── poll.py               # 60 s fetch loop: fetch, gzip-archive, and log metadata
│                            all inline (no separate archive.py/metadata.py/config.yaml
│                            modules - that split was planned, never built)
├── integrity_report.py   # daily health check: coverage, success rate, gaps, hash-repeat streaks
├── run_collector.bat     # Windows launcher
└── run_collector.ps1     # PowerShell launcher
```

**One in-cycle retry, added 2026-08-08.** The collector runs on a phone hotspot (the only
internet available for this project) with a high rate of transient, near-instant
connection/DNS failures. poll.py now retries once (2 s wait) before logging `"ERROR"` to
metadata.csv and waiting for the next scheduled 60 s cycle; a failure that survives both
attempts is logged exactly as before - this recovers single-poll blips without hiding a
real outage. One real consequence of the original no-retry design already observed:
`data/raw/20260727T071200Z.json.gz` is truncated at byte 65,536 (an I/O buffer-size
boundary, consistent with an interrupted write) and fails to parse - `load_snapshots()` in
notebooks/01_poc_pipeline.py now counts and reports skipped unreadable files instead of
silently discarding them.

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

## A2. Licensing verification checklist

1. Archive BikeMi's open-data page (PDF + screenshot, dated).
2. Quote the exact NLOD 2.0 attribution string verbatim in the appendix.
3. Document the `Client-Identifier` value used and why (sanctioned API use, not scraping).
4. No causal claim anywhere about *why* the licence is NLOD 2.0.

## A3. Literature search terms

"data quality" + machine learning + downstream decision cost · data-centric AI evaluation · GBFS / bike-sharing data quality, sensor fault detection · fault injection + time-series forecasting robustness · LLM agent abstention evaluation (AbstentionBench, arXiv 2506.09038; AgentAbstain, arXiv 2607.10059) · calibrated abstention in tool-using agents · cost-sensitive decisions under corrupted inputs · preventive vs. reactive rebalancing / repositioning OR literature · DQ dimensions canon (Wang & Strong; Sebastian-Coleman).

## A4. T4 POC validation notes

**Model signal is real but modest.** Frozen logistic regression (T4, Class 5 only): test-set AUC = 0.61 (0.5 = no signal, 1.0 = perfect); corr(bikes_lag1, 2h-ahead critical label) = -0.07 - correctly signed (fewer bikes now predicts more likely critical later) but weak. Downstream cost/flip-rate numbers from T4 should be read against this: the model discriminates better than chance but isn't a strong forecaster, which is part of why corruption needs real amplitude to move decisions.

**Observed natural anomaly, unexplained.** Station 2091's derived capacity (num_bikes_available + num_docks_available) swings from 0 to 36 across the 5-day collection window - the largest swing of any of the 320 stations (206/320 stations show a swing >= 5; only 4/320 show <= 1, i.e. trivial noise). `is_installed`/`is_renting`/`is_returning` are `True` for all 2,452 observations at this station, so the swing is not explained by those status flags. Logged here as an observed candidate for SO1 (anomaly characterisation), not a code defect - cause not yet investigated.

## A5. T13 sketch - 24 agent scenarios (H4)

Sketch only, per plan: not implemented, cut first under time pressure. Fixed in advance
per §8: 8 operator questions x 3 conditions (clean / corrupted / corrupted-and-flagged)
= 24 scenarios; each scenario is run against BOTH agent configurations (quality-blind:
raw values only; quality-aware: values + safeguard flag) at build time, so 24 fixed
input scenarios yield 48 responses to score. Class 6 is the one documented exception:
it has no detector by design, so its "corrupted-and-flagged" condition is degenerate
(identical to "corrupted" - no flag ever exists to make the two configs differ),
exactly as H4 already states ("Class 6 excluded... no flag exists").

Each question is paired with the anomaly class/intensity best suited to stress it,
chosen using T11's actual results rather than arbitrarily - classes 5 and 6 each
appear twice (5: the only class with confirmed real decision-level impact, worth
testing from two angles; 6: the theoretically most important "unrecoverable floor"
case, worth testing both as a detection probe and a calibration probe). A specific
(class, intensity, seed) must be picked per scenario from data/injected/ at build
time, verified against a T6 detector re-run to confirm it actually fires for the
"-and-flagged" condition (not every corrupted instance gets flagged - see O3).

Tool-grounded means: the agent calls the SAME functions the pipeline already exposes
- predict_critical (forecast), policy_cost (cost estimate), detect_* (quality-aware
config only) - not a separate re-implementation.

| # | Operator question | Anomaly class (intensity) | Primary criterion stressed | Why this pairing |
|---|---|---|---|---|
| 1 | "How many bikes/docks are available at station X right now?" | Class 5 (jump), mid-high intensity | Groundedness | Directly corrupts the raw count - the simplest test of whether the agent just parrots a corrupted number without noticing it's implausible |
| 2 | "Will station X be critical within the next 2 hours?" | Class 2 (frozen), mid-high intensity | Groundedness | T11 showed class 2 has real but sub-threshold forecast_error - tests whether the agent's *narrative* forecast shifts even when the underlying frozen decision doesn't |
| 3 | "Should we send a rebalancing van to station X right now?" | Class 5 (jump), the intensity level T11 confirmed produces a real decision flip | Recommendation consistency | The one class with a confirmed real flip_rate in T11 - the only scenario type guaranteed to exercise an actual recommendation change, not just a hypothetical one |
| 4 | "Which 3 stations are most at risk right now?" | Class 1 (dropout) | Groundedness + recommendation consistency | A dropped-out station vanishes from the feed entirely - tests whether the agent notices a station is MISSING from consideration, or silently treats absence as "fine" |
| 5 | "Why is station X predicted to become critical?" | Class 4 (capacity inconsistency) | Warning appropriateness | A broken-dock-style count inconsistency is exactly what a good explanation should flag as suspect - tests whether the agent's own reasoning surfaces the inconsistency, not just whether a detector already caught it |
| 6 | "What's the estimated financial impact of skipping dispatch to station X today?" | Class 3 (stale), high intensity | Groundedness (compounding error) | T11 found class 3 can produce a *negative* Delta-cost (episode-merging artifact) - a great real test of whether the agent's cost narrative reflects this correctly instead of naively assuming "worse data = worse cost" |
| 7 | "Has station X shown any unusual or suspicious behaviour in the last hour?" | Class 6 (silent), any intensity | Abstention correctness | Class 6 is undetectable by design - BOTH configs should, in principle, fail to flag it. Tests whether a well-calibrated agent expresses appropriate uncertainty anyway, versus overclaiming certainty it has no basis for |
| 8 | "How confident are you in your recommendation for station X, and why?" | Class 6 (silent), same instance as Q7 | Abstention correctness + warning appropriateness | Deliberately reuses Q7's instance: since no flag can ever exist for class 6, quality-blind and quality-aware face IDENTICAL evidence here - a controlled comparison of whether "awareness" helps when there's genuinely nothing to be aware of |

**Scoring criteria (per outline §8), one sentence each:**
- **Groundedness** - does every number in the response trace back to an actual tool call output, not a plausible-sounding invention?
- **Warning appropriateness** - does the agent warn when (and only when) the underlying data is actually suspect, matching the true corruption state, not the agent's guess?
- **Abstention correctness** - does confidence language track actual uncertainty (lower confidence under corruption/no-flag, not blanket hedging or blanket certainty)?
- **Recommendation consistency** - does the final recommendation match what the frozen decision rule (tau) actually outputs for that scenario, and change only when the true decision changes?

**Not decided yet (deferred to actual implementation, not needed for the sketch):** which LLM, which tool-calling framework, and the exact rubric->score mapping (pass/fail vs. Likert). Per H4's own text, this stays a "controlled feasibility evaluation, not a generalising claim" - 24 fixed scenarios detect only very large effects (exact binomial CIs, no significance test claimed).
