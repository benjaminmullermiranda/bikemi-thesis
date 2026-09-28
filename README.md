# Data Quality and Agentic AI in Operational Decision Support
### A Bike-Sharing Case Study (BikeMi Milan) — Bachelor's Thesis

B.Sc. Economics with Data Science (Class L-33) · Supervisor: Prof. Ciro Russo

## What this project does
Collects the live GBFS feed of Milan's BikeMi bike-sharing system, characterises real data-quality anomalies, and measures — via controlled fault injection — how data-quality degradation propagates through a deliberately simple, frozen forecasting model into dispatch decisions and operational cost. A bounded final experiment tests whether language-model assistants given data-quality flags warn or abstain differently (H4). The thesis is in [docs/thesis/thesis_full.md](docs/thesis/thesis_full.md); all its tables and Figure 5.1 are in [reports/thesis_tables_and_figures.xlsx](reports/thesis_tables_and_figures.xlsx).

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
├── reports/              # final results (t38_*, t11_*, t14_*, t40_*, agent_h4_*) + tables workbook
├── archive/              # superseded results, kept for audit (see archive/README.md)
├── agent/                # SO3/H4 assistant experiment: pre-registered protocol, runner, scenarios
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
| 1 | `notebooks/07_multiday_substrate.py` | `reports/t38_*`, the 62-period census. **Already done — do not re-run**: the census was fixed on 2026-09-22 and is committed; re-running recomputes it from the archive and overwrites it. To regenerate the thesis results, start at step 2 |
| 2 | `notebooks/03_train_frozen_model.py` | `models/frozen_model.joblib`, `frozen_config.json` (tau, split) |
| 3 | `notebooks/02_generate_injection_grid.py` | `data/injected/`, 120 corrupted datasets (windows in the 12 test periods) |
| 4 | `notebooks/04_dose_response_analysis.py` | `reports/t11_*`, dose-response on the test periods (resumable) |
| 5 | `notebooks/05_hypothesis_tests.py` | `reports/t14_h1_*`, `t14_h2_*`, Holm summary |
| 6 | `notebooks/06_h3_recovery_test.py` | `reports/t14_h3_*` |
| 7 | `notebooks/08_exposure_census.py` | `reports/t40_exposure_test_window.csv` (Table 5.1) |
| 8 | `agent/h4_agent.py build` → `run` → `score` | `reports/agent_h4_*` (Table 5.4; `run` needs a `GROQ_API_KEY`) |
| 9 | `docs/thesis/build.py`, then `build_docx.py` | `docs/thesis/thesis_full.md`, Word version |

Steps 1–7 need the raw archive (not in git, see below) and several GB of free RAM; the committed outputs in `reports/` and `models/` are the ones reported in the thesis. Weather is fetched from the Open-Meteo archive API; the series used in the thesis run is archived in `reports/weather_openmeteo_used_20260924.csv` for reference. Because Open-Meteo can revise past values, a re-run can differ marginally from it.

## Data & licensing
- **Source:** BikeMi official public GBFS feed (`station_status`), polled every 60 s with the required `Client-Identifier` header, published under NLOD 2.0 (attribution). The licence page and licence text are archived in `docs/evidence/`.
- **Weather:** Open-Meteo historical weather API (CC BY 4.0).
- **Raw data is not versioned in git** (see `.gitignore`): the archive of raw feed payloads is a multi-gigabyte research asset, kept with an off-machine backup and shared with the thesis supervisor separately. The acquisition metadata of every poll (`data/metadata.csv`) and the station-information snapshots (`data/static/`) are in the repository; processed and injected datasets are regenerated from the raw archive by the scripts above.
- **Injection substrate:** the project's own BikeMi collection: 62 certified daily periods (251.5 h over 36 days, 320 stations), fixed on 2026-09-22 before any experiment — see `reports/t38_*` and thesis §3.5. All thesis tables and Figure 5.1 are collected in `reports/thesis_tables_and_figures.xlsx`.

## Status
- [x] Collection (analysis window frozen at 2026-09-19)
- [x] Validation layer (classes 1–5)
- [x] Injection framework (6 classes × 4 intensities × 5 seeds)
- [x] Frozen model + tau calibration (tau = 0.85, test AUC 0.58)
- [x] Cost model + dose–response curves (12 test periods)
- [x] H1–H3 tests
- [x] H4 assistant experiment (8 scenarios × 3 conditions × 2 configurations, 3 models × 3 repetitions = 432 answers)
- [x] Thesis complete (`docs/thesis/`)

## Author
Benjamin Muller — Università degli Studi di Cassino e del Lazio Meridionale.
