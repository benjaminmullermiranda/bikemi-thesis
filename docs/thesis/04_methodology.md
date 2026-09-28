# 4. Methodology

The credibility of the results depends on the order in which the method was fixed. After a pilot on the first continuous stretch of data (25–26 July 2026), the design was frozen on 8 August 2026: taxonomy, injection grid, detectors, safeguard, cost parameters, model specification, threshold-calibration procedure, and hypotheses H1–H3. What was frozen was the *procedure*; its outputs (the split, the threshold τ, and the test AUC) were computed once, on the final substrate, fixed after the census of 19 September (§3.5). A review of the first run on that substrate found implementation errors, which were corrected before everything was re-run; the split, τ, and AUC were unchanged, and Chapter 5 reports only the corrected run (Appendix A.1).
## 4.1 Anomaly taxonomy

| # | Class | Dimension | Cause | Detectable? | Injection parameters |
|---|---|---|---|---|---|
| 1 | Station dropout | Completeness | Registry/backend churn | Yes: station absent vs. the registry of 320 stations | stations, duration |
| 2 | Frozen counter | Accuracy | Stuck sensor/process | Yes: no change in bikes or docks over a rolling window | duration |
| 3 | Stale feed | Timeliness | Pipeline delay/caching | Feed-level only: `last_updated` is one value shared by all stations | lag Δt |
| 4 | Capacity inconsistency | Consistency | Broken docks, configuration drift | Partially: bikes vs. their sum by vehicle type; the capacity check would need `station_information` (§3.4) | magnitude |
| 5 | Implausible jump | Validity | Transmission/parsing fault | Yes: change between consecutive polls faster than one bike per minute | magnitude, rate |
| 6 | Silent misreporting | Accuracy | Undetected defective bike | No: nothing in the feed distinguishes it from a genuine available bike | offset k, share |

*Table 4.1. Anomaly taxonomy.*

The detectors are used twice: to certify the substrate (§3.5) and as the safeguard (§4.4). The frozen-counter detector uses a 60-minute window for certification and a 3-minute window as a safeguard (Appendix A.3).

## 4.2 Injection design and leakage protocol

Faults are injected at serving time only and scored only in the 12 test
periods (§4.5); training and validation data are never corrupted. The grid
crosses 6 classes × 4 intensities × 5 seeds = 120 corrupted datasets:

| Class | Intensity levels (i0 → i3) |
|---|---|
| 1 Dropout | 1 station for 5 min · 1 for 15 min · 3 for 30 min · 5 for 1 h |
| 2 Frozen | one station for 5 min · 15 min · 30 min · 1 h |
| 3 Stale | lag 60 s · 300 s · 900 s · 3600 s |
| 4 Capacity inconsistency | magnitude 2 · 5 · 10 · 20 bikes |
| 5 Jump | magnitude 2 · 5 · 10 · 20 bikes, at 5% of rows |
| 6 Silent | offset k = 1 · 2 · 4 · 8 bikes, at 5% of stations |

*Table 4.2. Injection grid.*

Silent misreporting leaves the feed untouched and lowers the *true* number of usable bikes by k at 16 stations, which only the cost layer sees; Appendix A.2 describes how the other classes alter the data.

Classes 1–4 are placed inside one test period drawn by the seed, so no fault
straddles two periods (the longest lasts one hour, the shortest period 2.25
hours); Classes 5 and 6 act across the whole test window. A given seed selects
the same placement at every intensity, so intensities differ only in size. The
grid was sized on 30 July and not revised after any result on the final
substrate.  Following Kapoor and Narayanan (2023),
splits are chronological, the model is trained once on clean data and frozen,
and corruption signals are never used as features.

## 4.3 Decision pipeline

Pipeline: raw feed → validation/feature layer → forecast → decision rule →
intervention list → cost.

**Critical state:** ≤ 2 bikes or ≤ 2 free docks; the target is whether a
station will be critical two hours ahead.

**Forecast:** an L2-regularised logistic regression on twelve features entered
linearly: bikes and free docks lagged 1, 2, 5, and 15 minutes, hour of day
(UTC), weekday, temperature, and precipitation. It is deliberately simple, since the thesis studies data quality, not
forecasting. Lags that would span a gap are invalidated, so no lag or horizon
crosses from one period into the next.

**Decision rule:** dispatch if and only if P̂ ≥ τ. τ is the value on a grid
from 0.05 to 0.95 (step 0.05) that minimises total cost (§4.5) on validation
data under the mid cost profile, then frozen. A row for which the corrupted
data yields no forecast, such as a station removed by a dropout, is scored as
"no dispatch": a station the pipeline cannot see is one it does not act on.

## 4.4 Safeguard and recovery layer

The safeguard, which tests SO2, replaces a flagged row's bikes and docks with
the station's last unflagged observation in the same period (carry-forward) and
re-scores the decision. It can be evaluated only where a detector can act on
the injected data. Class 1 has nothing to carry forward, since its rows are
removed. Class 3's detector reads `last_updated` and the payload hash, which
the injected station-level data does not carry. Class 4's detector cannot fire:
the processed substrate keeps only each station's total bike count, so the
type-sum check compares the total with itself, and its zero recovery is not
evidence either way. Class 6 has no detector by design and is reported as the
unrecoverable floor. The safeguard is therefore tested on Classes 2 and 5.

## 4.5 Model, cost model, and threshold

The model is trained on a chronological split at the 60th and 80th percentiles
of forecastable rows, each cut moved to the end of its period so that no
training label horizon reaches into validation. Two short periods have no forecastable row, leaving 60: 33 for training (1,240,603 rows,
to 14 August), 15 for validation (14 August to 7 September), and 12 for testing
(7 to 17 September; 48.2 hours; 360,541 labelled rows).

The cost of a policy over the test window has two components.
**C_penalty** = unserved critical station-hours × pickup rate × (1 − σ) ×
revenue per ride, where a critical station-hour is unserved when the policy did
not dispatch two hours earlier; a dispatch is assumed to prevent the shortfall
it anticipates. The penalty is an opportunity-cost proxy for lost rides, not a
recorded expense. **C_transit** = dispatch episodes × cost per dispatch, where
an episode is one visit: a contiguous run of dispatch decisions at one station,
never continued across a gap.

| Parameter | Low | Mid | High | Source |
|---|---|---|---|---|
| Revenue per ride (EUR) | 0.00 | 0.50 | 1.50 | BikeMi's published tariffs (BikeMi, n.d.) |
| Pickup rate (per station-hour) | 1.0 | 1.94 | 3.0 | This project's own data |
| Cost per dispatch (EUR) | 10.0 | 15.0 | 25.0 | Documented estimate: no published figure found |
| σ (substitution share) | 0.2 | 0.5 | 0.8 | Illustrative range, not derived from ridership data |

*Table 4.3. Cost parameters.*

Appendix A.4 explains how each value was set. Under the mid profile an unserved critical station-hour costs
1.94 × 0.5 × €0.50 = €0.485, so one €15 dispatch equals about 31 of them. All
results use the mid profile, under which τ was calibrated; §5.7 discusses the
other values rather than re-estimating, since another profile would also call
for another τ.

The procedure gives τ = 0.85 and a test AUC of 0.58, against a base rate of
19.1% critical rows (§3.5). Both are reported as produced, not tuned: the model
discriminates weakly, and the high threshold makes the policy conservative.

## 4.6 Assistant experiment (SO3)

SO3 uses a tool-grounded language-model assistant: one call per question, with
the pipeline's output precomputed and passed in as a tool result. The protocol was committed before the first model call; later amendments changed only the provider (Appendix A.5).

Eight scenarios were drawn deterministically from one Class 5 dataset
(magnitude 10, seed 0), each at a different station: four in which the
corruption flips the frozen model's decision and four in which it does not.
Each shows the lagged and current readings, the predicted probability, τ, the
recommendation, and the €15 dispatch cost, under three conditions: *clean*,
*corrupted* with every quality flag set to "ok" (a failed detector), and
*corrupted-flagged* with the detector's real flags. Two configurations cross
these: *blind* (numbers only, so its two corrupted prompts are identical) and
*aware* (numbers plus a quality column and a description of the jump rule).
The assistant returns a decision (dispatch, no dispatch, or abstain), a warning
flag, and a rationale.

Each answer is scored automatically and binarily for *groundedness* (every
number in the rationale appears in the tool output), *warning appropriateness*
(warns if and only if the data is corrupted), *abstention correctness*
(abstains if and only if the data is corrupted and the decision flipped), and
*consistency* (same decision as on the clean version). The protocol also
reports *correct action* (in Chapter 5, *agreement with the clean-model action*): the decision equals the frozen model's clean
decision. Abstaining never counts as correct there, so repeating the
recommendation scores exactly 50% on corrupted data. Stability is the share of
the 48 prompt cells in which three repetitions agree on decision and warning.
gpt-oss-20b and gpt-oss-120b (OpenAI, 2025) and Qwen3.8-27B (Qwen Team, 2026a,
2026b) were run through the Groq API at temperature 0, three repetitions each:
8 × 3 × 2 × 3 × 3 = 432 answers, none missing.

## 4.7 Hypotheses and analysis plan

H1–H3 were fixed on 8 August; after the pilot, a day factor and Milan local
time were added to H1, before it was run on the final substrate. H4 was fixed in its protocol on 24 September, after the H1–H3 run and before any assistant call. No test was chosen after seeing results on
the final substrate. Effect sizes with confidence intervals are the primary
evidence; the tests are secondary.

- **H1 (Occurrence; SO1).** Anomalies occur at non-negligible, uneven rates
  across stations, hours, and days. *Test:* negative-binomial GLM on
  detected-jump counts over the 62 periods, in local time, with a
  likelihood-ratio test per factor.
- **H2 (Non-linear, class-dependent propagation; primary objective).**
  Decision-flip rate and Δcost grow non-linearly with intensity and differ by
  class. *Test:* class × intensity interaction on Δcost; a Freedman–Lane
  permutation test if diagnostics fail.
- **H3 (Bounded recoverability; SO2).** The safeguard recovers a substantial
  share of Δcost for the classes it can detect. *Test:* percentile bootstrap CI
  on paired pre/post Δcost per class and intensity (n = 5 seeds); Wilcoxon's
  signed-rank test as a secondary check, pooled over intensities (n = 20)
  because with five pairs its smallest possible p-value is 0.0625.
- **H4 (Assistant quality-awareness; SO3).** An assistant given quality flags
  warns and abstains more appropriately than one without them. *Analysis:*
  descriptive rates; with eight scenarios, no inferential test.

The Holm correction (α = 0.05) is applied jointly to the three H1 tests and the
H2 interaction test.
