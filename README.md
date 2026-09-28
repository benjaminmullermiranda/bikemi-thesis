# Data Quality and Agentic AI in Operational Decision Support
### A Bike-Sharing Case Study (BikeMi Milan) — Bachelor's Thesis

B.Sc. Economics with Data Science (Class L-33) · Supervisor: Prof. Ciro Russo

## What this project does
Collects the live GBFS feed of Milan's BikeMi bike-sharing system, characterises real data-quality anomalies, and measures — via controlled fault injection — how data-quality degradation propagates through a deliberately simple, frozen forecasting model into dispatch decisions and operational cost. A bounded agent experiment (quality signals exposed to an LLM agent) is specified but not run in this submission. Full research design: [docs/thesis_outline.md](docs/thesis_outline.md).

## Repository structure
```
bikemi-thesis/
├── collector/            # data acquisition (the only code that must run 24/7)
│   ├── poll.py               # polls the GBFS feed every 60 s -> raw archive + metadata
│   └── integrity_report.py   # daily health check: uptime, gaps, drift, frozen-cache streaks
├── data/                 # raw/injected/tmp NOT versioned (GBs); metadata.csv + static/ are
├── src/                  # analysis library (each module has an assert-based demo())
│   ├── data_io.py            # load + deduplicate raw snapshots
│   ├── validation.py         # safeguard layer: detectors for anomaly classes 1-5
│   ├── injection.py          # controlled fault injectors for classes 1-6
│   ├── features.py           # feature building for the frozen forecast model
│   ├── model.py              # logistic regression P(critical at t+2h), frozen tau
│   └── costs.py              # cost model, decision-flip rate, delta-cost
├── models/               # frozen model + config (tau, split boundaries)
├── notebooks/            # pipeline scripts (run order below); 00/01 are exploratory only
├── reports/              # final result tables and figure (t38_*, t11_*, t14_*)
├── archive/              # superseded results, kept for audit (see archive/README.md)
├── agent/                # SO3 agent comparison: specified, not run (see thesis §4.6)
├── tests/                # pytest: smoke import + every src demo() self-check
└── docs/                 # thesis chapters (docs/thesis/), outline, design freeze, evidence/
```

## Quickstart
```bash
pip install -r requirements.txt
python collector/poll.py              # start collecting (keep the laptop awake)
python collector/integrity_report.py  # run daily: collection health report
python -m pytest tests -q             # self-checks
```

## Reproducing the results
Run from the repository root, in this order (the file numbering is historical, not the run order):

| Step | Script | Produces |
|---|---|---|
| 1 | `notebooks/07_multiday_substrate.py` | `reports/t38_*`, the certified 62-period substrate. **Do not re-run**: the committed `t38_daily_periods.csv` is the certified substrate used in the thesis; re-running recomputes it from the still-growing archive |
| 2 | `notebooks/03_train_frozen_model.py` | `models/frozen_model.joblib`, `frozen_config.json` (tau, split) |
| 3 | `notebooks/02_generate_injection_grid.py` | `data/injected/`, 120 corrupted datasets (windows in the 12 test periods) |
| 4 | `notebooks/04_dose_response_analysis.py` | `reports/t11_*`, dose-response on the test periods (resumable) |
| 5 | `notebooks/05_hypothesis_tests.py` | `reports/t14_h1_*`, `t14_h2_*`, Holm summary |
| 6 | `notebooks/06_h3_recovery_test.py` | `reports/t14_h3_*` |
| 7 | `docs/thesis/build.py` | `docs/thesis/thesis_full.md` |

Steps 2–5 load the full raw archive and need several GB of free RAM; on a small machine run them from a plain terminal. Weather comes live from the Open-Meteo archive API, so a re-run can differ marginally if archived values are revised.

## Data & licensing
- **Source:** BikeMi official public GBFS feed (`station_status`), polled every 60 s with the required `Client-Identifier` header, published under NLOD 2.0 (attribution). The licence page and licence text are archived in `docs/evidence/`.
- **Weather:** Open-Meteo historical weather API (CC BY 4.0).
- **Raw data is not versioned in git** (see `.gitignore`): it is a multi-gigabyte research asset, archived locally with an independent backup.
- **Injection substrate:** the project's own BikeMi collection: 62 certified daily periods (251.5 h over 36 days, 320 stations), fixed on 2026-09-22 before any experiment — see `reports/t38_*` and thesis §3.5. All thesis tables and Figure 5.1 are collected in `reports/thesis_tables_and_figures.xlsx`.

## Status
- [x] Collection (analysis window frozen at 2026-09-19)
- [x] Validation layer (classes 1–5)
- [x] Injection framework (6 classes × 4 intensities × 5 seeds)
- [x] Frozen model + tau calibration (tau = 0.85, test AUC 0.58)
- [x] Cost model + dose–response curves (12 test periods)
- [x] H1–H3 tests
- [ ] Agent comparison (24 scenarios): specified, not run
- [ ] Thesis text: results, discussion, conclusion

## Author
Benjamin Muller — Università degli Studi di Cassino e del Lazio Meridionale.
