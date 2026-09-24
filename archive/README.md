# Superseded artifacts (kept for audit, not used by any script)

| Path | What it was | Superseded by |
|---|---|---|
| `t11_allperiods_20260924/` | T37 results (120 experiments) scored on all 62 periods, incl. train/val | `reports/t11_*` on the 12 test periods only (methodology §4.5), 2026-09-24 |
| `t11_partial_class6_buggy/` | Class 6 results before the label-NaN asymmetry fix (flat ~3,500 Δcost floor) | same |
| `old_class1_dropout__i0__seed0.json` | single leftover worker result from the 2026-09-22 run | same |
| `t15_clean_phat_vector.csv` | clean-substrate predicted probabilities of the 2026-08-09 model (used in `docs/model_diagnostics_2026-08-09.md`) | retrained model, `models/frozen_config.json` (2026-09-22) |
