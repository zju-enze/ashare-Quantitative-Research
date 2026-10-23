"""Fixed v1.2 EG and complete-family correction; no application filters."""
from itertools import combinations
import warnings

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.adfvalues import mackinnonp, _tau_mins
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.tsatools import add_trend


METHODS = {"BF": "bonferroni", "Holm": "holm", "BH": "fdr_bh"}
VALID = ("valid", "tail_unresolved")


def adf_audit(x, regression):
    result = adfuller(x, regression=regression, autolag="AIC",
                      maxlag=None, store=True, regresults=True)
    stat, p, _, store = result
    return dict(stat=float(stat), p=float(p), used_lag=int(store.usedlag),
                L_max=int(store.maxlag), N_effective=int(store.nobs),
                AIC_best=float(store.icbest))


def applicability(x):
    x = np.asarray(x, dtype=float)
    if not np.isfinite(x).all() or np.ptp(x) == 0 or np.ptp(np.diff(x)) == 0:
        return dict(compatible=False, status="invalid_or_constant", level=None, difference=None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        level, difference = adf_audit(x, "c"), adf_audit(np.diff(x), "c")
    compatible = level["p"] >= .05 and difference["p"] < .05
    return dict(compatible=bool(compatible), status="compatible" if compatible else "incompatible",
                level=level, difference=difference,
                warnings=[type(w.message).__name__ + ": " + str(w.message) for w in caught])


def eg_audit(a, b):
    """Same OLS/residual-ADF/MacKinnon path as frozen statsmodels coint."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    row = dict(N_input=len(a), EG_executed=False, EG_stat=None, p_library=None,
               p_raw=None, p_for_adjustment=1., compute_status="numerically_ineligible",
               parameter_valid=False, placeholder_reason=None, p_zero_origin=None,
               warning_class="", alpha=None, beta=None, residual_mean=None,
               residual_std=None, residual_variance_ratio=None, rank=None,
               condition_number=None, R_squared=None, L_max=None, used_lag=None,
               N_effective=None, AIC_best=None)
    if a.shape != b.shape:
        raise ValueError("Aligned pair inputs required")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        row["placeholder_reason"] = "nonfinite_input"
        return row
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        design = add_trend(b, trend="c", prepend=False)
        fit = OLS(a, design).fit()
        row.update(rank=int(fit.model.rank), condition_number=float(fit.condition_number),
                   R_squared=float(fit.rsquared))
        if design.shape[1] != 2 or row["rank"] != 2:
            row["placeholder_reason"] = "rank_deficient"
            return row
        beta, alpha = fit.params
        residual = fit.resid
        row.update(EG_executed=True, alpha=float(alpha), beta=float(beta),
                   residual_mean=float(residual.mean()), residual_std=float(residual.std(ddof=1)),
                   residual_variance_ratio=float(np.var(residual)/np.var(a)) if np.var(a)>0 else None)
        tolerance = 1e-10 * max(1, np.sqrt(np.mean(a*a)), abs(alpha),
                                np.sqrt(np.mean((beta*b)**2)))
        if abs(residual.mean()) > tolerance:
            raise ArithmeticError("Residual mean exceeds fixed tolerance")
        if not fit.rsquared < 1 - 100 * np.sqrt(np.finfo(float).eps):
            row.update(EG_stat=-np.inf, p_library=0., p_zero_origin="near_collinearity_forced",
                       placeholder_reason="near_collinearity", warning_class="CollinearityWarning")
            return row
        audit = adf_audit(residual, "n")
        stat = audit.pop("stat")
        audit.pop("p")  # Ordinary residual-ADF p is not the EG p.
        p = float(mackinnonp(stat, regression="c", N=2))
        row.update(audit, EG_stat=stat, p_library=p)
    row["warning_class"] = ";".join(type(w.message).__name__ for w in caught)
    if not np.isfinite(stat) or not np.isfinite(p) or not 0 <= p <= 1:
        row["placeholder_reason"] = "nonfinite_stat_or_invalid_p"
        return row
    row.update(p_raw=p, p_for_adjustment=p, parameter_valid=True, compute_status="valid")
    if p == 0:
        row.update(compute_status="tail_unresolved",
                   p_zero_origin="mackinnon_boundary" if stat < _tau_mins["c"][1] else "normal_cdf_zero")
    return row


def candidates(universe):
    columns = ["candidate_id", "A", "B", "name_A", "name_B", "L2", "L3_A", "L3_B",
               "layer", "L3_family", "M_L2", "M_L3", "M_GLOBAL"]
    rows = []
    for l2, group in universe.sort_values("ts_code").groupby("L2", sort=True):
        for a, b in combinations(group.to_dict("records"), 2):
            same = a["L3"] == b["L3"]
            rows.append(dict(candidate_id=a["ts_code"]+"__"+b["ts_code"],
                             A=a["ts_code"], B=b["ts_code"], name_A=a["name"], name_B=b["name"],
                             L2=l2, L3_A=a["L3"], L3_B=b["L3"], layer="T" if same else "C",
                             L3_family=a["L3"] if same else None))
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=columns)
    result["M_L2"] = result.groupby("L2").candidate_id.transform("size")
    result["M_L3"] = result.groupby("L3_family").candidate_id.transform("size")
    result["M_GLOBAL"] = len(result)
    return result[columns]


def test_pair(task):
    candidate, a, b, gate_a, gate_b = task
    row = dict(candidate, I1_A_status=gate_a["status"], I1_B_status=gate_b["status"])
    if not gate_a["compatible"] or not gate_b["compatible"]:
        row.update(compute_status="precheck_placeholder", EG_executed=False, p_raw=None,
                   p_library=None, p_for_adjustment=1., placeholder_reason="I1_incompatible",
                   parameter_valid=False, N_input=len(a))
    else:
        row.update(eg_audit(a, b))
    return row


def correct(results):
    table = results.copy()
    if table.candidate_id.duplicated().any():
        raise ValueError("Duplicate candidate")
    if not table.compute_status.isin([*VALID, "precheck_placeholder", "numerically_ineligible"]).all():
        raise ValueError("Unexplained terminal status")
    p = table.p_for_adjustment.to_numpy(float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid correction inputs")
    for domain, key in [("L3", "L3_family"), ("L2", "L2"), ("GLOBAL", None)]:
        for method in METHODS:
            table[f"p_{domain}_{method}"] = np.nan
            table[f"reject_{domain}_{method}"] = pd.Series(pd.NA, index=table.index, dtype="boolean")
        groups = [("GLOBAL", table.index)] if key is None else table.groupby(key, dropna=True).groups.items()
        for _, indices in groups:
            if not len(indices):
                continue
            expected = table.loc[indices, f"M_{domain}"].to_numpy()
            if not np.all(expected == len(indices)):
                raise ValueError("Incomplete frozen family")
            for method, name in METHODS.items():
                reject, adjusted, _, _ = multipletests(table.loc[indices, "p_for_adjustment"], .05, method=name)
                table.loc[indices, f"p_{domain}_{method}"] = adjusted
                table.loc[indices, f"reject_{domain}_{method}"] = reject
    main = table.loc[table.compute_status.isin(VALID) & table.reject_L2_Holm.fillna(False)].copy()
    if len(main):
        main["equation"] = main.apply(
            lambda r: f"P*({r.A}) = {r.alpha:.12g} + ({r.beta:.12g}) P*({r.B}) + residual", axis=1)
        main["calibration_note"] = "名义校正发现，预定校准诊断尚未完成"
    return table, main
