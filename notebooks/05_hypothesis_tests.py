"""T14: the actual H1/H2 statistical tests the outline promises (docs/thesis_outline.md
S3) - notebooks/04 only produced descriptive dose-response curves and bootstrap CIs before
this. Built 2026-08-08, same day as the Class-2 detector window fix and the Class-4
injector drift_start bound - this script assumes both fixes are already applied to
src/validation.py and src/injection.py.

H1 (Occurrence): negative-binomial GLM on the 62 certified periods, one LRT per factor
(station, hour, day; Milan local time) - see run_h1. Holm correction across H1-H2 (§4.7).
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


def _nb_lrt(agg, full_terms, drop_term):
    """LRT for one factor: NB GLM with all full_terms vs. the same model without
    drop_term, both offset by log(exposure) so bins with more observations aren't
    penalised for having more raw opportunities to flag."""
    def fit(terms):
        rhs = " + ".join(f"C({t})" for t in terms) or "1"
        return smf.negativebinomial(f"n_jump ~ {rhs}", data=agg, offset=agg["log_exposure"]).fit(disp=0, maxiter=200)
    full = fit(full_terms)
    reduced = fit([t for t in full_terms if t != drop_term])
    lr = 2 * (full.llf - reduced.llf)
    df_diff = int(full.df_model - reduced.df_model)
    return {"factor": drop_term, "n_bins": len(agg), "lr_statistic": lr, "lr_df": df_diff,
            "lr_p_value": sstats.chi2.sf(lr, df_diff), "alpha_dispersion": float(full.params.get("alpha", np.nan))}


def run_h1(raw):
    """Updated 2026-09-24 for the certified multi-day substrate: raw is restricted
    to the 62 certified periods (not the live archive), hours/days are Milan local
    time, and day is added as a factor (§4.7). One LRT per factor, since a single
    station x hour x day NB model (~160k bins x ~370 dummies) does not fit in this
    machine's memory: station and hour are tested on (station, hour) bins, day on
    (day, hour) bins. Hours only cover the daytime window the collector actually
    captured - H1's hour effect says nothing about unobserved night hours."""
    print("=" * 70)
    print("H1 (Occurrence): negative-binomial GLM, LRT per factor (station, hour, day)")
    print("=" * 70)

    flagged = detect_implausible_jump(raw, max_flow_per_min=1.0)
    local = flagged["ts"].dt.tz_convert("Europe/Rome")
    flagged["hour"], flagged["day"] = local.dt.hour, local.dt.date.astype(str)
    print(f"{int(flagged['jump_flag'].sum())} flagged rows of {len(flagged)}; "
          f"local hours covered: {sorted(flagged['hour'].unique())}")

    def bins(keys):
        agg = flagged.groupby(keys, observed=True).agg(n_jump=("jump_flag", "sum"), n_obs=("jump_flag", "size")).reset_index()
        agg = agg[agg["n_obs"] > 0].copy()
        agg["log_exposure"] = np.log(agg["n_obs"])
        return agg

    station_hour = bins(["station_id", "hour"])
    day_hour = bins(["day", "hour"])
    rows = [_nb_lrt(station_hour, ["station_id", "hour"], "station_id"),
            _nb_lrt(station_hour, ["station_id", "hour"], "hour"),
            _nb_lrt(day_hour, ["day", "hour"], "day")]
    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    result.to_csv(REPORTS_DIR / "t14_h1_glm_result.csv", index=False)
    station_hour.to_csv(REPORTS_DIR / "t14_h1_station_hour_counts.csv", index=False)
    day_hour.to_csv(REPORTS_DIR / "t14_h1_day_hour_counts.csv", index=False)
    print(f"\nSaved to reports/t14_h1_glm_result.csv, t14_h1_station_hour_counts.csv, t14_h1_day_hour_counts.csv")
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
    print("Loading raw collection, restricted to the 62 certified periods, for H1...")
    raw = load_full_collection()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from importlib import import_module
    periods = import_module("07_multiday_substrate").load_certified_periods()
    in_period = np.zeros(len(raw), dtype=bool)
    for p in periods.itertuples():
        in_period |= ((raw["ts"] >= p.start) & (raw["ts"] <= p.end)).to_numpy()
    raw = raw.loc[in_period, ["station_id", "ts", "num_bikes_available"]].reset_index(drop=True)
    print(f"{len(raw)} rows in {len(periods)} certified periods, {raw['station_id'].nunique()} stations\n")

    h1 = run_h1(raw)
    del raw
    h2 = run_h2()

    # Holm across the H1-H2 family, as pre-registered in §4.7
    p_h2 = h2["permutation_p"] if h2["permutation_p"] is not None else h2["parametric_p"]
    names = [f"H1 {f}" for f in h1["factor"]] + ["H2 class x intensity"]
    pvals = list(h1["lr_p_value"]) + [p_h2]
    order = np.argsort(pvals)
    holm = np.empty(len(pvals))
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        holm[i] = running
    summary = pd.DataFrame({"test": names, "p_raw": pvals, "p_holm": holm, "reject_at_0.05": holm < 0.05})
    print("\n" + "=" * 70)
    print("SUMMARY (Holm-corrected, alpha=0.05)")
    print("=" * 70)
    print(summary.to_string(index=False))
    summary.to_csv(REPORTS_DIR / "t14_h1_h2_holm_summary.csv", index=False)


if __name__ == "__main__":
    main()
