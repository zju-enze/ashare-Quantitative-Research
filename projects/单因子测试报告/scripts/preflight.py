"""P0/P1 input audit only: no factor fitting, sorting, portfolio returns or data writes."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def make_calendar(days, cutoff, start_month="2007-01"):
    days = pd.DatetimeIndex(pd.to_datetime(sorted(set(days)), format="%Y%m%d"))
    cutoff = pd.Timestamp(cutoff)
    last_by_month = pd.Series(days, index=days.to_period("M")).groupby(level=0).max()
    rows = []
    for month in pd.period_range(start_month, cutoff.to_period("M"), freq="M"):
        signal = last_by_month.get(month, pd.NaT)
        next_signal = last_by_month.get(month + 1, pd.NaT)
        # A later observed month is needed to establish a complete calendar month.
        month_known = month < days[-1].to_period("M")
        next_known = month + 1 < days[-1].to_period("M")
        i = days.searchsorted(signal, side="right") if pd.notna(signal) else len(days)
        j = days.searchsorted(next_signal, side="right") if pd.notna(next_signal) else len(days)
        entry = days[i] if month_known and i < len(days) else pd.NaT
        exit_date = days[j] if next_known and j < len(days) else pd.NaT
        complete_signal = bool(month_known and signal <= cutoff)
        complete_holding = bool(complete_signal and pd.notna(exit_date) and exit_date <= cutoff)
        fmt = lambda x: x.strftime("%Y%m%d") if pd.notna(x) else ""
        rows.append(dict(signal_month=str(month), signal_date=fmt(signal) if month_known else "",
                         entry_date=fmt(entry), next_signal_date=fmt(next_signal) if next_known else "",
                         exit_date=fmt(exit_date), holding_month=entry.strftime("%Y-%m") if pd.notna(entry) else "",
                         signal_complete=complete_signal, holding_complete=complete_holding,
                         missing_endpoint_reason="" if complete_holding else
                         ("signal_after_common_cutoff" if not complete_signal else "exit_after_common_cutoff")))
    return pd.DataFrame(rows)


def bp_reason(values, row_present):
    values = np.asarray(values, dtype=float)
    return np.select([~np.asarray(row_present), np.isnan(values), ~np.isfinite(values),
                      values == 0, values < 0],
                     ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_zero", "pb_negative"],
                     default="valid")


def positive(values):
    return np.isfinite(values) & (values > 0)


def industry_at(members, date):
    # Local intervals end on the old classification's final trading day.
    hits = members[(members.in_date <= date) & (members.end >= date)]
    counts = hits.groupby("ts_code").l1_name.nunique()
    # Several interval versions may agree on the same L1 at this date.
    one = hits[hits.ts_code.isin(counts[counts.eq(1)].index)]
    labels = one.drop_duplicates("ts_code").set_index("ts_code").l1_name
    return labels, set(counts[counts.gt(1)].index)


def check_pb_samples(data, db, private):
    codes = ["000001.SZ", "000651.SZ", "600036.SH"]
    fina = pq.read_table(data / "fina_indicator.parquet", columns=["ts_code", "ann_date", "end_date", "bps"],
                         filters=[("ts_code", "in", codes)]).to_pandas()
    rows = []
    for code in codes:
        for year in ["2007", "2015", "2025"]:
            sample = db[db.ts_code.eq(code) & db.trade_date.str.startswith(year + "12")]
            if sample.empty:
                continue
            point = sample.iloc[-1]
            known = fina[fina.ts_code.eq(code) & fina.ann_date.le(point.trade_date) & fina.bps.notna()]
            if known.empty:
                rows.append(dict(ts_code=code, signal_date=point.trade_date, status="no_announced_bps"))
                continue
            latest = known[known.end_date.eq(known.end_date.max())]
            latest = latest[latest.ann_date.eq(latest.ann_date.max())]
            vals = latest.bps.unique()
            rows.append(dict(ts_code=code, signal_date=point.trade_date, pb=point.pb,
                             implied_bps=point.close/point.pb, financial_ann_date=latest.ann_date.iloc[0],
                             financial_end_date=latest.end_date.iloc[0], bps_versions=len(vals),
                             bps=float(vals[0]) if len(vals) == 1 else np.nan,
                             status="comparison_only_not_PIT_proof"))
    sample = pd.DataFrame(rows)
    assert (sample.financial_ann_date.dropna() <= sample.loc[sample.financial_ann_date.notna(), "signal_date"]).all()
    sample.to_csv(private / "pb_financial_samples.csv", index=False, encoding="utf-8-sig")
    comparable = sample.dropna(subset=["bps", "implied_bps"])
    relative = (comparable.implied_bps/comparable.bps - 1).abs()
    return dict(preselected_codes=codes, preselected_years=[2007, 2015, 2025], observations=len(sample),
                unambiguous_bps_observations=len(comparable),
                abs_relative_difference_min=float(relative.min()), abs_relative_difference_max=float(relative.max()),
                limitation="PB excludes other equity instruments per current vendor definition; historical revision policy unverified")


def main(course):
    root = Path(__file__).resolve().parents[1]
    out = root / "outputs" / "preflight"
    private = root / ".local" / "preflight"
    out.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(course))
    from qfbook.data import loader
    from qfbook.factor import single_test
    data = loader.get_data_dir().resolve()
    assert data == (course / "data" / "offline").resolve(), "Unexpected data override"
    raw_files = sorted(data.glob("*.parquet")) + [data / "metadata.json"]
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in raw_files}
    summary = {"kind": "P0_P1_preflight_not_factor_results", "checked_at": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), "course_root": str(course),
               "data_root": str(data), "python": sys.version, "executable": sys.executable,
               "single_test_source": single_test.__file__, "source_is_git_checkout": False,
               "versions": {p: importlib.metadata.version(p) for p in
                            ["numpy", "pandas", "pyarrow", "scipy", "statsmodels", "matplotlib"]}}
    checks, inventory = [], []

    def save(frame, name, local=False):
        frame.to_csv((private if local else out) / name, index=False, encoding="utf-8-sig")

    def keyed(frame, keys, name, scope):
        bad = frame.duplicated(keys, keep=False) | frame[keys].isna().any(axis=1)
        checks.append(dict(dataset=name, scope=scope, rows_checked=len(frame),
                           duplicate_or_null_key_rows=int(bad.sum())))
        if bad.any():
            save(frame.loc[bad], name + "_ambiguous_keys.csv", local=True)
        # Ambiguous keys remain a recorded blocker; never silently choose their values.
        return frame.loc[~bad].copy()

    for p in sorted(data.glob("*.parquet")):
        f = pq.ParquetFile(p)
        ranges = {}
        for col in [c for c in f.schema_arrow.names if c.endswith("date") or c == "date"]:
            index = f.schema_arrow.names.index(col)
            stats = [f.metadata.row_group(i).column(index).statistics for i in range(f.metadata.num_row_groups)]
            stats = [s for s in stats if s and s.has_min_max]
            if stats:
                ranges[col] = [str(min(s.min for s in stats)), str(max(s.max for s in stats))]
        inventory.append(dict(file=p.name, path=str(p), bytes=p.stat().st_size,
                              mtime=pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC").isoformat(),
                              rows=f.metadata.num_rows,
                              schema=json.dumps({v.name: str(v.type) for v in f.schema_arrow}, ensure_ascii=False),
                              date_ranges=json.dumps(ranges, ensure_ascii=False)))
    save(pd.DataFrame(inventory), "data_inventory.csv")
    ranges = {x["file"]: json.loads(x["date_ranges"]) for x in inventory}
    primary_end = min(ranges[n + ".parquet"]["trade_date"][1] for n in ["daily", "daily_basic", "adj_factor"])

    index_daily = keyed(pd.read_parquet(data / "index_daily.parquet"), ["ts_code", "trade_date"],
                        "index_daily", "all_rows")
    sse_days = set(loader.load_index_daily("000001.SH", start_date="2005-01-01").trade_date)
    sz_days = set(loader.load_index_daily("399001.SZ", start_date="2005-01-01").trade_date)
    ext = course / "data" / "external" / "baostock"
    bank_days = []
    for name in ["daily_sh.600036.csv", "daily_sh.601166.csv"]:
        d = pd.read_csv(ext / name, dtype={"date": str, "tradestatus": str})
        bank_days.append(set(d.loc[d.tradestatus.eq("1"), "date"].str.replace("-", "")))
    tail_days = {d for d in bank_days[0] & bank_days[1] if d > max(sse_days)}
    days = sse_days | tail_days
    independent = pd.read_csv(ext / "trade_calendar_2023_2025.csv")
    independent_days = set(independent.loc[independent.is_trading_day.eq(1), "calendar_date"].str.replace("-", ""))
    summary["calendar_validation"] = dict(
        sse_sz_symmetric_difference=len(sse_days ^ sz_days),
        baostock_2023_2025_mismatches=len({d for d in sse_days if "20230101" <= d <= "20251231"} ^ independent_days),
        primary_end=primary_end, observed_calendar_end=max(days),
        tail_source="intersection of local BaoStock 600036/601166 tradestatus=1 dates; calendar evidence only",
        independent_full_window_calendar=False)
    calendar = make_calendar(days, primary_end)
    calendar["calendar_source"] = "local SSE index; SZ cross-check; BaoStock calendar 2023-2025; two-stock dates after index cutoff"
    for code in ["000300.SH", "000905.SH"]:
        valid_dates = set(index_daily.loc[index_daily.ts_code.eq(code) & positive(index_daily.close), "trade_date"])
        calendar[code + "_endpoints_present"] = calendar.entry_date.isin(valid_dates) & calendar.exit_date.isin(valid_dates)
    calendar["market_dates_complete"] = calendar.holding_complete & calendar["000300.SH_endpoints_present"] & calendar["000905.SH_endpoints_present"]
    save(calendar, "calendar_audit.csv")
    complete = calendar[calendar.signal_complete]
    summary["calendar"] = dict(signal_months=len(complete), complete_holding_periods=int(calendar.holding_complete.sum()),
                               last_signal=complete.iloc[-1].signal_date,
                               last_complete=calendar.loc[calendar.holding_complete].iloc[-1].to_dict())
    signal_dates = complete.signal_date.tolist()
    endpoints = sorted(set(complete.entry_date) | set(complete.exit_date))

    print("Reading only monthly signals and entry/exit endpoint columns", flush=True)
    dbcols = ["ts_code", "trade_date", "pb", "close", "total_mv", "circ_mv", "total_share", "float_share"]
    db = keyed(pq.read_table(data / "daily_basic.parquet", columns=dbcols,
                            filters=[("trade_date", "in", signal_dates)]).to_pandas(),
               ["ts_code", "trade_date"], "daily_basic", "all complete candidate signal dates")
    prices = keyed(pq.read_table(data / "daily.parquet", columns=["ts_code", "trade_date", "close"],
                                filters=[("trade_date", "in", sorted(set(endpoints) | set(signal_dates)))]).to_pandas(),
                   ["ts_code", "trade_date"], "daily", "candidate signal and endpoint dates")
    factors = keyed(pq.read_table(data / "adj_factor.parquet", columns=["ts_code", "trade_date", "adj_factor"],
                                 filters=[("trade_date", "in", endpoints)]).to_pandas(),
                    ["ts_code", "trade_date"], "adj_factor", "candidate entry and exit dates")
    basic = keyed(loader.load_stock_basic(), ["ts_code"], "stock_basic", "all_rows")
    names = keyed(loader.load_namechange(), ["ts_code", "start_date", "name"], "namechange", "all_rows")
    members = pd.read_parquet(data / "industry_sw_member.parquet")
    summary["industry_same_start_interval_variant_rows"] = int(members.duplicated(["ts_code", "l3_code", "in_date"], keep=False).sum())
    members["end"] = members.out_date.fillna("99991231")
    members = keyed(members, ["ts_code", "l3_code", "in_date", "end"], "industry_sw_member", "all interval versions")
    weights = keyed(pd.read_parquet(data / "index_weight.parquet"),
                    ["index_code", "trade_date", "con_code"], "index_weight", "all_rows")
    susp = keyed(loader.load_suspend(start_date="2005-01-01"),
                 ["ts_code", "trade_date", "suspend_type"], "suspend_d", "all_rows")
    save(pd.DataFrame(checks), "key_checks.csv")
    names["end"] = names.end_date.fillna("99991231")
    members["end"] = members.out_date.fillna("99991231")
    basic["end"] = basic.delist_date.fillna("99991231")
    basic = basic.set_index("ts_code", drop=False)
    summary["lifecycle"] = dict(rows=len(basic), status=basic.list_status.value_counts().to_dict(),
                                exchanges=basic.ts_code.str[-2:].value_counts().to_dict(),
                                price_codes_absent_from_basic=len(set(prices.ts_code) - set(basic.index)),
                                valuation_codes_absent_from_basic=len(set(db.ts_code) - set(basic.index)))
    summary["suspension"] = dict(first_date=susp.trade_date.min(), last_date=susp.trade_date.max(),
                                 intraday_rows=int(susp.suspend_timing.notna().sum()),
                                 rule="exclude every recorded entry-date S, including intraday; absent records before coverage are unknown")
    summary["industry"] = dict(l1_labels=sorted(members.l1_name.unique().tolist()),
                               labels=len(members.l1_name.unique()),
                               is_new=members.is_new.value_counts().to_dict(),
                               source_classification_version="not recorded in offline metadata")
    transitions = []
    for stock, intervals in members.groupby("ts_code"):
        for old in intervals[intervals.out_date.notna()].itertuples(index=False):
            later = intervals[intervals.in_date.gt(old.in_date) & intervals.in_date.ge(old.out_date)]
            following_days = [day for day in sorted(sse_days) if day > old.out_date]
            if len(later) and following_days and "20070101" <= old.out_date <= primary_end:
                transitions.append(dict(ts_code=stock, old_out=old.out_date, new_in=later.in_date.min(),
                                        next_trade_day=following_days[0]))
    transition_frame = pd.DataFrame(transitions)
    save(transition_frame, "industry_interval_transitions.csv", local=True)
    summary["industry_boundary"] = dict(transitions_checked=len(transition_frame),
        next_trade_day_matches=int(transition_frame.new_in.eq(transition_frame.next_trade_day).sum()),
        same_date_new_interval=int(transition_frame.new_in.eq(transition_frame.old_out).sum()),
        local_interval_convention="in_date <= signal_date <= out_date; open intervals have no end",
        caveat="The interval audit does not establish historically unrevised classification vintages")
    known_codes = set(basic.index)
    unknown = sorted((set(prices.ts_code) | set(db.ts_code) | set(weights.con_code)) - known_codes)
    save(pd.DataFrame({"ts_code": unknown}), "codes_absent_from_basic.csv", local=True)
    numeric = []
    for label, frame, col in [("daily", prices, "close"), ("adj_factor", factors, "adj_factor"),
                               ("daily_basic", db, "total_mv"), ("daily_basic", db, "circ_mv")]:
        numeric.append(dict(dataset=label, field=col, rows=len(frame), invalid=int((~positive(frame[col])).sum())))
    save(pd.DataFrame(numeric), "numeric_checks.csv")
    units = {}
    for cap, shares in [("total_mv", "total_share"), ("circ_mv", "float_share")]:
        delta = ((db[cap] - db.close * db[shares]).abs() / db[cap]).replace([np.inf, -np.inf], np.nan)
        units[cap] = dict(comparable=int(delta.notna().sum()), max_relative_gap=float(delta.max()),
                          median_relative_gap=float(delta.median()), above_0_1_percent=int(delta.gt(0.001).sum()))
    summary["market_cap_unit_check"] = units
    summary["pb_financial_samples"] = check_pb_samples(data, db, private)

    by_db = {date: g.set_index("ts_code") for date, g in db.groupby("trade_date")}
    by_price = {date: g.set_index("ts_code").close for date, g in prices.groupby("trade_date")}
    by_adj = {date: g.set_index("ts_code").adj_factor for date, g in factors.groupby("trade_date")}
    by_susp = {date: set(g.ts_code) for date, g in susp[susp.suspend_type.eq("S")].groupby("trade_date")}
    by_weight = {code: {date: g for date, g in sub.groupby("trade_date")}
                 for code, sub in weights.groupby("index_code") if code in ["000300.SH", "000905.SH"]}
    empty = pd.Series(dtype=float)
    flows, histories, exchange_flows, industry_counts, endpoint_issues, state_issues = [], [], [], [], [], []
    for row in complete.itertuples(index=False):
        signal, entry, exit_date = row.signal_date, row.entry_date, row.exit_date
        active = basic[(basic.list_date <= signal) & (basic.end > signal)]
        current_names = names[(names.start_date <= signal) & (names.end >= signal)]
        st = set(current_names.loc[current_names.name.str.contains(r"ST|PT", case=False, na=False), "ts_code"])
        named = set(current_names.ts_code)
        halted = by_susp.get(entry, set())
        industry, ambiguous_industry = industry_at(members, signal)
        candidates = active.copy()
        candidates["st"] = candidates.index.isin(st)
        candidates["entry_halt"] = candidates.index.isin(halted)
        candidates["name_unknown"] = ~candidates.index.isin(named)
        candidates["industry"] = industry.reindex(candidates.index)
        candidates["industry_ambiguous"] = candidates.index.isin(ambiguous_industry)
        val = by_db.get(signal, pd.DataFrame(columns=dbcols).set_index("ts_code"))
        candidates["bp_reason"] = bp_reason(val.pb.reindex(candidates.index).to_numpy(), candidates.index.isin(val.index))
        candidates["cap_ok"] = positive(val.total_mv.reindex(candidates.index)) & positive(val.circ_mv.reindex(candidates.index))
        candidates["U"] = ~candidates.st & ~candidates.entry_halt
        candidates["F"] = candidates.U & candidates.bp_reason.eq("valid")
        candidates["S"] = candidates.F & candidates.cap_ok & candidates.industry.notna()
        # Endpoint observability is joined only after U/F/S have been fixed.
        for prefix, date in [("entry", entry), ("exit", exit_date)]:
            candidates[prefix + "_price_ok"] = positive(by_price.get(date, empty).reindex(candidates.index))
            candidates[prefix + "_adj_ok"] = positive(by_adj.get(date, empty).reindex(candidates.index))
        candidates["Y"] = candidates.S & candidates.entry_price_ok & candidates.exit_price_ok & candidates.entry_adj_ok & candidates.exit_adj_ok
        susp_covered = susp.trade_date.min() <= entry <= susp.trade_date.max()
        pools = {"ALL_A": set(active.index)}
        raw_sizes = {"ALL_A": len(active)}
        for code, snapshots in by_weight.items():
            eligible = [d for d in snapshots if d <= signal]
            date = max(eligible) if eligible else ""
            snapshot = snapshots.get(date, pd.DataFrame(columns=weights.columns))
            ids = set(snapshot.con_code)
            pools[code] = ids & set(active.index)
            raw_sizes[code] = len(ids)
            histories.append(dict(pool=code, signal_month=row.signal_month, snapshot_date=date,
                                  snapshot_age_days=(pd.Timestamp(signal)-pd.Timestamp(date)).days if date else np.nan,
                                  same_month=bool(date and date[:6] == signal[:6]), members=len(ids),
                                  weight_sum=float(snapshot.weight.sum()), absent_basic=len(ids-known_codes),
                                  outside_lifecycle=len(ids-set(active.index)),
                                  changed_from_previous=0 if not eligible[:-1] else
                                  len(ids ^ set(snapshots[sorted(eligible)[-2]].con_code))))
        for pool, ids in pools.items():
            g = candidates.loc[candidates.index.isin(ids)]
            u, f, s = g[g.U], g[g.F], g[g.S]
            rec = dict(pool=pool, signal_month=row.signal_month, holding_month=row.holding_month,
                       historical_members=raw_sizes[pool], lifecycle_members=len(g),
                       st_pt_excluded=int(g.st.sum()), entry_suspended_excluded=int((~g.st & g.entry_halt).sum()),
                       U=len(u), F=len(f), S=len(s), Y=int(s.Y.sum()) if row.holding_complete else np.nan,
                       bp_coverage_f_over_u=len(f)/len(u) if len(u) else np.nan,
                       unknown_name_in_U=int(u.name_unknown.sum()), industry_missing_in_F=int(f.industry.isna().sum()),
                       industry_conflicting_in_F=int(f.industry_ambiguous.sum()),
                       cap_invalid_after_industry=int((f.industry.notna() & ~f.cap_ok).sum()),
                       suspension_period_covered=susp_covered, holding_complete=row.holding_complete,
                       scope_status="unfrozen_input_audit_not_approved_universe")
            for reason in ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_zero", "pb_negative"]:
                rec[reason] = int(u.bp_reason.eq(reason).sum())
            for endpoint in ["entry_price", "exit_price", "entry_adj", "exit_adj"]:
                rec[endpoint + "_unavailable_in_S"] = int((~s[endpoint + "_ok"]).sum()) if row.holding_complete else np.nan
            assert rec["F"] + sum(rec[x] for x in ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_zero", "pb_negative"]) == rec["U"]
            assert rec["S"] + rec["industry_missing_in_F"] + rec["cap_invalid_after_industry"] == rec["F"]
            flows.append(rec)
        for exchange, g in candidates.groupby(candidates.index.str[-2:]):
            exchange_flows.append(dict(signal_month=row.signal_month, exchange=exchange, base=len(g),
                                       U=int(g.U.sum()), F=int(g.F.sum()), S=int(g.S.sum()),
                                       Y=int(g.Y.sum()) if row.holding_complete else np.nan))
        s = candidates[candidates.S]
        for name, n in s.groupby("industry").size().items():
            industry_counts.append(dict(signal_month=row.signal_month, industry=name, S=int(n), c4_min25=n >= 25))
        state_issues.append(dict(signal_month=row.signal_month,
                                 overlapping_name_codes=int(current_names.groupby("ts_code").size().gt(1).sum()),
                                 conflicting_industry_codes=len(ambiguous_industry),
                                 industry_out_date_on_signal=int(members.out_date.eq(signal).sum()),
                                 S_on_industry_end_date=int((candidates.S & candidates.index.isin(
                                     members.loc[members.out_date.eq(signal), "ts_code"])).sum()),
                                 old_monthly_st_extra_exclusions=len(set(names.loc[names.name.str.contains("ST", na=False) &
                                     names.start_date.str[:6].le(signal[:6]) & names.end.str[:6].ge(signal[:6]), "ts_code"]) - st)))
        if row.holding_complete:
            bad = s[~s.Y].copy()
            bad["signal_month"] = row.signal_month
            bad["entry_date"], bad["exit_date"] = entry, exit_date
            bad["exit_suspended"] = bad.index.isin(by_susp.get(exit_date, set()))
            bad["delisted_by_exit"] = bad.end.le(exit_date)
            bad["in_hs300"], bad["in_zz500"] = bad.index.isin(pools["000300.SH"]), bad.index.isin(pools["000905.SH"])
            endpoint_issues.append(bad[["ts_code", "signal_month", "entry_date", "exit_date", "entry_price_ok",
                                       "exit_price_ok", "entry_adj_ok", "exit_adj_ok", "exit_suspended",
                                       "delisted_by_exit", "in_hs300", "in_zz500"]])
    flow = pd.DataFrame(flows)
    save(flow, "sample_flow.csv")
    save(pd.DataFrame(histories), "index_history_audit.csv")
    save(pd.DataFrame(exchange_flows), "bp_by_exchange.csv")
    save(pd.DataFrame(industry_counts), "industry_sample_counts.csv")
    save(pd.DataFrame(state_issues), "state_interval_audit.csv")
    issues = pd.concat(endpoint_issues, ignore_index=True)
    save(issues, "endpoint_issues.csv", local=True)
    issues["reason"] = np.select([~issues.entry_price_ok, ~issues.exit_price_ok & issues.delisted_by_exit,
                                   ~issues.exit_price_ok & issues.exit_suspended, ~issues.exit_price_ok],
                                  ["entry_price_unavailable", "exit_price_delisted", "exit_price_recorded_suspension",
                                   "exit_price_unexplained"], default="adjustment_factor_unavailable")
    save(issues.groupby(["signal_month", "reason"]).size().rename("stock_observations").reset_index(), "endpoint_issue_counts.csv")
    summary["endpoint_issues"] = issues.reason.value_counts().to_dict()
    summary["flow"] = {pool: dict(months=len(g), min_bp_coverage=float(g.bp_coverage_f_over_u.min()),
                                  max_bp_coverage=float(g.bp_coverage_f_over_u.max()),
                                  signal_stock_observations_U=int(g.U.sum()), signal_stock_observations_F=int(g.F.sum()),
                                  signal_stock_observations_S=int(g.S.sum()),
                                  complete_periods_with_all_S_endpoints=int((g.holding_complete & g.S.eq(g.Y)).sum()))
                       for pool, g in flow.groupby("pool")}
    before_exit = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in raw_files}
    assert before == before_exit, "Raw input size or mtime changed during preflight"
    summary["raw_input_size_mtime_unchanged"] = True
    summary["no_factor_or_portfolio_results_computed"] = True
    (out / "preflight_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "last_complete": summary["calendar"]["last_complete"],
                      "flow": summary["flow"], "endpoint_issues": summary["endpoint_issues"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    args = parser.parse_args()
    main(args.course_root.resolve())
