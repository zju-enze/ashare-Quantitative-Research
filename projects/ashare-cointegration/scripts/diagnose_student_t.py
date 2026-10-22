"""Fit Student-t tail parameters to frozen 2021-2025 data; no simulations."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".local/diagnostics_runtime/arch-8.0.0"
sys.path.insert(0, str(RUNTIME))
for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS",
            "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import importlib.metadata
import json
import platform
import time
import warnings
import numpy as np
import pandas as pd
from scipy import stats
from arch import arch_model
from arch.univariate import StudentsT
from statsmodels.stats.diagnostic import acorr_ljungbox

INPUT = ROOT / ".local/production/formation-2021-2025-v2"
PRIVATE = ROOT / ".local/review/student_t_2021_2025"
OUTPUT = ROOT / "results_review/student_t_2021_2025"
WORKERS = 4
MODEL_NAMES = ("constant_t", "garch_t", "gjr_t")
SERIES = None


def now():
    return datetime.now().astimezone().isoformat()


def self_check():
    # Verify the unit-variance parameterization, not the ordinary t scale.
    x = np.array([-4., -1., 0., .7, 3.])
    for nu in (3., 5., 12.):
        expected = stats.t.logpdf(x, df=nu, scale=np.sqrt((nu-2)/nu))
        observed = StudentsT().loglikelihood([nu], x, np.ones(len(x)),
                                            individual=True)
        np.testing.assert_allclose(observed, expected, rtol=1e-12, atol=1e-12)
    assert set(MODEL_NAMES) == {"constant_t", "garch_t", "gjr_t"}


def prepare():
    freeze = json.loads((INPUT / "freeze.json").read_text(encoding="utf-8"))
    universe = pd.read_parquet(INPUT / "U.parquet").reset_index(drop=True)
    prices = np.load(INPUT / "prices.npy", mmap_mode="r")
    dates = pd.DatetimeIndex(freeze["calendar"])
    assert freeze["formation"] == ["2021-01-01", "2025-12-31"]
    assert dates.min() >= pd.Timestamp("2021-01-01")
    assert dates.max() <= pd.Timestamp("2025-12-31")
    assert dates.is_monotonic_increasing and dates.is_unique
    assert prices.shape == (len(dates), len(universe)) == (1212, 2984)
    assert universe.ts_code.is_unique
    assert np.isfinite(prices).all() and (prices > 0).all()
    returns = 100 * np.diff(np.log(prices), axis=0)
    total = returns.sum(axis=1)
    groups = universe.groupby("L2", sort=True).indices
    cols, metadata = [], []

    def add(values, kind, identifier, name, l2="", members=0, controls=""):
        cols.append(np.asarray(values, dtype=float))
        metadata.append(dict(series_index=len(cols)-1, kind=kind,
                             identifier=identifier, name=name, L2=str(l2),
                             members=int(members), controls=controls))

    for j, row in universe.iterrows():
        add(returns[:, j], "stock", row.ts_code, row["name"],
            row.L2, len(groups[row.L2]))
    add(returns.mean(axis=1), "market_proxy", "U_EQUAL_WEIGHT",
        "Equal-weight frozen universe", members=len(universe))
    for l2, indices in groups.items():
        if len(indices) < 5:
            continue
        sector = returns[:, indices].mean(axis=1)
        market_ex_sector = ((total-returns[:, indices].sum(axis=1))
                            / (len(universe)-len(indices)))
        design = np.column_stack((np.ones(len(returns)), market_ex_sector))
        fit, _, rank, _ = np.linalg.lstsq(design, sector, rcond=None)
        if rank != 2:
            raise ValueError(f"Industry proxy design is not identified: {l2}")
        add(sector-design @ fit, "industry_proxy", str(l2),
            universe.loc[indices[0], "L2_name"], l2, len(indices),
            "market_excluding_industry")
    for j, row in universe.iterrows():
        indices = groups[row.L2]
        market_loo = (total-returns[:, j])/(len(universe)-1)
        predictors = [np.ones(len(returns)), market_loo]
        label = "market_leave_self_out"
        if len(indices) >= 5:
            sector_loo = ((returns[:, indices].sum(axis=1)-returns[:, j])
                          / (len(indices)-1))
            predictors.append(sector_loo)
            label += "+industry_leave_self_out"
        design = np.column_stack(predictors)
        fit, _, rank, _ = np.linalg.lstsq(design, returns[:, j], rcond=None)
        if rank != design.shape[1]:
            raise ValueError(f"Stock proxy design is not identified: {row.ts_code}")
        add(returns[:, j]-design @ fit, "specific_proxy", row.ts_code,
            row["name"], row.L2, len(indices), label)
    values = np.column_stack(cols)
    assert np.isfinite(values).all()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.save(PRIVATE / "series.npy", values)
    meta = pd.DataFrame(metadata)
    meta.to_csv(PRIVATE / "series_metadata.csv", index=False, encoding="utf-8")
    tasks = []
    for row in metadata:
        models = MODEL_NAMES if row["kind"] == "stock" else ("garch_t",)
        tasks.extend((row, model) for model in models)
    spec = dict(created_at=now(), input_run=INPUT.name,
                price_dates=[str(dates[0].date()), str(dates[-1].date())],
                return_dates=[str(dates[1].date()), str(dates[-1].date())],
                model_dates=[str(dates[2].date()), str(dates[-1].date())],
                prices=1212, returns=1211, model_observations=1210,
                stocks=len(universe), planned_series=len(meta),
                series_counts=meta.kind.value_counts().to_dict(),
                planned_fits=len(tasks), workers=WORKERS, blas_threads=1,
                mean_model="AR(1) with constant",
                primary="GARCH(1,1) with standardized symmetric Student-t",
                comparator="AR(1) with constant variance and Student-t",
                sensitivity="AR(1)-GJR-GARCH(1,1)-t for all stocks",
                distribution_parameter_bounds=[2.05, 500.0],
                stock_ADF_filter=False, trimming_or_winsorization=False,
                simulations=False, EG_DH_retests=False,
                uncertainty="Per-series approximate robust Wald intervals; withheld for nu or volatility constraint boundaries; no simultaneous coverage or independent-stock assumption",
                solver_policy="One targeted refit for initial optimizer failure or a GJR likelihood below its nested GARCH fit; initial estimates retained",
                proxy_limit="Proxy residuals are not identified structural permanent/transitory innovations; their intervals do not include factor-estimation uncertainty",
                program="scripts/diagnose_student_t.py",
                python=platform.python_version(),
                libraries={p: importlib.metadata.version(p) for p in
                           ("arch", "numpy", "scipy", "pandas", "statsmodels")})
    (OUTPUT / "method.json").write_text(json.dumps(spec, ensure_ascii=False,
                                                  indent=2), encoding="utf-8")
    return tasks, spec


def initialize():
    global SERIES
    SERIES = np.load(PRIVATE / "series.npy", mmap_mode="r")


def fit_one(task, starting_values=None):
    meta, model = task
    row = dict(meta, model=model)
    values = np.asarray(SERIES[:, meta["series_index"]])
    scale = float(np.std(values, ddof=1))
    if not np.isfinite(scale) or scale <= 0:
        return dict(row, status="constant_or_invalid_series", scale=scale)
    y = values/scale
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fit = arch_model(
            y, mean="AR", lags=1,
            vol="Constant" if model == "constant_t" else "GARCH",
            p=1, o=int(model == "gjr_t"), q=1, dist="StudentsT",
            rescale=False).fit(
                disp="off", update_freq=0, cov_type="robust",
                show_warning=False, starting_values=starting_values,
                options={"maxiter": 500 if starting_values is None else 2000,
                         "ftol": 1e-8})
        parameters = fit.params
        nu = float(parameters["nu"])
        try:
            se = float(fit.std_err["nu"])
        except np.linalg.LinAlgError:
            se = float("nan")
        z = np.asarray(fit.std_resid)
        z = z[np.isfinite(z)]
        assert len(z) == fit.nobs == 1210
        tscale = np.sqrt((nu-2)/nu)
        pit = stats.t.cdf(z/tscale, df=nu)
        ordered_pit = np.sort(pit)
        ks_distance = max(np.max(np.arange(1, len(z)+1)/len(z)-ordered_pit),
                          np.max(ordered_pit-np.arange(len(z))/len(z)))
        lb = acorr_ljungbox(z, lags=[10], return_df=True)
        lb2 = acorr_ljungbox(z*z, lags=[10], return_df=True)
        alpha = float(parameters.get("alpha[1]", 0.))
        beta = float(parameters.get("beta[1]", 0.))
        gamma = float(parameters.get("gamma[1]", 0.))
        boundary = bool(nu <= 2.051 or nu >= 499.99)
        persistence = alpha+beta+gamma/2
        volatility_boundary = bool(
            model != "constant_t" and (persistence >= .9999 or alpha <= 1e-7
                                      or beta <= 1e-7 or alpha+gamma <= 1e-7))
        converged = bool(fit.convergence_flag == 0
                         and np.isfinite(parameters.to_numpy()).all()
                         and np.isfinite(fit.loglikelihood))
        row.update(status="converged" if converged else "optimization_failed",
                   convergence_flag=int(fit.convergence_flag),
                   optimizer_message=str(fit.optimization_result.message),
                   nobs=int(fit.nobs), scale=scale, nu=nu, nu_se_robust=se,
                   nu_ci_low=nu-1.959963984540054*se,
                   nu_ci_high=nu+1.959963984540054*se,
                   nu_boundary=boundary,
                   ci_available=bool(converged and np.isfinite(se) and se > 0
                                     and not boundary and not volatility_boundary),
                   ar1=float(parameters["y[1]"]),
                   mean_constant=float(parameters["Const"])*scale,
                   omega=float(parameters.get("omega",
                               parameters.get("sigma2", np.nan)))*scale**2,
                   alpha=alpha, beta=beta, gamma=gamma,
                   volatility_persistence=persistence,
                   persistence_boundary=bool(model != "constant_t"
                                             and persistence >= .9999),
                   volatility_constraint_boundary=volatility_boundary,
                   loglikelihood=float(fit.loglikelihood),
                   aic=float(fit.aic), bic=float(fit.bic),
                   z_variance=float(np.var(z, ddof=1)),
                   z_skew=float(stats.skew(z, bias=False)),
                   z_excess_kurtosis=float(stats.kurtosis(z, bias=False)),
                   lb10_z_p=float(lb.lb_pvalue.iloc[0]),
                   lb10_z2_p=float(lb2.lb_pvalue.iloc[0]),
                   pit_KS_distance=float(ks_distance))
        for q in (.01, .05):
            suffix = str(int(q*100))
            threshold = tscale*stats.t.ppf(1-q/2, df=nu)
            fixed5 = np.sqrt(3/5)*stats.t.ppf(1-q/2, df=5)
            row["tail_"+suffix+"_fitted"] = float(np.mean(np.abs(z)>threshold))
            row["tail_"+suffix+"_fixed5"] = float(np.mean(np.abs(z)>fixed5))
        row["warnings"] = " | ".join(sorted(set(str(w.message) for w in caught)))
    return row


def repair_fits(frame):
    """One deterministic refit for observed failures or a worse nested optimum."""
    initialize()
    records = []
    frame["warnings"] = frame["warnings"].fillna("").astype(str)
    parents = {(r.kind, r.identifier): r for _, r in
               frame.loc[frame.model.eq("garch_t")].iterrows()}
    for index, old in frame.iterrows():
        if old.status == "converged" and old.model != "gjr_t":
            continue
        parent = parents.get((old.kind, old.identifier))
        bad_nesting = (old.model == "gjr_t" and parent is not None
                       and old.loglikelihood < parent.loglikelihood-1e-5)
        if old.status == "converged" and not bad_nesting:
            continue
        if old.model == "gjr_t" and parent is not None:
            p = parent
            start = [p.mean_constant/p.scale, p.ar1, p.omega/p.scale**2,
                     p.alpha, 0., p.beta, p.nu]
        else:
            total = old.alpha+old.beta
            start = [old.mean_constant/old.scale, old.ar1, .02,
                     old.alpha*.98/total, old.beta*.98/total, old.nu]
        metadata = {key: old[key] for key in
                    ("series_index", "kind", "identifier", "name", "L2",
                     "members", "controls")}
        metadata["series_index"] = int(metadata["series_index"])
        new = fit_one((metadata, old.model), starting_values=start)
        accepted = (new["status"] == "converged"
                    and (old.status != "converged"
                         or new["loglikelihood"] >= old.loglikelihood-1e-6))
        reason = "worse_than_nested_model" if bad_nesting else "optimizer_failure"
        records.append(dict(kind=old.kind, identifier=old.identifier,
                            model=old.model, reason=reason, accepted=accepted,
                            old_status=old.status, old_nu=float(old.nu),
                            old_loglikelihood=float(old.loglikelihood),
                            new_status=new["status"], new_nu=new["nu"],
                            new_loglikelihood=new["loglikelihood"]))
        if accepted:
            for key, value in new.items():
                frame.loc[index, key] = value
        frame.loc[index, "repair_reason"] = reason
    # Boundary nuisance estimates do not support ordinary Wald coverage claims.
    vb = (frame.model.ne("constant_t")
          & ((frame.volatility_persistence >= .9999)
             | (frame.alpha <= 1e-7) | (frame.beta <= 1e-7)
             | ((frame.alpha+frame.gamma) <= 1e-7)))
    frame["volatility_constraint_boundary"] = vb
    frame["ci_available"] = (frame.status.eq("converged")
        & np.isfinite(frame.nu_se_robust) & frame.nu_se_robust.gt(0)
        & ~frame.nu_boundary.astype(bool) & ~vb)
    (PRIVATE / "optimizer_repairs.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(targeted_optimizer_refits=records),
                     ensure_ascii=False), flush=True)
    return frame


def summarize(frame, spec, elapsed):
    rows = []
    for (kind, model), part in frame.groupby(["kind", "model"], sort=False):
        good = part.loc[part.status.eq("converged")]
        ci = good.loc[good.ci_available.fillna(False).astype(bool)]
        item = dict(kind=kind, model=model, attempted=len(part),
                    converged=len(good), failed=len(part)-len(good),
                    nu_boundary=int(good.nu_boundary.sum()),
                    persistence_boundary=int(good.persistence_boundary.sum()),
                    volatility_constraint_boundary=int(
                        good.volatility_constraint_boundary.sum()),
                    CI_available=len(ci),
                    CI_contains_5=int(((ci.nu_ci_low<=5) & (ci.nu_ci_high>=5)).sum()),
                    CI_entirely_below_5=int((ci.nu_ci_high<5).sum()),
                    CI_entirely_above_5=int((ci.nu_ci_low>5).sum()),
                    nu_below_4=int((good.nu<4).sum()),
                    diagnostic_z_LB10_below_05=int((good.lb10_z_p<.05).sum()),
                    diagnostic_z2_LB10_below_05=int((good.lb10_z2_p<.05).sum()))
        for q in (.1, .25, .5, .75, .9):
            item["nu_q"+str(int(100*q))] = float(good.nu.quantile(q))
        for col in ("volatility_persistence", "tail_1_fitted", "tail_1_fixed5",
                    "tail_5_fitted", "tail_5_fixed5", "pit_KS_distance"):
            item[col+"_median"] = float(good[col].median())
        rows.append(item)
    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT / "summary.csv", index=False, encoding="utf-8")
    stocks = frame.loc[frame.kind.eq("stock") & frame.status.eq("converged")]
    industry = stocks.groupby(["L2", "model"]).agg(
        stocks=("nu", "size"), nu_median=("nu", "median"),
        nu_q25=("nu", lambda v: v.quantile(.25)),
        nu_q75=("nu", lambda v: v.quantile(.75))).reset_index()
    industry.to_csv(OUTPUT / "by_industry.csv", index=False, encoding="utf-8")
    state = dict(status="complete", completed_at=now(), fits=len(frame),
                 planned_fits=spec["planned_fits"], execution_seconds=elapsed,
                 converged=int(frame.status.eq("converged").sum()),
                 numerical_or_optimizer_failures=int((frame.status!="converged").sum()),
                 targeted_optimizer_refits=int(frame.get(
                     "repair_reason", pd.Series(dtype=str)).notna().sum()),
                 output=str(PRIVATE / "estimates.csv"),
                 simulations_started=False, EG_DH_retests_started=False)
    (OUTPUT / "execution.json").write_text(json.dumps(state, ensure_ascii=False,
                                                     indent=2), encoding="utf-8")
    print(summary.to_json(orient="records", force_ascii=False), flush=True)


def main():
    self_check()
    if (PRIVATE / "estimates.jsonl").exists():
        raise FileExistsError("Existing diagnostic evidence is preserved; do not overwrite.")
    tasks, spec = prepare()
    start = time.perf_counter()
    rows = []
    print(json.dumps(dict(started_at=now(), planned_fits=len(tasks),
                          series=spec["series_counts"], workers=WORKERS)), flush=True)
    with (PRIVATE / "estimates.jsonl").open("x", encoding="utf-8") as stream:
        with ProcessPoolExecutor(WORKERS, initializer=initialize) as pool:
            for row in pool.map(fit_one, tasks, chunksize=8):
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=True)+"\n")
                if len(rows) % 250 == 0:
                    stream.flush()
                    print(f"{len(rows)}/{len(tasks)} fits, "
                          f"{time.perf_counter()-start:.1f}s", flush=True)
    frame = pd.DataFrame(rows)
    assert len(frame) == len(tasks)
    assert not frame.duplicated(["kind", "identifier", "model"]).any()
    frame.to_csv(PRIVATE / "initial_estimates.csv", index=False, encoding="utf-8")
    frame = repair_fits(frame)
    frame.to_csv(PRIVATE / "estimates.csv", index=False, encoding="utf-8")
    summarize(frame, spec, time.perf_counter()-start)


if __name__ == "__main__":
    main()
