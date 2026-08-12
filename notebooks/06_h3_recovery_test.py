"""T14 (cont.): H3, the safeguard-recoverability test the outline promises
(docs/thesis_outline.md S3) - built 2026-08-12, same pattern as 05's H1/H2.
Prepared and checked against the CURRENT partial substrate per Russo's
2026-08-11 email item 3 ("prepare and check the code for the statistical
tests on sample results, so the analysis is ready the moment the real data
arrives") - this validates the test code runs correctly end to end, not the
registered result.

H3 (Bounded recoverability, classes 1-5): "the safeguard layer detects most
injected anomalies ... and recovers a substantial share of their Delta cost."
Primary: bootstrap percentile CI on the paired difference (delta_cost -
delta_cost_recovered) per class - i.e. how much of the corruption's cost the
safeguard actually recovers, with a CI, not just a point estimate.
Secondary: Wilcoxon signed-rank on the same pairs (per the outline: at n=5 its
minimum two-sided p is 0.0625, unable to reach alpha=0.05 - reported for
completeness, never treated as the primary evidence).

Scope, matching notebook 04's own established recovery-scoring boundaries:
- class1_dropout: no recovery mechanism (rows are REMOVED, nothing to carry
  forward) - excluded from H3, same as notebook 04's RECOVERABLE_CLASSES minus
  class1 already implies.
- class3_stale: feed-level detector needs a different data shape than the
  injected per-station files carry - excluded from recovery scoring (T11), so
  also excluded here.
- class6_silent: NO detector exists by design - recovery_rate=0.0, definitional
  "unrecoverable floor" per the outline, not a class H3 tests for recovery.
- Tested classes: class2_frozen, class4_capacity, class5_jump - the three with
  an actual carry-forward recovery mechanism and a saved delta_cost_recovered.

Pairing granularity: pooled across the full frozen intensity grid per class (4
intensities x 5 seeds = 20 pairs), the SAME pooling convention notebook 04's
own bootstrap CI on delta_cost already uses ("pooled across 4 intensities x 5
seeds = 20 draws") - a documented choice, not an attempt to dodge the n=5
power problem the outline flags for Wilcoxon specifically.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TESTED_CLASSES = ["class2_frozen", "class4_capacity", "class5_jump"]


def run_h3(dose_response_csv="reports/t11_dose_response.csv"):
    print("=" * 70)
    print("H3 (Bounded recoverability): paired bootstrap CI + Wilcoxon on")
    print("delta_cost vs. delta_cost_recovered, per class")
    print("=" * 70)

    df = pd.read_csv(dose_response_csv)
    if "delta_cost_recovered" not in df.columns:
        raise SystemExit(
            "reports/t11_dose_response.csv has no delta_cost_recovered column - "
            "re-run notebooks/04_dose_response_analysis.py (updated 2026-08-12) first."
        )

    rng = np.random.default_rng(0)
    n_boot = 5000
    bootstrap_rows, wilcoxon_rows = [], []

    for class_name in TESTED_CLASSES:
        sub = df.loc[df["class"] == class_name, ["delta_cost", "delta_cost_recovered"]].dropna()
        pre = sub["delta_cost"].to_numpy()
        post = sub["delta_cost_recovered"].to_numpy()
        recovered = pre - post  # amount of cost the safeguard recovered, per pair

        boot_means = [rng.choice(recovered, size=len(recovered), replace=True).mean() for _ in range(n_boot)]
        lo, hi = np.percentile(boot_means, [2.5, 97.5])
        bootstrap_rows.append({
            "class": class_name, "n_pairs": len(recovered),
            "mean_delta_cost_pre": pre.mean(), "mean_delta_cost_post": post.mean(),
            "mean_recovered": recovered.mean(), "ci_low": lo, "ci_high": hi,
        })
        print(f"\n{class_name}: n={len(recovered)} pairs")
        print(f"  pre-safeguard delta_cost  mean={pre.mean():10.3f}")
        print(f"  post-safeguard delta_cost mean={post.mean():10.3f}")
        print(f"  recovered (pre-post)      mean={recovered.mean():10.3f}  95% CI [{lo:10.3f}, {hi:10.3f}]")

        if np.allclose(pre, post):
            # e.g. class2_frozen/class4_capacity on the current substrate: delta_cost
            # is 0.0 for every row (docs/model_diagnostics_2026-08-09.md), so there is
            # no cost gap for the safeguard to recover - Wilcoxon is undefined on an
            # all-zero difference vector, not a code bug to work around.
            print("  Wilcoxon: skipped - pre == post for every pair (no cost gap exists "
                  "to recover on this substrate; see docs/model_diagnostics_2026-08-09.md)")
            wilcoxon_rows.append({"class": class_name, "n_pairs": len(recovered),
                                   "statistic": np.nan, "p_value": np.nan,
                                   "note": "degenerate: pre==post for every pair"})
        else:
            stat, p = sstats.wilcoxon(pre, post)
            print(f"  Wilcoxon signed-rank: statistic={stat:.3f}, p={p:.4f}")
            wilcoxon_rows.append({"class": class_name, "n_pairs": len(recovered),
                                   "statistic": float(stat), "p_value": float(p), "note": ""})

    bootstrap_df = pd.DataFrame(bootstrap_rows)
    wilcoxon_df = pd.DataFrame(wilcoxon_rows)
    bootstrap_df.to_csv(REPORTS_DIR / "t14_h3_bootstrap_ci.csv", index=False)
    wilcoxon_df.to_csv(REPORTS_DIR / "t14_h3_wilcoxon_result.csv", index=False)
    print(f"\nSaved to reports/t14_h3_bootstrap_ci.csv, reports/t14_h3_wilcoxon_result.csv")
    print("\nCurrent partial substrate (POC-level, not final) - this validates the test "
          "code runs correctly end to end. Re-run once, unmodified, against the certified "
          "substrate at collection close for the registered result.")
    return bootstrap_df, wilcoxon_df


if __name__ == "__main__":
    run_h3()
