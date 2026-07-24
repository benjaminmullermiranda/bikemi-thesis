# Data Quality and Agentic AI in Operational Decision Support
### A Bike-Sharing Case Study (BikeMi Milan) — Bachelor's Thesis

B.Sc. Business with Data Science · Supervisor: Prof. Ciro Russo

## What this project does
Collects the live GBFS feed of Milan's BikeMi bike-sharing system, characterises real data-quality anomalies, and measures — via controlled fault injection — how data-quality degradation propagates through a deliberately simple, frozen forecasting model into dispatch decisions and operational cost. A bounded final experiment tests whether exposing the same quality signals to an LLM agent changes its reliability. Full research design: [docs/thesis_outline.md](docs/thesis_outline.md).

## Repository structure
```
bikemi-thesis/
├── collector/            # data acquisition (the only code that must run 24/7)
│   ├── poll.py               # polls the GBFS feed every 60 s -> raw archive + metadata
│   └── integrity_report.py   # daily health check: uptime, gaps, drift, frozen-cache streaks
├── data/                 # NOT versioned in git (research asset, grows to GBs)
│   ├── raw/                  # immutable gzipped GBFS responses, one file per poll
│   └── processed/            # cleaned/derived datasets
├── src/                  # analysis code (stubs now, filled in Phase 3-4)
│   ├── validation.py         # safeguard layer: detectors for anomaly classes 1-5
│   ├── injection.py          # controlled fault injectors for classes 1-6
│   ├── features.py           # feature building for the frozen forecast model
│   ├── model.py              # logistic regression P(critical at t+2h), frozen tau
│   └── costs.py              # cost model, decision-flip rate, delta-cost
├── agent/                # bounded final experiment (24 scenarios, hard-capped)
├── notebooks/            # exploratory analysis, numbered (00_, 01_, ...)
├── tests/                # pytest smoke tests
└── docs/                 # thesis outline and project documents
```

## Quickstart
```bash
pip install -r requirements.txt
python collector/poll.py              # start collecting (keep the laptop awake)
python collector/integrity_report.py  # run daily: collection health report
```

## Data & licensing
- **Source:** BikeMi official public GBFS feed (`station_status`), polled every 60 s with the required `Client-Identifier` header, published under NLOD 2.0 (attribution). The licence page is archived in the thesis appendix.
- **Raw data is not versioned in git** (see `.gitignore`): it is a multi-gigabyte research asset, archived locally with an independent backup.
- **Secondary clean substrate** for injection experiments: SF Bay Area Bike Share (Kaggle), verified on download.

## Status
- [ ] Collector running continuously
- [ ] 5-week collection window frozen
- [ ] Validation layer (classes 1–5)
- [ ] Injection framework (6 classes × 4 intensities × 5 seeds)
- [ ] Frozen model + tau calibration
- [ ] Cost model + dose–response curves
- [ ] Agent comparison (24 scenarios)

## Author
Benjamin [Surname] — Università degli Studi di Cassino e del Lazio Meridionale.
