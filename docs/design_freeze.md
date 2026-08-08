# Design Freeze

Frozen 2026-08-08, per Prof. Russo's approval of the outline ("Treat it as final and freeze
the design now"). Structured around the four categories he named — injection design, cost
parameterisation, model, threshold — in that order.

**Freeze/record distinction.** What's frozen today is the *procedure* for choosing each
number, not necessarily every number's final value. Two numbers below (the model's train/
val/test split and τ) were computed on 2026-07-30, before this freeze, on a partial
collection — they are recorded here as the **current interim values**, produced by exactly
the procedure being frozen. They will be **recomputed once**, by the same frozen procedure,
against the certified substrate at collection close (2026-08-28), and that single recomputation
— not a comparison of several candidate values — is what becomes final. No value here is
adjusted based on how the injection/dose-response results look; §4 documents why the two
values that already existed before this freeze were not tuned that way.

## 1. Injection design

**Substrate.** The project's own BikeMi collection (not an external dataset), certified as
the longest continuous run with no gap over 120s between polls (`notebooks/02_generate_injection_grid.py:certify_clean_substrate`), per outline §4. Within that run, rows the Class-5
detector flags as implausible jumps are excluded (~1.6% natural false-positive rate on the
full collection); Class 2's natural frozen-counter rate is counted but not excluded pending
resolution of its high natural flag rate (~45%, see open question below).

**Taxonomy and detectors (outline §5, `src/validation.py`):**

| Class | Detector | Rule |
|---|---|---|
| 1 Dropout | `detect_station_dropout` | station id absent from feed window vs. registry |
| 2 Frozen counter | `detect_frozen_counter` | zero variance in bikes AND docks over a 60 min rolling window |
| 3 Stale feed | `detect_stale_update` | feed-level only: `request_ts - last_updated > 180s`, OR identical `payload_sha256` vs. previous poll |
| 4 Count inconsistency | `detect_capacity_inconsistency` | `num_bikes_available != sum(vehicle_types_available)` (type-sum only; capacity-vs-declared half is unimplementable — no `station_information` feed was ever collected) |
| 5 Implausible jump | `detect_implausible_jump` | `|Δbikes| / Δt_min > 1.0` |
| 6 Silent misreporting | none by design | injection-only; this is what makes it the unrecoverable floor |

**Intensity grid (`notebooks/02_generate_injection_grid.py:GRID_SPEC`) — 6 classes × 4
intensities × 5 seeds = 120 experiments:**

| Class | Intensity levels |
|---|---|
| 1 Dropout | 1 station/5min · 1 station/15min · 3 stations/30min · 5 stations/1h |
| 2 Frozen | 5min · 15min · 30min · 1h |
| 3 Stale | lag 60s · 300s · 900s · 3600s |
| 4 Capacity | magnitude 2 · 5 · 10 · 20 |
| 5 Jump | magnitude 2 · 5 · 10 · 20 (rate 0.05) |
| 6 Silent | offset k 1 · 2 · 4 · 8 (share 0.05) |

Duration/magnitude ceilings are sized to the certified substrate's length (documented in
code: "1h max leaves headroom for 5 independently-placed seeds without heavy overlap"), not
to what produced a visible effect — this grid was fixed on 2026-07-30, before any dose-response
result existed to tune it toward.

**Safeguard/recovery policy (§H3):** for classes 1/2/4/5, where the class's detector flags a
row, replace with the last non-flagged observation for that station (carry-forward), then
rescore. Class 1 has no recovery (rows are removed, not corrupted-in-place — nothing to carry
forward). Class 3 is excluded from recovery scoring (feed-level detector needs a different
data shape than the per-station injected files carry). Class 6 recovery = 0.0, definitional.

**Open questions:** (O4, partially addressed 2026-08-08) Class 4's capacity-vs-declared
check needs `station_information` (capacity, lat/lon) — never collected for the first 15
days of the window. `collector/poll.py` now fetches one daily snapshot to `data/static/`
going forward, so the remaining ~3 weeks have it; the first 15 days don't, and wiring it
into `detect_capacity_inconsistency` (currently type-sum only) is still unbuilt. Report as
partial-period coverage, not full resolution.

(O3, resolved 2026-08-08) Class 2's natural flag rate on the full collection is 31.3%, not
45% — that figure was specific to the small certified substrate. Checked whether this reflects
genuine sensor faults or a detector miscalibration: the flag rate tracks time of day closely
(51-65% at 00:00-02:00 and 06:00, vs. 19-33% during 07:00-18:00), is spread across most of
the network rather than concentrated in a few stations (3/320 stations >80% flagged, the
likely genuine hardware-fault candidates; the rest form a graded distribution), and the
median flagged streak is 20 minutes (not the sustained multi-hour pattern a truly stuck
sensor would show). This is low nighttime ridership being caught by a detector that can't
tell "nothing happened" from "sensor stuck," exactly the limitation the code already
documents — not a bug. No change to the outline's existing policy of counting Class 2
natural flags without excluding them from the substrate.

**Safeguard-detector bug found and fixed 2026-08-08 (before any further injected-data
runs):** `notebooks/04_dose_response_analysis.py`'s Class-2 recovery step called
`detect_frozen_counter(df, window="60min")` — but a time-based rolling window still contains
pre-freeze variation until the entire window falls inside the frozen period, so it could
never fire on the 5/15/30-minute injected intensities (verified: 0/5, 0/15, 0/30 rows
flagged) and only just caught the tail of the 1-hour one (1/60). Before this fix, the
pre-freeze POC run had `delta_cost=0.0`/`recovery_rate=NaN` for every single class2_frozen
row — those numbers measured nothing, void rather than a real null result. Fixed by
shortening the window to `3min` (below the shortest injected intensity), verified in
isolation against the same four intensities: 3/5, 13/15, 28/30, 58/60 rows now flagged.

**Re-run same day, and a second, deeper finding.** The injection grid and dose-response
analysis WERE re-run after this fix (and after the Class-4 `drift_start` bound, §1) — not
to see how results look, but to build and verify `notebooks/05_hypothesis_tests.py` (the
actual H1/H2 statistical tests) against real output. Nothing about the frozen values
changed as a result: the intensity grid, cost parameters, and model spec are all unchanged
from what's recorded above. Only the two pre-existing implementation bugs — found by
inspecting the code and unit-testing the detector/injector directly, not by looking at
whether dose-response numbers looked "right" — were corrected.

After the re-run, class2_frozen's `delta_cost` is **still** exactly 0.0 across all 20
(intensity, seed) combinations — checked directly against the regenerated
`reports/t11_dose_response.csv`, not assumed. This is no longer the same bug: `forecast_error`
is now genuinely non-zero (up to ~2.4e-5), confirming the detector and model do see the
frozen counter post-fix. But at that magnitude, against τ=0.6 and this model's weak
discrimination (test AUC 0.61), the probability shift never crosses the decision threshold —
`flip_rate=0.0` for every row, so there is no cost gap for the safeguard to recover.
Class 2's near-zero decision-level propagation on this substrate is itself a legitimate
class-dependent finding for H2, not a residual defect — but it means Class 2's H3
recoverability claim stays untestable on this substrate specifically, independent of the
detector fix. Both the fix and this follow-on limitation should be stated together if this
ever comes up with Russo, not just the fix in isolation.

The re-run's own numbers (`reports/t11_dose_response.csv`, `reports/t14_h1_*`,
`reports/t14_h2_*`) are POC-level, same status as the original 2026-07-30 run, not the
registered result. The single
collection-close re-run against the certified final substrate is still what produces the
final numbers; this session's re-run only proves the code that will produce them works.

## 2. Cost parameterisation

`src/costs.py`. `C_penalty = critical station-hours × C_miss`, `C_miss = expected failed
pickups × (1−σ) × revenue_per_ride`; `C_transit = preventive dispatch episodes × C_dispatch`.
All four swept low/mid/high (3⁴ = 81 scenario combinations, `sweep_costs`):

| Parameter | Low | Mid | High | Source |
|---|---|---|---|---|
| revenue_per_ride (EUR) | 0.0 | 0.50 | 1.50 | BikeMi's published tariffs (bikemi.com/compra, fetched 2026-07-30): first 30min free, then EUR 0.50/30min block |
| pickup_rate_per_hour | 1.0 | 1.94 | 3.0 | This project's own collected data — departures per station-hour, restricted to non-critical hours (17,706/20,800 qualifying station-hours) |
| c_dispatch (EUR/stop) | 10.0 | 15.0 | 25.0 | **Documented estimate**, not publicly sourced — no isolated per-stop rebalancing figure exists in the literature searched; Milan urban logistics rates for a ~15–20min van+driver stop |
| σ (substitution share) | 0.2 | 0.5 | 0.8 | Per outline §7's own stated sweep — illustrative, not derived from ridership data |

`c_dispatch` is the one parameter without an external source; it's flagged as an estimate in
the code itself and swept rather than treated as a point value, which is the intended mitigation.

## 3. Model

`src/features.py` + `src/model.py` + `notebooks/03_train_frozen_model.py`.

- **Forecast:** regularised logistic regression (`sklearn.LogisticRegression`, `C=1.0`),
  predicting P(critical at t+2h) per station.
- **Critical state:** ≤2 bikes OR ≤2 free docks on `num_bikes_available`.
- **Features:** bikes/docks lags at 1/2/5/15 polls back (~1/2/5/15 min), hour-of-day,
  weekday, hourly temperature + precipitation (Milan, Open-Meteo archive API). A lag or the
  label is invalidated (NaN) rather than silently wrong whenever the actual elapsed time to
  that row exceeds 1.5x the nominal cadence — collection gaps don't get treated as valid
  short lags.
- **Split:** chronological only, by `ts` quantile — train <=60th pct, val (60th, 80th], test
  (80th, end]. Never shuffled.
- **Trained on:** the full gap-tolerant collection (not the smaller certified injection
  substrate) — the model should see as much real operating variation as it can; the
  substrate restriction is specifically for the injection experiment, not for training.

**Current interim values (2026-07-30 run, to be recomputed once at collection close per
the freeze/record note above):** `train_end=2026-07-29 10:26:15 UTC`, `val_end=2026-07-29
19:44:00 UTC`, `test_end=2026-07-30 08:33:45 UTC`; test AUC = 0.6105; corr(bikes_lag1,
label) = -0.069 (correctly signed, weak). These boundaries are saved in
`models/frozen_config.json` specifically so no later script recomputes the split quantiles
fresh against a larger collection and silently redraws train/val/test membership.

## 4. Threshold

**Decision rule:** dispatch iff P̂ >= τ. **Calibration procedure:** grid search τ in
[0.05, 0.95] step 0.05 on the validation split, minimising `policy_cost` total under the
**MID** cost profile only (`revenue=0.50, pickup=1.94, c_dispatch=15.0, σ=0.5`) —
one τ, not one per cost-profile combination (27 profiles x per-profile τ would mean
recalibrating and rerunning the full grid 27 times; a single frozen τ lets the 81-way cost
sweep be a re-score of one fixed set of decisions instead). Per-profile τ sensitivity, if
reported at all, is a secondary table computed on the validation set only, never re-run
through the injection grid.

**Current interim value:** τ = 0.60 (from the 2026-07-30 run described in §3; recomputed
once, same procedure, at collection close).

**Robustness variants already scoped in the outline, not yet run:** critical-state threshold
of 1 or 3 bikes/docks instead of 2; a type-level (vs. aggregate) critical definition.

---

## Acquisition status (Russo's stated priority)

As of 2026-08-08: 62.0% overall poll coverage since 2026-07-24, 59.1% success rate. The
certified injection substrate (§1) has not grown past 6.2h since first measured on
2026-07-30, despite two more weeks of collection. Two confirmed causes:

1. The collector's laptop drains to critical battery and hibernates most nights (confirmed
   via Windows power-event log) — not fixable in software; the laptop is not kept on power
   overnight and that isn't something this project can change.
2. Intermittent DNS resolution failures during active hours (e.g. a 15-poll unbroken failure
   streak on 2026-08-08) also break substrate continuity, independent of (1).

(1) is a fixed constraint for the remainder of the window. (2) is the only remaining lever
on substrate length and hasn't been investigated yet. Full detail in `docs/collection_status.txt`.

SO1 (anomaly characterisation) draws on the full collection, not the certified substrate, and
is unaffected by this. The propagation analysis (H2/H3) is the part that depends on substrate
length; if it stays near 6.2h through 2026-08-28, that is reported as a scope limitation
rather than treated as a blocker — the outline already frames the substrate as "the longest
continuous high-coverage segment," not a guaranteed multi-day window.
