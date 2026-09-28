# Appendix A. Implementation details

This appendix holds implementation detail moved out of the main text; it is excluded from the word count.

## A.1 Order of work

The credibility of the results depends on the order in which the method was
fixed, so that order comes first. The design was built and tested in a pilot on
the first continuous stretch of data (6.2 hours, 25–26 July 2026), which
exercised every injector, an interim model, and the cost model, and exposed two
injection bugs (Classes 2 and 4) and a detector window too long to catch short
freezes, all fixed as code corrections. On 8 August 2026 the design was frozen: taxonomy, injection grid, detectors,
safeguard, cost parameters, model specification, threshold-calibration
procedure, and hypotheses H1–H3. What was frozen was the *procedure*; its
outputs (the split, the threshold τ, and the test AUC) were to be computed
once, on the final substrate.

That substrate was fixed after the census of 19 September (§3.5). On
22 September the frozen procedure produced the split, τ = 0.85, and a test AUC
of 0.58, and the 120 corrupted datasets were scored. A review of that run found
that the evaluation code did not yet match the design as written: it scored all
62 periods instead of the 12 test periods, treated unlabelled rows differently
across classes, let the safeguard and the dispatch-episode count cross the gap
between periods, and pooled intensities when bootstrapping. These were
corrected on 24 September and everything was re-run; the split, τ, and AUC
were unchanged, and Chapter 5 reports only the corrected run. The assistant
experiment (§4.6) was pre-registered separately on 24 September, before any
model was called.

## A.2 How each class alters the data

A dropout removes the chosen stations' rows; a frozen counter holds one station's values at their first reading; a stale feed repeats the last real snapshot of every station for Δt; a capacity inconsistency adds the magnitude to one station's bikes, without adjusting docks, until the end of the period; a jump shifts a station's bike count up or down by the magnitude at each row with probability 0.05, clipped to capacity. Silent misreporting leaves the feed untouched and lowers the *true* number of usable bikes by k at 16 stations, which only the cost layer sees. Every corrupted dataset is labelled as modified (NLOD §5–6) and never presented as observed BikeMi data.

## A.3 Detector windows

The detectors are used twice: to certify the substrate
(§3.5) and as the safeguard (§4.4). The frozen-counter detector uses a
60-minute window for certification, so that only long stillness is flagged,
and a 3-minute window as a safeguard, because a 60-minute window cannot catch
freezes shorter than an hour.

## A.4 Cost parameters

A classic-bike ride is free for 30 minutes and costs €0.50 per further
30 minutes, so most trips earn nothing directly, hence the zero low value. The
pickup rate is the number of departures per station-hour in hours when the
station was never critical (median 1.0, mean 1.94, 75th percentile 3.0). The
cost per dispatch estimates a 15–20 minute van stop at Milan logistics rates;
σ, the share of riders who find another bike instead of abandoning the trip,
has no source.

## A.5 Assistant protocol

The protocol (`agent/PROTOCOL.md`) was committed before the first model call; two dated amendments (A1, A2) changed only the provider, because the providers first planned were unavailable, and one earlier test call is recorded and excluded.

## A.6 Detector count

Run over the substrate as a whole rather than period by period, the detector marks 72,895 jumps, four more than the certification excluded.

## A.7 Code and data

| Component | Repository path |
|---|---|
| Collector | `collector/poll.py` |
| Detectors and safeguard | `src/validation.py` |
| Per-period census | `reports/t38_daily_periods.csv` |
| Frozen split and model | `models/frozen_config.json`, `models/frozen_model.joblib` |
| Results | `reports/t11_*`, `t14_*`, `t40_*`, `agent_h4_*` |
| Exposure table | `reports/t40_exposure_test_window.csv` |
| Pilot model diagnostic | `docs/model_diagnostics_2026-08-09.md` |
| Assistant protocol | `agent/PROTOCOL.md` |

Repository: https://github.com/benjaminmullermiranda/bikemi-thesis
