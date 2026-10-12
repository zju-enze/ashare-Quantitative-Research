"""Monthly panel construction and empirical tests for A-share signal robustness.

All signals have a formation date; returns belong to the next calendar month.
Inputs are local Tushare-format Parquet exports, never fetched at runtime.
"""
from pathlib import Path
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

START = "20050101"
END = "20241231"
HOLDOUT = pd.Period("2018-01", freq="M")
SIGNALS = {"EP": ("ep", True), "Size": ("mktcap", False),
           "Value": ("bm", True), "Momentum": ("mom", True),
           "LowVol": ("volatility", False), "Profitability": ("op", True)}


def read_table(name, columns=None, dated=False):
    root = Path(os.environ["ASHARE_DATA_DIR"])
    filters = [("trade_date", ">=", START), ("trade_date", "<=", END)] if dated else None
    return pd.read_parquet(root / f"{name}.parquet", columns=columns, filters=filters)


def monthly_prices(daily, adjustments):
    """Adjusted returns and non-trading/gap diagnostics, before universe filtering."""
    d = daily.merge(adjustments, on=["ts_code", "trade_date"], validate="one_to_one")
    d["trade_date"] = pd.to_datetime(d["trade_date"], format="%Y%m%d")
    d = d.sort_values(["ts_code", "trade_date"])
    d["adj_close"] = d["close"] * d["adj_factor"]
    d["ym"] = d["trade_date"].dt.to_period("M")
    d["daily_ret"] = d.groupby("ts_code")["adj_close"].pct_change(fill_method=None)
    d["active"] = d["vol"] > 0
    m = d.groupby(["ts_code", "ym"], observed=True).agg(
        adj_close=("adj_close", "last"), close=("close", "last"),
        last_trade_date=("trade_date", "last"), last_vol=("vol", "last"),
        trade_days=("active", "sum"), volatility=("daily_ret", "std"))
    m = m.reset_index().sort_values(["ts_code", "ym"])
    calendar = d.groupby("ym")["trade_date"].max()
    m["trade_date"] = m["ym"].map(calendar)
    m["market_trade_days"] = m["ym"].map(d.groupby("ym")["trade_date"].nunique())
    g = m.groupby("ts_code", sort=False)
    adjacent = m["ym"].astype("int64") - g["ym"].shift(1).astype("int64") == 1
    m["ret"] = (m["adj_close"] / g["adj_close"].shift(1) - 1).where(adjacent)
    m["raw_ret"] = (m["close"] / g["close"].shift(1) - 1).where(adjacent)
    next_month = g["ym"].shift(-1)
    adjacent_next = next_month.astype("int64") - m["ym"].astype("int64") == 1
    m["ret_next"] = g["ret"].shift(-1).where(adjacent_next)
    m["return_month"] = m["ym"] + 1
    m["mom"] = m.groupby("ts_code")["ret"].transform(
        lambda x: (1 + x).rolling(11, min_periods=11).apply(np.prod, raw=True).shift(1) - 1)
    # Calendar gaps must not turn eleven observations into an eleven-month signal.
    contiguous = m["ym"].astype("int64") - g["ym"].shift(12).astype("int64") == 12
    m["mom"] = m["mom"].where(contiguous)
    final_dates = d["trade_date"].drop_duplicates().nlargest(20)
    avg_amount = d.loc[d["trade_date"].isin(final_dates)].groupby("ts_code")["amount"].mean() * 1000
    m["avg_amount_20d"] = np.nan
    last = m["ym"] == m["ym"].max()
    m.loc[last, "avg_amount_20d"] = m.loc[last, "ts_code"].map(avg_amount)
    return m


def historical_st(monthly, names):
    """Use effective historical names, not today's ST labels."""
    flag = pd.Series(False, index=monthly.index)
    st = names[names["name"].str.contains("ST", case=False, na=False)].copy()
    for col in ["start_date", "end_date", "ann_date"]:
        st[col] = pd.to_datetime(st[col], format="%Y%m%d", errors="coerce")
    st["available"] = st[["start_date", "ann_date"]].max(axis=1)
    st["end_date"] = st["end_date"].fillna(pd.Timestamp.max)
    rows_by_stock = monthly.groupby("ts_code").groups
    for r in st.itertuples():
        indices = rows_by_stock.get(r.ts_code)
        if indices is not None:
            dates = monthly.loc[indices, "trade_date"]
            flag.loc[indices] |= dates.between(r.available, r.end_date)
    return flag


def annual_versions(frame, fields):
    """Keep dated report versions; same-day conflicting versions are unusable."""
    d = frame.loc[(frame["report_type"].astype(str) == "1") &
                  frame["end_date"].astype(str).str.endswith("1231")].copy()
    for c in ["ann_date", "f_ann_date", "end_date"]:
        d[c] = pd.to_datetime(d[c], format="%Y%m%d", errors="coerce")
    d["available_date"] = d[["ann_date", "f_ann_date", "end_date"]].max(axis=1)
    d["fiscal_year"] = d["end_date"].dt.year
    keys = ["ts_code", "fiscal_year", "available_date"]
    d = d[keys + fields].dropna(subset=keys).drop_duplicates()
    conflicts = d.groupby(keys, dropna=False)[fields].nunique(dropna=False).max(axis=1) > 1
    d = d.merge(conflicts.rename("conflict"), on=keys, validate="many_to_one")
    n_conflicts = int(conflicts.sum())
    d.loc[d["conflict"], fields] = np.nan
    return d.drop_duplicates(keys)[keys + fields], n_conflicts


def reports_asof(monthly, versions, fields, fiscal_lag=1):
    left = monthly[["ts_code", "trade_date"]].copy()
    left["row_id"] = np.arange(len(left))
    left["fiscal_year"] = left["trade_date"].dt.year - fiscal_lag
    right = versions.copy()
    left["fiscal_year"] = left["fiscal_year"].astype("int64")
    right["fiscal_year"] = right["fiscal_year"].astype("int64")
    merged = pd.merge_asof(left.sort_values("trade_date"), right.sort_values("available_date"),
                           left_on="trade_date", right_on="available_date",
                           by=["ts_code", "fiscal_year"], allow_exact_matches=False)
    available = merged["available_date"].notna()
    assert (merged.loc[available, "available_date"] < merged.loc[available, "trade_date"]).all()
    return merged.sort_values("row_id")[fields + ["available_date"]].reset_index(drop=True)


def prepare_panel():
    daily = read_table("daily", ["ts_code", "trade_date", "close", "vol", "amount"], True)
    adj = read_table("adj_factor", ["ts_code", "trade_date", "adj_factor"], True)
    monthly = monthly_prices(daily, adj)
    del daily, adj
    basic = read_table("daily_basic", ["ts_code", "trade_date", "pe_ttm", "pb", "total_mv", "turnover_rate"], True)
    basic["trade_date"] = pd.to_datetime(basic["trade_date"], format="%Y%m%d")
    basic["ym"] = basic["trade_date"].dt.to_period("M")
    basic = basic.sort_values("trade_date").groupby(["ts_code", "ym"]).tail(1)
    monthly = monthly.merge(basic.drop(columns="trade_date"), on=["ts_code", "ym"], how="left", validate="one_to_one")
    del basic
    monthly["mktcap"] = monthly["total_mv"] * 1e4
    monthly["bm"] = (1 / monthly["pb"]).where(monthly["pb"] > 0)
    monthly["ep"] = (1 / monthly["pe_ttm"]).where(monthly["pe_ttm"] > 0)
    stocks = read_table("stock_basic", ["ts_code", "list_date", "list_status", "industry"])
    stocks["list_date"] = pd.to_datetime(stocks["list_date"], format="%Y%m%d")
    monthly = monthly.merge(stocks, on="ts_code", how="left", validate="many_to_one")
    monthly["industry"] = monthly["industry"].fillna("Unknown")
    monthly["is_st"] = historical_st(monthly, read_table("namechange"))
    monthly["eligible"] = (~monthly["is_st"] &
        ((monthly["trade_date"] - monthly["list_date"]).dt.days >= 120) &
        (monthly["trade_days"] >= np.minimum(15, monthly["market_trade_days"])) &
        (monthly["last_trade_date"] == monthly["trade_date"]) &
        (monthly["last_vol"] > 0) & (monthly["mktcap"] > 0))
    monthly = monthly.sort_values(["ts_code", "ym"]).reset_index(drop=True)
    monthly["mktcap_lag"] = monthly.groupby("ts_code")["mktcap"].shift(1)
    inc_fields = ["revenue", "oper_cost", "sell_exp", "admin_exp"]
    bs_fields = ["total_assets", "total_hldr_eqy_exc_min_int"]
    inc, ci = annual_versions(read_table("income", ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type"] + inc_fields), inc_fields)
    bs, cb = annual_versions(read_table("balancesheet", ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type"] + bs_fields), bs_fields)
    fi = reports_asof(monthly, inc, inc_fields)
    fb = reports_asof(monthly, bs, bs_fields)
    previous = reports_asof(monthly, bs, ["total_assets"], fiscal_lag=2)
    equity = fb["total_hldr_eqy_exc_min_int"].where(fb["total_hldr_eqy_exc_min_int"] > 0)
    # The supplied schema lacks interest expense: OP is explicitly a proxy.
    expenses = fi[["oper_cost", "sell_exp", "admin_exp"]].fillna(0).sum(axis=1)
    monthly["op"] = (fi["revenue"] - expenses) / equity
    monthly["ag"] = fb["total_assets"] / previous["total_assets"].where(previous["total_assets"] > 0) - 1
    monthly["book_equity"] = equity
    monthly["income_available"] = fi["available_date"]
    monthly["balance_available"] = fb["available_date"]
    december = monthly.loc[monthly["ym"].dt.month == 12, ["ts_code", "ym", "mktcap"]].copy()
    december["formation_year"] = december["ym"].dt.year + 1
    december = december.rename(columns={"mktcap": "december_cap"})
    monthly["formation_year"] = monthly["ym"].dt.year
    monthly = monthly.merge(december[["ts_code", "formation_year", "december_cap"]],
                            on=["ts_code", "formation_year"], how="left", validate="many_to_one")
    monthly["annual_bm"] = monthly["book_equity"] / monthly["december_cap"]
    valid = monthly["ret"].notna() & monthly["raw_ret"].notna()
    audit = {"raw_stock_months": len(monthly), "stocks": monthly["ts_code"].nunique(),
             "delisted_stocks_observed": monthly.loc[monthly["list_status"] == "D", "ts_code"].nunique(),
             "adjustment_changes_over_1pp": int((abs(monthly.loc[valid, "ret"] - monthly.loc[valid, "raw_ret"]) > .01).sum()),
             "historical_st_stock_months": int(monthly["is_st"].sum()),
             "income_conflicting_report_dates": ci, "balance_conflicting_report_dates": cb}
    panel = monthly.loc[monthly["eligible"] & (monthly["return_month"] <= pd.Period("2024-12", freq="M"))].copy()
    audit.update(eligible_stock_months=len(panel), missing_forward_returns=int(panel["ret_next"].isna().sum()),
                 usable_stock_months=int(panel["ret_next"].notna().sum()))
    assert (panel["return_month"].astype("int64") - panel["ym"].astype("int64") == 1).all()
    return monthly, panel, audit


def standardize(series):
    clipped = series.clip(series.quantile(.01), series.quantile(.99))
    return (clipped - clipped.mean()) / clipped.std(ddof=1)


def mean_hac(series, lags=6):
    s = pd.Series(series).dropna().astype(float).sort_index()
    calendar = pd.period_range(s.index.min(), s.index.max(), freq="M")
    # Missing labels have no score contribution; they must not collapse calendar lags.
    residual = (s.reindex(calendar)-s.mean()).fillna(0).to_numpy()
    variance = residual @ residual
    for lag in range(1, min(lags, len(residual)-1)+1):
        variance += 2*(1-lag/(lags+1))*(residual[lag:] @ residual[:-lag])
    se = np.sqrt(variance)/len(s)
    t_value = s.mean()/se
    return {"months": len(s), "mean": float(s.mean()), "t_hac": float(t_value),
            "p_hac": float(2*stats.norm.sf(abs(t_value))), "se_hac": float(se)}


def fama_macbeth(panel, signal):
    """Direction-aligned characteristic regressions; size cannot control itself."""
    column, long_top = SIGNALS[signal]
    p = panel.dropna(subset=[column, "ret_next", "mktcap"]).copy()
    characteristic = np.log(p[column]) if signal == "Size" else p[column]
    p["signal_z"] = characteristic.groupby(p["ym"]).transform(standardize) * (1 if long_top else -1)
    p["size_z"] = p.groupby("ym")["mktcap"].transform(lambda x: standardize(np.log(x)))
    rows = []
    for ym, d in p.groupby("ym"):
        if len(d) < 100:
            continue
        industries = pd.get_dummies(d["industry"], drop_first=True, dtype=float).to_numpy()
        f = d["signal_z"].to_numpy()
        size = d["size_z"].to_numpy()
        y = d["ret_next"].to_numpy()
        controls = np.column_stack([np.ones(len(d)), industries] if signal == "Size"
                                   else [np.ones(len(d)), size, industries])
        neutral = f - controls @ np.linalg.lstsq(controls, f, rcond=None)[0]
        row = {"return_month": ym + 1, "stocks": len(d),
               "raw_ic": stats.spearmanr(f, y).statistic,
               "neutral_ic": stats.spearmanr(neutral, y).statistic}
        designs = {"Signal": np.column_stack([np.ones(len(d)), f]),
                   "Industry_controlled": np.column_stack([controls, f])}
        if signal != "Size":
            designs["Size_controlled"] = np.column_stack([np.ones(len(d)), f, size])
        for name, x in designs.items():
            row[name] = np.linalg.lstsq(x, y, rcond=None)[0][-1 if name == "Industry_controlled" else 1]
        rows.append(row)
    coefficients = pd.DataFrame(rows).set_index("return_month")
    summary = []
    for period, values in [("Full", coefficients), ("Development_2005_2017", coefficients.loc[coefficients.index < HOLDOUT]),
                           ("Holdout_2018_2024", coefficients.loc[coefficients.index >= HOLDOUT])]:
        for name in [*designs, "raw_ic", "neutral_ic"]:
            r = mean_hac(values[name])
            r.update(period=period, signal=signal, specification=name,
                     first_month=str(values.index.min()), last_month=str(values.index.max()))
            summary.append(r)
    return p, coefficients, pd.DataFrame(summary)


def quintile_returns(panel, column, long_top=True):
    rows = []
    for ym, d in panel.dropna(subset=[column]).groupby("ym"):
        if len(d) < 100 or d[column].nunique() < 5:
            continue
        q = pd.qcut(d[column], 5, labels=False, duplicates="drop")
        means = d.groupby(q)["ret_next"].mean()
        if len(means) != 5:
            continue
        spread = means.iloc[-1] - means.iloc[0]
        rows.append({"return_month": ym + 1, **{f"Q{i+1}": means.iloc[i] for i in range(5)},
                     "spread": spread if long_top else -spread, "stocks": len(d),
                     "missing_forward_returns": int(d["ret_next"].isna().sum())})
    return pd.DataFrame(rows).set_index("return_month")


def signal_tests(panel):
    portfolios = {name: quintile_returns(panel, col, direction) for name, (col, direction) in SIGNALS.items()}
    returns = pd.DataFrame({name: frame["spread"] for name, frame in portfolios.items()})
    rows = []
    for period, values in [("Full", returns), ("Development_2005_2017", returns.loc[returns.index < HOLDOUT]),
                           ("Holdout_2018_2024", returns.loc[returns.index >= HOLDOUT])]:
        period_rows = []
        for name in SIGNALS:
            s = values[name].dropna()
            r = mean_hac(s)
            r.update(period=period, signal=name, ann_mean=s.mean()*12,
                     sharpe=s.mean()/s.std(ddof=1)*np.sqrt(12))
            period_rows.append(r)
        pvals = [r["p_hac"] for r in period_rows]
        bh = multipletests(pvals, method="fdr_bh")[1]
        holm = multipletests(pvals, method="holm")[1]
        for r, q, h in zip(period_rows, bh, holm):
            r.update(q_bh=float(q), p_holm=float(h))
        rows.extend(period_rows)
    return portfolios, returns, pd.DataFrame(rows)


def block_bootstrap(returns, repetitions=10000, block_length=None):
    s = pd.Series(returns).sort_index()
    s = s.loc[s.first_valid_index():s.last_valid_index()]
    x = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M")).to_numpy()
    n = len(x)
    length = block_length or int(np.ceil(n ** (1/3)))
    rng = np.random.default_rng(42)
    starts = rng.integers(0, n-length+1, size=(repetitions, int(np.ceil(n/length))))
    samples = x[(starts[..., None] + np.arange(length)).reshape(repetitions, -1)[:, :n]]
    # Keep missing calendar positions inside blocks rather than joining distant months.
    sharpe = np.nanmean(samples, axis=1) / np.nanstd(samples, axis=1, ddof=1) * np.sqrt(12)
    lo, hi = np.quantile(sharpe, [.025, .975])
    return {"months": int(np.isfinite(x).sum()), "calendar_months": n,
            "missing_months": int(np.isnan(x).sum()),
            "first_month": str(s.index.min()), "last_month": str(s.index.max()),
            "repetitions": repetitions, "block_length": length,
            "sharpe": float(np.nanmean(x)/np.nanstd(x, ddof=1)*np.sqrt(12)),
            "ci_low": float(lo), "ci_high": float(hi)}


def permutation_ic(panel, repetitions=2000):
    """Within-month exchangeability diagnostic; not a replacement for HAC inference."""
    rng = np.random.default_rng(42)
    simulated = np.zeros(repetitions)
    observed = []
    for _, d in panel.dropna(subset=["ep", "ret_next"]).groupby("ym"):
        if len(d) < 100:
            continue
        f = stats.rankdata(d["ep"])
        y = stats.rankdata(d["ret_next"])
        f -= f.mean()
        y -= y.mean()
        denominator = np.linalg.norm(f)*np.linalg.norm(y)
        shuffled = rng.permuted(np.tile(y, (repetitions, 1)), axis=1)
        simulated += shuffled @ f / denominator
        observed.append(float(y @ f / denominator))
    simulated /= len(observed)
    value = float(np.mean(observed))
    p = (1 + np.sum(abs(simulated) >= abs(value))) / (repetitions + 1)
    return {"months": len(observed), "repetitions": repetitions, "mean_ic": value,
            "p_exchangeability": float(p)}


def risk_free():
    d = read_table("shibor", ["date", "1y"])
    d["ym"] = pd.to_datetime(d["date"], format="%Y%m%d").dt.to_period("M")
    return d.groupby("ym")["1y"].mean()/1200


def annual_sort_returns(panel, monthly, characteristic, bins=3):
    assignments = []
    for ym, d in panel.loc[panel["ym"].dt.month == 6].dropna(subset=[characteristic, "mktcap"]).groupby("ym"):
        if len(d) < 200:
            continue
        d = d.copy()
        if bins == 3:
            d["size_group"] = (d["mktcap"] > d["mktcap"].median()).astype(int)
            low, high = d[characteristic].quantile([.3, .7])
            d["char_group"] = pd.cut(d[characteristic], [-np.inf, low, high, np.inf], labels=False)
        else:
            d["size_group"] = pd.qcut(d["mktcap"], 5, labels=False)
            d["char_group"] = pd.qcut(d[characteristic], 5, labels=False)
        for step in range(1, 13):
            a = d[["ts_code", "size_group", "char_group"]].copy()
            a["ym"] = ym + step
            assignments.append(a)
    assignment = pd.concat(assignments, ignore_index=True)
    held = assignment.merge(monthly[["ts_code", "ym", "ret", "mktcap_lag"]],
                            on=["ts_code", "ym"], how="left", validate="one_to_one")
    held = held.loc[held["ym"] <= monthly["ym"].max()]
    coverage = held.groupby("ym").agg(assigned=("ts_code", "size"), available=("ret", "count"))
    held = held.dropna(subset=["ret", "mktcap_lag"])
    held = held.loc[held["mktcap_lag"] > 0].copy()
    held["weighted_return"] = held["ret"]*held["mktcap_lag"]
    grouped = held.groupby(["ym", "size_group", "char_group"])[["weighted_return", "mktcap_lag"]].sum()
    port = (grouped["weighted_return"]/grouped["mktcap_lag"]).unstack(["size_group", "char_group"])
    columns = pd.MultiIndex.from_product([range(2 if bins == 3 else 5), range(bins)])
    return port.reindex(columns=columns).dropna(), coverage


def grs_test(test_returns, factors):
    """Unbiased covariance convention, matched to CRAN GRS.test (Wu statistic)."""
    joined = test_returns.join(factors, how="inner", lsuffix="_asset").dropna()
    y = joined.iloc[:, :test_returns.shape[1]].to_numpy()
    f = joined.iloc[:, test_returns.shape[1]:].to_numpy()
    t, n = y.shape
    k = f.shape[1]
    if t <= n+k:
        raise ValueError("GRS requires T > N + K")
    x = np.column_stack([np.ones(t), f])
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    residuals = y-x @ coefficients
    sigma = residuals.T @ residuals/(t-k-1)
    centered = f-f.mean(axis=0)
    omega = centered.T @ centered/(t-1)
    alpha = coefficients[0]
    numerator = alpha @ np.linalg.solve(sigma, alpha)
    denominator = 1 + f.mean(axis=0) @ np.linalg.solve(omega, f.mean(axis=0))
    statistic = t/n*(t-n-k)/(t-k-1)*numerator/denominator
    return {"months": t, "assets": n, "factors": k, "grs": float(statistic),
            "p_value": float(stats.f.sf(statistic, n, t-n-k)),
            "mean_abs_alpha": float(np.abs(alpha).mean())}, alpha


def asset_pricing(panel, monthly):
    p = panel.dropna(subset=["ret_next", "mktcap"]).copy()
    p["weighted_return"] = p["ret_next"]*p["mktcap"]
    sums = p.groupby("return_month")[["weighted_return", "mktcap"]].sum()
    rf = risk_free().reindex(sums.index).fillna(.03/12)
    market = sums["weighted_return"]/sums["mktcap"] - rf
    value, coverage = annual_sort_returns(panel, monthly, "annual_bm")
    profit, _ = annual_sort_returns(panel, monthly, "op")
    invest, _ = annual_sort_returns(panel, monthly, "ag")
    def smb(ports):
        return ports[0].mean(axis=1)-ports[1].mean(axis=1)
    def high_low(ports):
        return (ports[(0, 2)]+ports[(1, 2)]-ports[(0, 0)]-ports[(1, 0)])/2
    ff3 = pd.DataFrame({"MKT": market, "SMB": smb(value), "HML": high_low(value)}).dropna()
    ff5 = pd.DataFrame({"MKT": market, "SMB": (smb(value)+smb(profit)+smb(invest))/3,
                        "HML": high_low(value), "RMW": high_low(profit), "CMA": -high_low(invest)}).dropna()
    tests, _ = annual_sort_returns(panel, monthly, "annual_bm", bins=5)
    tests.columns = [f"S{a+1}_V{b+1}" for a, b in tests.columns]
    tests = tests.sub(rf.reindex(tests.index).fillna(.03/12), axis=0)
    common = tests.index.intersection(ff3.index).intersection(ff5.index)
    rows, alphas = [], {}
    for name, factors in [("CAPM", ff3[["MKT"]]), ("FF3_adapted", ff3), ("FF5_adapted", ff5)]:
        r, alpha = grs_test(tests.loc[common], factors.loc[common])
        r.update(model=name, start=str(common.min()), end=str(common.max()), reject_5pct=r["p_value"] < .05)
        rows.append(r)
        alphas[name] = alpha
    return ff3, ff5, tests, pd.DataFrame(rows), pd.DataFrame(alphas, index=tests.columns), coverage


def beta_pricing(monthly, panel):
    rf = risk_free().reindex(monthly["ym"].unique()).fillna(.03/12)
    d = monthly.copy()
    d["excess"] = d["ret"]-d["ym"].map(rf)
    y = d.pivot(index="ym", columns="ts_code", values="excess").sort_index()
    observed = panel.dropna(subset=["ret_next", "mktcap"]).copy()
    observed["weighted"] = observed["ret_next"]*observed["mktcap"]
    totals = observed.groupby("return_month")[["weighted", "mktcap"]].sum()
    x = (totals["weighted"]/totals["mktcap"]-rf.reindex(totals.index)).reindex(y.index)
    valid = y.notna().mul(x.notna(), axis=0)
    xv = valid.mul(x, axis=0).fillna(0)
    yv = y.where(valid, 0)
    count = valid.rolling(60, min_periods=60).sum()
    sx = xv.rolling(60, min_periods=60).sum()
    sy = yv.rolling(60, min_periods=60).sum()
    sxy = yv.mul(x.fillna(0), axis=0).rolling(60, min_periods=60).sum()
    sx2 = xv.pow(2).rolling(60, min_periods=60).sum()
    beta = ((sxy-sx*sy/count)/(sx2-sx.pow(2)/count)).where(count >= 36)
    beta.index.name = "ym"
    beta = beta.stack().rename("beta").reset_index()
    p = panel.merge(beta, on=["ts_code", "ym"], validate="one_to_one").dropna(subset=["ret_next", "bm"])
    p["target_excess"] = p["ret_next"]-p["return_month"].map(rf)
    rows = []
    for ym, g in p.groupby("return_month"):
        if len(g) < 100:
            continue
        for name, predictors in [("Beta", g[["beta"]].to_numpy()),
                                 ("Beta_Size_Value", np.column_stack([g["beta"], np.log(g["mktcap"]), np.log(g["bm"])]))]:
            xmat = np.column_stack([np.ones(len(g)), predictors])
            coefficient = np.linalg.lstsq(xmat, g["target_excess"], rcond=None)[0][1]
            rows.append({"return_month": ym, "specification": name, "beta_price": coefficient})
    coefficients = pd.DataFrame(rows)
    summary = []
    for name, g in coefficients.groupby("specification"):
        summary.append({"specification": name, **mean_hac(g.set_index("return_month")["beta_price"])})
    return coefficients, pd.DataFrame(summary)
