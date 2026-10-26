"""Project adapter for qfbook.factor.single_test; frozen method v0.5.

Reuse course transforms/design and two-leg costs. Separate formation from
responses, retain missing months, and include initial wealth in drawdown.
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from qfbook.factor import single_test as course


def form_cross_section(g):
    # Select only formation-time fields: future columns cannot enter transforms.
    g = g[["ts_code", "pb", "total_mv", "circ_mv", "industry_code"]].copy()
    g = g.sort_values("ts_code").reset_index(drop=True)
    g["industry"] = g.industry_code
    g["bp"] = 1 / g.pb
    g["ln_mv"] = np.log(g.total_mv)
    g["w_wls"] = np.sqrt(g.circ_mv)
    if len(g) < 50 or g.bp.nunique() < 20:
        return g, "insufficient_sample_or_distinct_bp"
    mad = (g.bp - g.bp.median()).abs().median()
    if mad <= 0:
        return g, "zero_mad"
    g["bp_w"] = course.mad_winsorize(g.bp)
    if g.bp_w.std(ddof=0) <= 0:
        return g, "zero_std"
    g["bp_z"] = course.zscore(g.bp_w)
    x = course._design(g, ["ln_mv"])
    if len(g) <= x.shape[1] or np.linalg.matrix_rank(x) < x.shape[1]:
        return g, "neutralization_rank_or_df"
    g["f_neu"] = course.neutralize(g, "bp")
    return g, "ok"


def form_pool(panel, calendar):
    groups = dict(tuple(panel.groupby("signal_month")))
    formed, status = {}, {}
    for month in calendar.signal_month:
        formed[month], status[month] = form_cross_section(groups.get(month, panel.iloc[:0]))
    return formed, status


def assign_layers(g, n_layer, min_stocks, min_unique):
    if len(g) < min_stocks or g.f_neu.nunique() < min_unique:
        return g.assign(layer=np.nan), "insufficient_domain_sample_or_distinct_factor"
    g = g.sort_values("ts_code").copy()
    g["layer"] = pd.qcut(g.f_neu.rank(method="first"), n_layer, labels=False) + 1
    return g, "ok"


def frozen_wls(g):
    """Course WLS algebra, with z-scores frozen BEFORE response filtering."""
    x = course._design(g, ["bp_z", "ln_mv"])
    y, w = g.ret_fwd.to_numpy(), g.w_wls.to_numpy()
    sw = np.sqrt(w / w.mean())
    xw, yw = x * sw[:, None], y * sw
    n, k = xw.shape
    if n <= k or np.linalg.matrix_rank(xw) < k:
        return np.nan, np.nan, "wls_rank_or_df"
    beta = np.linalg.lstsq(xw, yw, rcond=None)[0]
    resid = yw - xw @ beta
    se = np.sqrt((resid @ resid / (n - k)) * np.linalg.pinv(xw.T @ xw)[1, 1])
    return beta[1], beta[1] / se if se > 0 else np.nan, "ok" if se > 0 else "zero_se"


def evaluate_layers(formed, formation_status, responses, calendar, n_layer=5,
                    min_stocks=50, min_unique=20, regress=True):
    """Keep holdings fixed if responses are absent; never reweight observed names."""
    idx = pd.PeriodIndex(calendar.holding_month, freq="M", name="holding_month")
    columns = range(1, n_layer + 1)
    gross = pd.DataFrame(np.nan, index=idx, columns=columns)
    turnover, counts, known = gross.copy(), gross.copy(), gross.copy()
    monthly = pd.DataFrame(np.nan, index=idx, columns=["factor_ret", "t", "ic", "benchmark", "n_formed", "n_response"])
    response_groups = dict(tuple(responses.groupby("signal_month")))
    previous = {q: None for q in columns}
    holdings, reasons = [], []
    for row, period in zip(calendar.itertuples(), idx):
        g, reason = formed[row.signal_month], formation_status[row.signal_month]
        if reason == "ok":
            g, reason = assign_layers(g, n_layer, min_stocks, min_unique)
        monthly.loc[period, "n_formed"] = len(g)
        if reason != "ok":
            reasons.append(dict(holding_month=str(period), signal_month=row.signal_month, reason=reason))
            previous = {q: None for q in columns}
            continue
        holdings.append(g[["ts_code", "layer"]].assign(signal_month=row.signal_month))
        y = response_groups.get(row.signal_month, responses.iloc[:0])
        g = g.merge(y[["ts_code", "ret_fwd"]], on="ts_code", how="left", validate="one_to_one")
        observed = g[np.isfinite(g.ret_fwd)]
        monthly.loc[period, "n_response"] = len(observed)
        if len(observed) == len(g):
            monthly.loc[period, "benchmark"] = g.ret_fwd.mean()
        if regress and len(observed):
            a, t, wls_reason = frozen_wls(observed)
            monthly.loc[period, ["factor_ret", "t"]] = a, t
            if wls_reason != "ok":
                reasons.append(dict(holding_month=str(period), signal_month=row.signal_month, reason=wls_reason))
            if len(observed) >= 2 and observed.ret_fwd.nunique() > 1 and observed.f_neu.nunique() > 1:
                monthly.loc[period, "ic"] = spearmanr(observed.f_neu, observed.ret_fwd).statistic
            else:
                reasons.append(dict(holding_month=str(period), signal_month=row.signal_month, reason="undefined_ic"))
        for q in columns:
            layer = g[g.layer.eq(q)]
            names = set(layer.ts_code)
            counts.loc[period, q] = len(names)
            known.loc[period, q] = np.isfinite(layer.ret_fwd).mean()
            if known.loc[period, q] == 1:
                gross.loc[period, q] = layer.ret_fwd.mean()
            turnover.loc[period, q] = 1 if previous[q] is None else 1 - len(names & previous[q]) / len(names)
            previous[q] = names
        if len(observed) != len(g):
            reasons.append(dict(holding_month=str(period), signal_month=row.signal_month, reason="missing_response"))
    res = {col: monthly[col] for col in monthly}
    res.update(layers_gross=gross, layers_net=gross - 0.004 * turnover,
               turnover=turnover, counts=counts, known_weight=known,
               holdings=pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame(),
               reasons=pd.DataFrame(reasons, columns=["holding_month", "signal_month", "reason"]))
    res["long_short"] = course.long_short_net(res, n_layer)
    return res


def continuous(s):
    return len(s) > 0 and s.index.equals(pd.period_range(s.index[0], s.index[-1], freq="M", name=s.index.name))


def nav(s):
    if not continuous(s):
        s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    return np.r_[1., np.cumprod(1 + s.to_numpy())]


def performance(s, benchmark=None):
    keys = ["ann", "sharpe", "max_dd", "win_rate", "ann_exc", "ir", "excess_max_dd", "relative_win_rate"]
    out = dict.fromkeys(keys, np.nan)
    if not continuous(s) or not np.isfinite(s).all():
        return out
    wealth = nav(s)
    out.update(ann=wealth[-1] ** (12 / len(s)) - 1,
               sharpe=np.sqrt(12) * s.mean() / s.std(ddof=1) if len(s) > 1 and s.std(ddof=1) > 0 else np.nan,
               max_dd=np.min(wealth / np.maximum.accumulate(wealth) - 1), win_rate=s.gt(0).mean())
    if benchmark is not None and benchmark.index.equals(s.index) and np.isfinite(benchmark).all():
        excess = s - benchmark
        relative = wealth / nav(benchmark)
        out.update(ann_exc=12 * excess.mean(),
                   ir=np.sqrt(12) * excess.mean() / excess.std(ddof=1) if len(s) > 1 and excess.std(ddof=1) > 0 else np.nan,
                   excess_max_dd=np.min(relative / np.maximum.accumulate(relative) - 1),
                   relative_win_rate=excess.gt(0).mean())
    return out


def layer_statistics(res):
    return pd.DataFrame([dict(layer=q, **performance(res["layers_net"][q], res["benchmark"]))
                         for q in res["layers_net"]]).set_index("layer")


def rolling_excess(res):
    r, b = res["layers_net"], res["benchmark"]
    full = pd.period_range(r.index.min(), r.index.max(), freq="M", name=r.index.name)
    return (1 + r.reindex(full)).rolling(12, min_periods=12).apply(np.prod, raw=True).sub(
        (1 + b.reindex(full)).rolling(12, min_periods=12).apply(np.prod, raw=True), axis=0)


def c1_row(res):
    t, ic, a = [res[k].dropna() for k in ["t", "ic", "factor_ret"]]
    return dict(t_abs_mean=t.abs().mean(), t_abs_gt2=int(t.abs().gt(2).sum()), n_t=len(t),
                t_abs_gt2_rate=t.abs().gt(2).mean(), t_mean=t.mean(), factor_ret_mean=a.mean(),
                rank_ic_mean=ic.mean(), rank_ic_sd=ic.std(ddof=1),
                ic_ir=ic.mean() / ic.std(ddof=1) if len(ic) > 1 and ic.std(ddof=1) > 0 else np.nan,
                ic_positive=int(ic.gt(0).sum()), n_ic=len(ic), ic_positive_rate=ic.gt(0).mean())


def annual_table(res):
    rows = []
    for year in sorted(set(res["ic"].index.year)):
        mask = res["ic"].index.year == year
        ls, q5, bench = [res[k].loc[mask] if k != "layers_net" else res[k].loc[mask, 5]
                         for k in ["long_short", "layers_net", "benchmark"]]
        complete = continuous(ls) and all(np.isfinite(s).all() for s in [ls, q5, bench])
        rows.append(dict(year=year, n_months=len(ls), partial_year=len(ls) != 12,
                         long_short_return=nav(ls)[-1] - 1 if complete else np.nan,
                         long_short_win_rate=ls.gt(0).mean() if complete else np.nan,
                         q5_return=nav(q5)[-1] - 1 if complete else np.nan,
                         benchmark_return=nav(bench)[-1] - 1 if complete else np.nan,
                         long_excess=nav(q5)[-1] - nav(bench)[-1] if complete else np.nan,
                         rank_ic_mean=res["ic"].loc[mask].mean()))
    return pd.DataFrame(rows)
