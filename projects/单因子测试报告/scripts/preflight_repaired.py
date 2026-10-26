"""Rebuild candidate U/F/S with repaired historical inputs; never calculate factor returns."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from preflight import bp_reason, positive
from prepare_local_repairs import canonical_codes, collapse_equal_alias_rows, industry_asof


def halted_at_close(timing):
    if pd.isna(timing):
        return True
    # Observed source ranges ending at 14:57 resume for the closing auction.
    return any(part.split("-")[-1] == "15:00" for part in timing.split(","))


def canonical_factor_series(frame, aliases):
    frame = frame.copy()
    frame["raw_code"] = frame.ts_code
    frame.ts_code = canonical_codes(frame.ts_code, aliases)
    canonical = frame[frame.raw_code.eq(frame.ts_code)]
    redundant = frame[frame.raw_code.ne(frame.ts_code) & frame.ts_code.isin(canonical.ts_code)]
    reference_keys = pd.MultiIndex.from_frame(canonical[["ts_code", "trade_date"]])
    alias_keys = pd.MultiIndex.from_frame(redundant[["ts_code", "trade_date"]])
    if not alias_keys.isin(reference_keys).all():
        raise ValueError("Canonical factor series is incomplete; alias scales cannot be spliced")
    frame = frame.drop(index=redundant.index)
    assert not frame.duplicated(["ts_code", "trade_date"]).any()
    return frame


def entry_qualification(delisted, close_halt, traded, daily_status):
    # Primary positive-volume OHLCV outranks a secondary carried-price status snapshot.
    return np.select([delisted, close_halt, traded, daily_status.eq("0"), daily_status.eq("1")],
                     ["already_delisted", "not_tradable_at_close", "tradable", "not_tradable_at_close", "tradable"],
                     default="unknown")


def main(course):
    root = Path(__file__).resolve().parents[1]
    repairs = root / ".local/data_repairs"
    private, public = root / ".local/preflight_repaired", root / "outputs/preflight_repaired"
    private.mkdir(exist_ok=True)
    public.mkdir(exist_ok=True)
    data = course / "data/offline"
    aliases = pd.read_csv(repairs / "security_aliases.csv", dtype=str)
    calendar = pd.read_csv(root / "outputs/preflight/calendar_audit.csv",
                           dtype={c: str for c in ["signal_date", "entry_date", "exit_date", "next_signal_date"]})
    calendar = calendar[calendar.signal_complete].copy()
    signals = calendar.signal_date.tolist()
    endpoints = sorted(set(calendar.entry_date.dropna()) | set(calendar.loc[calendar.holding_complete, "exit_date"]))
    files = [data / (name + ".parquet") for name in ["daily", "daily_basic", "adj_factor", "stock_basic", "namechange", "suspend_d", "index_weight"]]
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    db = pq.read_table(data / "daily_basic.parquet", columns=["ts_code", "trade_date", "pb", "total_mv", "circ_mv"],
                       filters=[("trade_date", "in", signals)]).to_pandas()
    db.ts_code = canonical_codes(db.ts_code, aliases)
    db = collapse_equal_alias_rows(db, ["ts_code", "trade_date"], ["pb", "total_mv", "circ_mv"])
    cap_path = repairs / "circ_mv_overrides.csv"
    cap_changes = 0
    if cap_path.exists():
        overrides = pd.read_csv(cap_path, dtype={"ts_code": str, "trade_date": str}).set_index(["ts_code", "trade_date"])
        db = db.set_index(["ts_code", "trade_date"])
        assert overrides.index.is_unique and overrides.index.isin(db.index).all()
        assert np.allclose(db.loc[overrides.index, "circ_mv"], overrides.original_circ_mv, rtol=1e-10, atol=0)
        assert positive(overrides.corrected_circ_mv).all()
        db.loc[overrides.index, "circ_mv"] = overrides.corrected_circ_mv
        cap_changes = len(overrides)
        db = db.reset_index()
    prices = pq.read_table(data / "daily.parquet", columns=["ts_code", "trade_date", "close", "vol"],
                           filters=[("trade_date", "in", endpoints)]).to_pandas()
    prices.ts_code = canonical_codes(prices.ts_code, aliases)
    prices = collapse_equal_alias_rows(prices, ["ts_code", "trade_date"], ["close", "vol"])
    factors = pq.read_table(data / "adj_factor.parquet", columns=["ts_code", "trade_date", "adj_factor"],
                            filters=[("trade_date", "in", endpoints)]).to_pandas()
    factors = canonical_factor_series(factors, aliases)
    basic = pd.read_parquet(data / "stock_basic.parquet")
    basic.ts_code = canonical_codes(basic.ts_code, aliases)
    assert basic.ts_code.is_unique
    early_bj = basic.ts_code.str.endswith(".BJ") & basic.list_date.lt("20211115")
    basic["source_list_date"] = basic.list_date
    basic.loc[early_bj, "list_date"] = "20211115"
    basic["end"] = basic.delist_date.fillna("99991231")
    basic = basic.set_index("ts_code", drop=False)
    names = pd.read_parquet(data / "namechange.parquet")
    names.ts_code = canonical_codes(names.ts_code, aliases)
    names["end"] = names.end_date.fillna("99991231")
    names["risk_name"] = names.name.str.contains(r"ST|PT", case=False, na=False)
    risk_path = repairs / "signal_risk_status.csv"
    risk_supplement = pd.read_csv(risk_path, dtype=str) if risk_path.exists() else pd.DataFrame(columns=["ts_code", "signal_date", "isST"])
    by_risk = {day: frame.set_index("ts_code").isST for day, frame in risk_supplement.groupby("signal_date")}
    industry = pd.read_parquet(repairs / "industry_event_history.parquet")
    susp = pd.read_parquet(data / "suspend_d.parquet")
    susp.ts_code = canonical_codes(susp.ts_code, aliases)
    susp = susp[susp.trade_date.isin(endpoints) & susp.suspend_type.eq("S")]
    susp["close_halt"] = susp.suspend_timing.map(halted_at_close)
    close_halts = {day: set(g.ts_code) for day, g in susp[susp.close_halt].groupby("trade_date")}
    snapshots = []
    for path in repairs.glob("baostock_market_status_*.csv"):
        day = path.stem.removeprefix("baostock_market_status_").replace("-", "")
        if day not in endpoints:
            continue
        frame = pd.read_csv(path, dtype=str)
        frame["ts_code"] = canonical_codes(frame.code.str[3:] + "." + frame.code.str[:2].str.upper(), aliases)
        frame["trade_date"] = day
        snapshots.append(frame[["ts_code", "trade_date", "tradeStatus"]])
    status = collapse_equal_alias_rows(pd.concat(snapshots, ignore_index=True), ["ts_code", "trade_date"], ["tradeStatus"])
    weights = pd.read_parquet(data / "index_weight.parquet")[["index_code", "trade_date", "con_code"]]
    weights = weights[weights.index_code.isin(["000300.SH", "000905.SH"])].copy()
    weights["source"] = "offline_monthly_snapshot"
    additions = []
    for filename in ["index_membership_candidates.csv", "index_membership_csi_reconstruction.csv"]:
        frame = pd.read_csv(repairs / filename, dtype=str).rename(columns={"signal_date": "trade_date"})
        additions.append(frame[["index_code", "trade_date", "con_code", "source"]])
    weights = pd.concat([weights, *additions], ignore_index=True)
    weights.con_code = canonical_codes(weights.con_code, aliases)
    assert not weights.duplicated(["index_code", "trade_date", "con_code"]).any()
    by_weight = {code: {day: g for day, g in frame.groupby("trade_date")} for code, frame in weights.groupby("index_code")}
    by_db = {day: g.set_index("ts_code") for day, g in db.groupby("trade_date")}
    by_prices = {day: g.set_index("ts_code") for day, g in prices.groupby("trade_date")}
    by_factors = {day: g.set_index("ts_code").adj_factor for day, g in factors.groupby("trade_date")}
    by_status = {day: g.set_index("ts_code").tradeStatus for day, g in status.groupby("trade_date")}
    valuations = []
    for name in ["suspension_valuations.parquet", "delisting_valuations.parquet", "merger_valuations.parquet"]:
        path = repairs / name
        if path.exists():
            valuations.append(pd.read_parquet(path)[["ts_code", "trade_date", "adjusted_value", "valuation_kind"]])
    values = pd.concat(valuations, ignore_index=True) if valuations else pd.DataFrame(columns=["ts_code", "trade_date", "adjusted_value", "valuation_kind"])
    assert not values.duplicated(["ts_code", "trade_date"]).any()
    by_value = {day: g.set_index("ts_code") for day, g in values.groupby("trade_date")}
    empty = pd.Series(dtype=float)
    panels, flows, membership, state_issues = [], [], [], []
    for number, row in enumerate(calendar.itertuples(index=False), 1):
        signal, entry, exit_date = row.signal_date, row.entry_date, row.exit_date
        g = basic[(basic.list_date.le(signal)) & basic.end.gt(signal)][["ts_code", "list_date", "end", "market"]].copy()
        g["signal_month"], g["signal_date"], g["entry_date"], g["exit_date"] = row.signal_month, signal, entry, exit_date
        g["holding_month"], g["holding_complete"] = row.holding_month, row.holding_complete
        current_names = names[names.start_date.le(signal) & names.end.ge(signal)]
        risk = current_names.groupby("ts_code").risk_name.agg(["any", "nunique"])
        g["st_pt"] = risk["any"].reindex(g.index).eq(True)
        g["name_unknown"] = ~g.index.isin(current_names.ts_code)
        g["name_risk_conflict"] = risk["nunique"].reindex(g.index).gt(1)
        supplemental_risk = by_risk.get(signal, empty).reindex(g.index)
        g.loc[g.name_unknown & supplemental_risk.notna(), "st_pt"] = supplemental_risk.eq("1")
        g["risk_status_unknown"] = g.name_unknown & supplemental_risk.isna()
        g["risk_status_source"] = np.where(~g.name_unknown, "historical_name_interval",
                                           np.where(supplemental_risk.notna(), "BaoStock_daily_isST", "unknown"))
        ep = by_prices[entry]
        traded = positive(ep.close.reindex(g.index)) & ep.vol.reindex(g.index).gt(0)
        halt = g.index.isin(close_halts.get(entry, set()))
        daily_status = by_status.get(entry, empty).reindex(g.index)
        conflict = traded & daily_status.eq("0") & ~halt & g.end.gt(entry)
        g["secondary_status_conflict"] = conflict
        g["entry_state"] = entry_qualification(g.end.le(entry), halt, traded, daily_status)
        val = by_db[signal].reindex(g.index)
        g["bp_reason"] = bp_reason(val.pb, g.index.isin(by_db[signal].index))
        g[["pb", "total_mv", "circ_mv"]] = val[["pb", "total_mv", "circ_mv"]]
        hist = industry_asof(industry, g.index, signal)
        g["industry_code"], g["industry_label"] = hist.l1_code, hist.l1_label
        g["cap_ok"] = positive(g.total_mv) & positive(g.circ_mv)
        g["U"] = ~g.st_pt & g.entry_state.eq("tradable")
        g["F"] = g.U & g.bp_reason.eq("valid")
        g["S"] = g.F & g.cap_ok & g.industry_code.notna()
        # Response data enters only after formation flags; do not shrink S to observed exits.
        for side, day in [("entry", entry), ("exit", exit_date)]:
            quote = by_prices.get(day, pd.DataFrame(columns=["close", "vol"], dtype=float))
            g[side + "_close"] = quote.close.reindex(g.index)
            g[side + "_adj_factor"] = by_factors.get(day, empty).reindex(g.index)
            g[side + "_price_ok"] = positive(g[side + "_close"]) & quote.vol.reindex(g.index).gt(0)
            g[side + "_adj_ok"] = positive(g[side + "_adj_factor"])
        exit_status = by_status.get(exit_date, empty).reindex(g.index)
        exit_halted = g.index.isin(close_halts.get(exit_date, set())) | exit_status.eq("0")
        g["exit_classification"] = np.select(
            [not row.holding_complete, g.exit_price_ok, g.end.le(exit_date), exit_halted],
            ["incomplete_holding_period", "quote_present", "terminal_event_unresolved", "confirmed_suspension"],
            default="unexplained_missing_quote")
        g["Y_raw"] = g.S & g.entry_price_ok & g.exit_price_ok & g.entry_adj_ok & g.exit_adj_ok & row.holding_complete
        g["entry_adjusted_value"] = g.entry_close * g.entry_adj_factor
        g["exit_adjusted_value"] = (g.exit_close * g.exit_adj_factor).where(g.exit_price_ok & g.exit_adj_ok)
        g["exit_value_kind"] = np.where(g.exit_adjusted_value.notna(), "actual_endpoint_close", "unresolved")
        if exit_date in by_value:
            supplemental_value = by_value[exit_date].reindex(g.index)
            use = g.exit_adjusted_value.isna() & supplemental_value.adjusted_value.notna()
            g.loc[use, "exit_adjusted_value"] = supplemental_value.adjusted_value
            g.loc[use, "exit_value_kind"] = supplemental_value.valuation_kind
        g["Y"] = g.S & g.entry_price_ok & positive(g.entry_adjusted_value) & positive(g.exit_adjusted_value) & row.holding_complete
        pools = {"ALL_A": set(g.index)}
        raw_sizes = {"ALL_A": len(g)}
        for code, days in by_weight.items():
            prior = [d for d in days if d <= signal]
            source_day = max(prior) if prior else ""
            frame = days.get(source_day, pd.DataFrame(columns=weights.columns))
            ids = set(frame.con_code)
            pools[code], raw_sizes[code] = ids & set(g.index), len(ids)
            membership.append(dict(pool=code, signal_month=row.signal_month, snapshot_date=source_day,
                                   same_month=bool(source_day and source_day[:6] == signal[:6]), members=len(ids),
                                   outside_lifecycle=len(ids-set(g.index)), source=";".join(frame.source.unique())))
            g["in_" + code[:6]] = g.index.isin(ids)
        for pool, ids in pools.items():
            f = g.loc[g.index.isin(ids)]
            u, valid, s = f[f.U], f[f.F], f[f.S]
            flow = dict(pool=pool, signal_month=row.signal_month, historical_members=raw_sizes[pool],
                        lifecycle_members=len(f), st_pt_excluded=int(f.st_pt.sum()),
                        entry_not_tradable=int((~f.st_pt & f.entry_state.isin(["already_delisted", "not_tradable_at_close"])).sum()),
                        entry_state_unknown=int((~f.st_pt & f.entry_state.eq("unknown")).sum()),
                        entry_state_conflict=int((~f.st_pt & f.entry_state.eq("conflicting_evidence")).sum()),
                        secondary_status_conflict=int((~f.st_pt & f.secondary_status_conflict).sum()),
                        U=len(u), F=len(valid), S=len(s), Y=int(s.Y.sum()) if row.holding_complete else None,
                        Y_raw=int(s.Y_raw.sum()) if row.holding_complete else None,
                        repaired_exit_values=int((s.Y & ~s.Y_raw).sum()) if row.holding_complete else None,
                        bp_coverage_f_over_u=len(valid)/len(u) if len(u) else None,
                        unknown_name_in_U=int(u.name_unknown.sum()), name_risk_conflict=int(f.name_risk_conflict.sum()),
                        unknown_risk_state_in_U=int(u.risk_status_unknown.sum()),
                        industry_missing_in_F=int(valid.industry_code.isna().sum()),
                        invalid_cap_after_industry=int((valid.industry_code.notna() & ~valid.cap_ok).sum()),
                        holding_complete=row.holding_complete)
            assert flow["U"] + flow["st_pt_excluded"] + flow["entry_not_tradable"] + flow["entry_state_unknown"] + flow["entry_state_conflict"] == len(f)
            for reason in ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_zero", "pb_negative"]:
                flow[reason] = int(u.bp_reason.eq(reason).sum())
            assert flow["F"] + sum(flow[r] for r in ["valuation_row_missing", "pb_missing", "pb_nonfinite", "pb_zero", "pb_negative"]) == len(u)
            assert flow["S"] + flow["industry_missing_in_F"] + flow["invalid_cap_after_industry"] == len(valid)
            flows.append(flow)
        uncertain = g[(g.risk_status_unknown & g.U) | g.name_risk_conflict | g.secondary_status_conflict | (~g.st_pt & g.entry_state.eq("unknown"))]
        state_issues.append(uncertain[["ts_code", "signal_date", "entry_date", "name_unknown", "risk_status_unknown", "name_risk_conflict", "entry_state", "secondary_status_conflict", "bp_reason", "S"]])
        panels.append(g.reset_index(drop=True))
        if number == 1 or number % 50 == 0 or number == len(calendar):
            print(f"Repaired preflight {number}/{len(calendar)}: {signal}", flush=True)
    panel = pd.concat(panels, ignore_index=True)
    assert not panel.duplicated(["ts_code", "signal_date"]).any()
    panel.to_parquet(private / "candidate_panel.parquet", index=False)
    pd.concat(state_issues, ignore_index=True).to_csv(private / "state_issues.csv", index=False, encoding="utf-8-sig")
    issues = panel[panel.S & panel.holding_complete & ~panel.Y]
    raw_issues = panel[panel.S & panel.holding_complete & ~panel.Y_raw]
    issues.to_csv(private / "endpoint_issues.csv", index=False, encoding="utf-8-sig")
    raw_issues.to_csv(private / "raw_endpoint_issues.csv", index=False, encoding="utf-8-sig")
    flow, member_audit = pd.DataFrame(flows), pd.DataFrame(membership)
    flow.to_csv(public / "sample_flow.csv", index=False, encoding="utf-8-sig")
    member_audit.to_csv(public / "index_history_audit.csv", index=False, encoding="utf-8-sig")
    calendar.to_csv(public / "calendar_audit.csv", index=False, encoding="utf-8-sig")
    assert before == {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    input_checks_passed = (issues.empty and member_audit.same_month.all() and
                          flow[["entry_state_unknown", "entry_state_conflict", "unknown_risk_state_in_U", "name_risk_conflict"]].eq(0).all(axis=None))
    complete = calendar[calendar.holding_complete]
    summary = dict(kind="repaired_candidate_preflight_not_factor_results", method_version="0.5", input_checks_passed=bool(input_checks_passed),
                   checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
                   bse_listing_dates_clamped_to_launch=int(early_bj.sum()),
                   circ_mv_rows_corrected=cap_changes,
                   bse_launch_source="https://www.bse.cn/company/introduce.html",
                   candidate_stock_periods=len(panel), endpoint_issue_stock_periods=len(issues),
                   raw_endpoint_issue_stock_periods=len(raw_issues),
                   endpoint_issue_classes=issues.exit_classification.value_counts().to_dict(),
                   raw_endpoint_issue_classes=raw_issues.exit_classification.value_counts().to_dict(),
                   complete_holding_periods=len(complete), first_signal_date=complete.signal_date.min(),
                   last_signal_date=complete.signal_date.max(), first_entry_date=complete.entry_date.min(),
                   last_exit_date=complete.exit_date.max(),
                   applied_exit_value_kinds=panel.loc[panel.S & panel.holding_complete, "exit_value_kind"].value_counts().to_dict(),
                   unresolved_index_months=int((~member_audit.same_month).sum()),
                   outside_lifecycle_index_observations=int(member_audit.outside_lifecycle.sum()),
                   flow=flow.groupby("pool")[["U", "F", "S", "entry_state_unknown", "entry_state_conflict", "secondary_status_conflict", "unknown_name_in_U", "unknown_risk_state_in_U", "name_risk_conflict", "industry_missing_in_F"]].sum().to_dict("index"),
                   raw_input_size_mtime_unchanged=True,
                   limitations=["Missing historical names are supplemented with date-specific isST; unresolved risk/status counts are reported separately.",
                                "Supported suspension and terminal-event valuations are labelled academic estimates, not guaranteed executable exits.",
                                "Universe retains the course stock_basic scope, including its STAR-market depositary receipt; market-scope disclosure required."])
    (public / "preflight_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    main(parser.parse_args().course_root.resolve())
