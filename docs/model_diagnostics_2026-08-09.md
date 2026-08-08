# Model diagnostics: why classes 1/2/4 show zero decision-level impact

Diagnostic only — nothing frozen (model, tau, injection design, cost params) was changed
to produce this. All checks are read-only scoring/refitting against data already collected,
run to explain an observed result, not to tune toward one. Companion to `design_freeze.md`.

## The observation

On the certified substrate, `class1_dropout`, `class2_frozen`, and `class4_capacity` all
show `flip_rate=0.0` / `delta_cost=0.0` across every (intensity, seed) combination.
`class5_jump` scales strongly (delta_cost 243 to 10,655). `class6_silent` is modest but
real (2.7 to 8.9) via a different mechanism (feed-invisible, costed against the true hidden
state, not decision changes). `class3_stale` is small and occasionally negative (episode-
merging artifact, previously documented).

## Root cause, confirmed in three independent ways

**1. The combined target has a U-shaped relationship with occupancy, which a linear model
cannot represent.** "Critical" = `(bikes<=2) OR (docks<=2)` - both extremes of the same
occupancy axis signal risk; the middle is safe. Splitting the 2h-ahead target into its two
components and predicting each separately with the *same* features:

| Target | AUC |
|---|---|
| Combined label (bikes<=2 OR docks<=2, 2h ahead) | 0.656 |
| stockout_2h (bikes<=2, 2h ahead) alone | 0.972 |
| dockfull_2h (docks<=2, 2h ahead) alone | 0.977 |

The features aren't weak - they're being asked to fit a non-monotonic relationship with a
linear model, and the OR-combination cancels most of the usable signal.

**2. The frozen model's own coefficients show this collapse directly.**

```
bikes_lag1   -0.02172        docks_lag1   -0.08420
bikes_lag2   -0.00974        docks_lag2   -0.01632
bikes_lag5   -0.01997        docks_lag5   -0.01871
bikes_lag15  -0.01307        docks_lag15  +0.02599
hour         +0.01058        weekday      +0.17154
temp_c       -0.08510        precip_mm    -0.63427
                              intercept    +2.44573
```

Every bike/dock lag coefficient is under 0.09 in magnitude. `precip_mm` (-0.634) and the
intercept (+2.446) dominate - the model leans on weather and a constant offset because
those have a genuinely monotonic relationship with the combined target; occupancy doesn't.

**3. Capacity-normalized occupancy correlates far better with the outcome than what the
model actually uses.** `corr(|bikes/capacity - 0.5|, label) = 0.632` vs.
`corr(bikes_lag1, label) = 0.002` on the same 72,092 rows (capacity from
`data/static/station_information_20260808.json.gz` - collected 2026-08-09, not from the
July substrate period itself, since capacity was never polled before O4's fix; used as a
proxy since GBFS capacity is documented as rarely-changing). The model was never given
occupancy, only raw counts un-normalized by station size.

## Why this explains the class-level pattern specifically

Classes 1/2/4 corrupt bike/dock *counts* - the exact channel the model's coefficients show
it barely uses. Class 5 (jump) injects large enough magnitude (2-20 bikes, 5% of rows) that
even a near-zero coefficient times a large delta still moves log-odds enough to occasionally
cross tau=0.60. Class 6 (silent) doesn't go through the model at all - it's costed directly
against the true hidden state. This is a complete, internally consistent account, not three
separate coincidences.

## What this is and isn't

**Is:** a genuine finding about model specification, worth stating plainly - the combined
critical target as currently defined is poorly suited to a linear model over raw counts.

**Isn't:** a reason to change the frozen model now. Fixing it (adding an occupancy feature,
splitting into two models, or using a non-linear model) means changing feature engineering
or model architecture in direct response to seeing which corruption classes produce effects
- exactly the post-hoc tuning the freeze prohibits, and arguably a more serious version of
it than any bug fix made so far, since it would touch the model itself, not code that
implements an already-decided spec. This is deliberately left unfixed and is presented here
as an open methodological finding, the same category as the H1 reframing - something to put
in front of Russo, not silently resolve.

## Supporting artifacts

- `reports/t15_clean_phat_vector.csv` - full P-hat vector, 72,092 rows
  (`row_id, station_id, timestamp, p_hat, y_true, decision_clean`).
- V1-V4 diagnostic numbers and the corrected V3 methodology (originally tested current-state
  stockout/dockfull, which is near-tautological given lag1 - fixed to use the same 2h-ahead
  shift as the real label) are captured in this document; the scripts that produced them
  were run from a scratch location, not added to the repo (pure one-off diagnostics, not
  part of the reproducible pipeline).
