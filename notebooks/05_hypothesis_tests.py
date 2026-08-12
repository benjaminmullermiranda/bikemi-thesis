"""T14: the actual H1/H2 statistical tests the outline promises (docs/thesis_outline.md
S3) - notebooks/04 only produced descriptive dose-response curves and bootstrap CIs before
this. Built 2026-08-08, same day as the Class-2 detector window fix and the Class-4
injector drift_start bound - this script assumes both fixes are already applied to
src/validation.py and src/injection.py.

H1 (Occurrence): negative-binomial GLM, count ~ station + hour, LRT for unevenness.
H2 (Non-linear, class-dependent propagation): two-way model on delta_cost, class x
intensity interaction; permutation inference if diagnostics fail at n=5 (they do here -
that's expected and reported, not a problem to hide).

Scope note on H1's anomaly signal: of the five per-station-hour-capable classes, only
Class 5 (implausible jump) is used. Class 2 (frozen counter) is confounded with genuine
low-ridership hours (O3, resolved 2026-08-08 - not usable as an anomaly *count* without a
ridership-adjusted baseline this project doesn't build). Class 4's natural detector is
currently vacuous (type-sum check against a synthetic ebike=0 breakdown, since real
vehicle-type data was never collected - always trivially consistent). Class 1 (dropout) and
Class 3 (stale) are span/state events, not repeatable per-station-hour point events, and
don't fit a count-per-bin GLM the same way. This narrows H1's operationalisation but keeps
it honest rather than inflating the count with a confounded or vacuous signal.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_io import load_snapshots as load_full_collection
from src.validation import detect_implausible_jump

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# H1: negative-binomial GLM, count ~ station + hour, LRT for unevenness
# ---------------------------------------------------------------------------


def run_h1(raw):
    print("=" * 70)
    print("H1 (Occurrence): negative-binomial GLM, count ~ station + hour")
    print("=" * 70)

    flagged = detect_implausible_jump(raw, max_flow_per_min=1.0)
    flagged["hour"] = flagged["ts"].dt.hour

    agg = flagged.groupby(["station_id", "hour"]).agg(
        n_jump=("jump_flag", "sum"), n_obs=("jump_flag", "size")
    ).reset_index()
    agg = agg[agg["n_obs"] > 0].copy()
    agg["log_exposure"] = np.log(agg["n_obs"])
    print(f"{len(agg)} (station, hour) bins, {agg['n_jump'].sum()} total flagged rows "
          f"of {agg['n_obs'].sum()} observed")

    # full: station + hour effects, offset by log(exposure) so bins with more
    # observations aren't penalised for having more raw opportunities to flag
    full = smf.negativebinomial(
        "n_jump ~ C(station_id) + C(hour)", data=agg, offset=agg["log_exposure"]
    ).fit(disp=0, maxiter=200)
    null = smf.negativebinomial(
        "n_jump ~ 1", data=agg, offset=agg["log_exposure"]
    ).fit(disp=0, maxiter=200)

    lr_stat = 2 * (full.llf - null.llf)
    df_diff = int(full.df_model - null.df_model)
    p_value = sstats.chi2.sf(lr_stat, df_diff)

    print(f"\nFull model: {full.df_model:.0f} params, llf={full.llf:.2f}")
    print(f"Null model (intercept only): llf={null.llf:.2f}")
    print(f"LRT: statistic={lr_stat:.2f}, df={df_diff}, p={p_value:.3e}")
    print(f"Dispersion (alpha) = {full.params.get('alpha', np.nan):.4f} "
          f"(alpha > 0 confirms overdispersion - chi2 on raw counts would have been invalid)")

    result = {
        "n_bins": len(agg), "total_flagged": int(agg["n_jump"].sum()), "total_obs": int(agg["n_obs"].sum()),
        "lr_statistic": lr_stat, "lr_df": df_diff, "lr_p_value": p_value,
        "alpha_dispersion": float(full.params.get("alpha", np.nan)),
    }
    pd.Series(result).to_csv(REPORTS_DIR / "t14_h1_glm_result.csv")
    agg.to_csv(REPORTS_DIR / "t14_h1_station_hour_counts.csv", index=False)
    print(f"\nSaved to reports/t14_h1_glm_result.csv, reports/t14_h1_station_hour_counts.csv")
    return result


# ---------------------------------------------------------------------------
# H2: two-way model on delta_cost, class x intensity interaction + diagnostics
# + permutation fallback
# ---------------------------------------------------------------------------

def run_h2(dose_response_csv="reports/t11_dose_response.csv"):
    print("\n" + "=" * 70)
    print("H2 (Non-linear, class-dependent propagation): class x intensity on delta_cost")
    print("=" * 70)

    df = pd.read_csv(dose_response_csv)
    # "class" is a Python reserved word - patsy's formula parser tries to parse
    # column references as Python expressions, so "C(class)" is a SyntaxError,
    # not just a naming clash. Rename rather than fight patsy's Q() quoting.
    df = df.rename(columns={"class": "anomaly_class"})
    df["anomaly_class"] = df["anomaly_class"].astype("category")
    df["intensity_idx"] = df["intensity_idx"].astype("category")

    model = smf.ols("delta_cost ~ C(anomaly_class) * C(intensity_idx)", data=df).fit()
    from statsmodels.stats.anova import anova_lm
    anova_table = anova_lm(model, typ=2)
    print("\nTwo-way ANOVA (parametric):")
    print(anova_table.to_string())

    resid = model.resid
    shapiro_stat, shapiro_p = sstats.shapiro(resid)
    groups = [g["delta_cost"].values for _, g in df.groupby(["anomaly_class", "intensity_idx"], observed=True)]
    levene_stat, levene_p = sstats.levene(*groups)
    print(f"\nDiagnostics: Shapiro-Wilk normality p={shapiro_p:.4f}, "
          f"Levene homoscedasticity p={levene_p:.4f}")
    diagnostics_ok = shapiro_p > 0.05 and levene_p > 0.05
    print(f"Diagnostics {'PASS' if diagnostics_ok else 'FAIL'} at alpha=0.05 "
          f"({'parametric ANOVA is trustworthy' if diagnostics_ok else 'falling back to permutation inference, as the outline specifies for n=5'})")

    interaction_row = [i for i in anova_table.index if ":" in i]
    interaction_f = anova_table.loc[interaction_row[0], "F"] if interaction_row else np.nan

    perm_p = None
    if not diagnostics_ok:
        # Freedman-Lane (1983): permuting the raw response against all labels tests
        # "is there any structure at all" (no main effects AND no interaction), not
        # specifically the interaction - main effects alone could make the interaction
        # F look artificially extreme relative to a fully-scrambled null. Instead: fit
        # the REDUCED (main-effects-only) model, permute ITS residuals, add them back
        # to the reduced model's fitted values, then refit the FULL model on that
        # pseudo-response and read off the interaction F. This isolates "no interaction
        # beyond what main effects explain" as the null, which is what H2 actually asks.
        rng = np.random.default_rng(0)
        n_perm = 5000
        observed_f = interaction_f

        reduced = smf.ols("delta_cost ~ C(anomaly_class) + C(intensity_idx)", data=df).fit()
        reduced_fitted = reduced.fittedvalues.to_numpy()
        reduced_resid = reduced.resid.to_numpy()

        def interaction_f_stat(frame):
            m = smf.ols("delta_cost ~ C(anomaly_class) * C(intensity_idx)", data=frame).fit()
            tab = anova_lm(m, typ=2)
            row = [i for i in tab.index if ":" in i]
            return tab.loc[row[0], "F"] if row else np.nan

        perm_stats = np.empty(n_perm)
        for i in range(n_perm):
            permuted = df.copy()
            permuted["delta_cost"] = reduced_fitted + rng.permutation(reduced_resid)
            perm_stats[i] = interaction_f_stat(permuted)
        perm_p = float((perm_stats >= observed_f).mean())
        print(f"\nPermutation test (Freedman-Lane, {n_perm} permutations of reduced-model "
              f"residuals): observed F={observed_f:.3f}, permutation p={perm_p:.4f}")

    result = {
        "n_rows": len(df), "interaction_F": float(interaction_f),
        "parametric_p": float(anova_table.loc[interaction_row[0], "PR(>F)"]) if interaction_row else np.nan,
        "shapiro_p": float(shapiro_p), "levene_p": float(levene_p),
        "diagnostics_ok": diagnostics_ok, "permutation_p": perm_p,
    }
    pd.Series(result).to_csv(REPORTS_DIR / "t14_h2_test_result.csv")
    anova_table.to_csv(REPORTS_DIR / "t14_h2_anova_table.csv")
    print(f"\nSaved to reports/t14_h2_test_result.csv, reports/t14_h2_anova_table.csv")
    return result


def main():
    print("Loading full raw collection for H1...")
    raw = load_full_collection()
    print(f"{len(raw)} rows, {raw['station_id'].nunique()} stations\n")

    h1 = run_h1(raw)
    h2 = run_h2()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"H1: unevenness LRT p={h1['lr_p_value']:.3e} "
          f"({'REJECT null (uneven)' if h1['lr_p_value'] < 0.05 else 'fail to reject'} at alpha=0.05)")
    p_for_h2 = h2["permutation_p"] if h2["permutation_p"] is not None else h2["parametric_p"]
    test_used = "permutation" if h2["permutation_p"] is not None else "parametric"
    print(f"H2: class x intensity interaction, {test_used} p={p_for_h2:.4f} "
          f"({'REJECT null (interaction present)' if p_for_h2 < 0.05 else 'fail to reject'} at alpha=0.05)")
    print("\nBoth results are from the CURRENT partial substrate (POC-level, not final) - "
          "this validates the test code runs correctly end to end. Re-run once, unmodified, "
          "against the certified substrate at collection close for the registered result.")


if __name__ == "__main__":
    main()
