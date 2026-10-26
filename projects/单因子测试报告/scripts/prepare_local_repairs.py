"""Prepare source-backed identity and historical-industry inputs; never edit source data."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def canonical_codes(values, aliases):
    return values.replace(dict(zip(aliases.old_code, aliases.new_code)))


def collapse_equal_alias_rows(frame, keys, value_columns):
    duplicates = frame.duplicated(keys, keep=False)
    if duplicates.any():
        distinct = frame.loc[duplicates].groupby(keys)[value_columns].nunique(dropna=False)
        if distinct.gt(1).any(axis=None):
            raise ValueError("Conflicting observations after canonical identity mapping")
    return frame.drop_duplicates(keys).copy()


def industry_asof(history, codes, cutoff):
    # Signals are formed after the month-end close for next-session execution; match effective calendar dates.
    available = history[history.effective_from.dt.normalize().le(pd.Timestamp(cutoff).normalize())]
    available = available.sort_values("effective_from").groupby("ts_code").tail(1)
    return available.set_index("ts_code").reindex(codes)


def read_industry_history(source, basic, aliases):
    catalogue = pd.read_excel(source / "SwClassCode_2021.xls", dtype=str)
    catalogue.columns = ["industry_code", "l1_name", "l2_name", "l3_name"]
    assert catalogue.industry_code.is_unique
    l1 = catalogue[catalogue.l2_name.isna()].set_index("industry_code").l1_name
    history = pd.read_excel(source / "StockClassifyUse_stock_live.xls", dtype=str)
    history.columns = ["symbol", "effective_from", "industry_code", "source_updated_at"]
    history.effective_from = pd.to_datetime(history.effective_from, errors="raise")
    history.source_updated_at = pd.to_datetime(history.source_updated_at, errors="raise")
    identities = pd.concat([basic.ts_code, aliases.old_code, aliases.new_code]).drop_duplicates()
    symbol_map = pd.Series(identities.to_numpy(), index=identities.str[:6])
    assert symbol_map.index.is_unique, "Ambiguous exchange for a stock symbol"
    history["ts_code"] = canonical_codes(history.symbol.map(symbol_map), aliases)
    history["l1_code"] = history.industry_code.str[:2] + "0000"
    history["l1_name"] = history.l1_code.map(l1)
    history["legacy_l1_not_in_2021_catalogue"] = history.l1_name.isna()
    # Preserve observed historical groups; never assign today's split industry backwards.
    history["l1_label"] = history.l1_name.fillna("申万历史一级代码" + history.l1_code)
    unknown_symbols = history[history.ts_code.isna()].copy()
    known = history[history.ts_code.notna()].copy()
    n = known.groupby(["ts_code", "effective_from"]).l1_code.nunique()
    if n.gt(1).any():
        raise ValueError("Conflicting L1 events at the same security/effective time")
    known = known.sort_values("source_updated_at").drop_duplicates(["ts_code", "effective_from", "l1_code"], keep="last")
    return catalogue, known, unknown_symbols, len(history)


def main(course, industry_source):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local" / "data_repairs"
    public = root / "outputs" / "repairs"
    public.mkdir(parents=True, exist_ok=True)
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str)
    assert aliases.old_code.is_unique and aliases.new_code.is_unique
    data = course / "data" / "offline"
    basic = pd.read_parquet(data / "stock_basic.parquet")
    catalogue, history, unknown, raw_event_rows = read_industry_history(industry_source, basic, aliases)
    history.to_parquet(private / "industry_event_history.parquet", index=False)
    unknown.to_csv(private / "industry_unmatched_symbols.csv", index=False, encoding="utf-8-sig")
    calendar = pd.read_csv(root / "outputs" / "preflight" / "calendar_audit.csv", dtype={"signal_date": str})
    signals = calendar[calendar.signal_complete]
    value_columns = ["pb", "close", "total_mv", "circ_mv"]
    db = pq.read_table(data / "daily_basic.parquet", columns=["ts_code", "trade_date", *value_columns],
                       filters=[("trade_date", "in", signals.signal_date.tolist())]).to_pandas()
    db["original_code"] = db.ts_code
    db.ts_code = canonical_codes(db.ts_code, aliases)
    duplicates = db.duplicated(["ts_code", "trade_date"], keep=False)
    reidentified = int(db.ts_code.ne(db.original_code).sum())
    duplicate_keys = len(db.loc[duplicates, ["ts_code", "trade_date"]].drop_duplicates())
    if duplicates.any():
        db.loc[duplicates].to_csv(private / "identity_valuation_overlaps.csv", index=False, encoding="utf-8-sig")
    db = collapse_equal_alias_rows(db, ["ts_code", "trade_date"], value_columns)
    rows = []
    for date, group in db.groupby("trade_date"):
        valid = group[np.isfinite(group.pb) & group.pb.gt(0)]
        cutoff = pd.Timestamp(date)
        matched = industry_asof(history, valid.ts_code, cutoff)
        counts = matched.l1_label.value_counts()
        rows.append(dict(signal_date=date, positive_pb_rows=len(valid), industry_matched=int(matched.l1_code.notna().sum()),
                         legacy_l1_rows=int(matched.legacy_l1_not_in_2021_catalogue.eq(True).sum()),
                         l1_groups=int(matched.l1_code.nunique()),
                         food_beverage=int(counts.get("食品饮料", 0)), textiles=int(counts.get("纺织服饰", 0)),
                         coal=int(counts.get("煤炭", 0))))
    pd.DataFrame(rows).to_csv(public / "local_industry_coverage.csv", index=False, encoding="utf-8-sig")
    unknown_prefix = history[history.legacy_l1_not_in_2021_catalogue]
    legacy = unknown_prefix.groupby("l1_code").agg(rows=("ts_code", "size"),
                                                   first_effective=("effective_from", "min"),
                                                   last_effective=("effective_from", "max"))
    legacy.to_csv(public / "legacy_industry_codes.csv", encoding="utf-8-sig")
    overlap = pd.read_csv(private / "hs300_overlap_checks.csv", dtype={"date": str})
    targets = set(pd.read_csv(root / "outputs" / "preflight" / "index_history_audit.csv").query("not same_month").signal_month)
    supplements, rejected = [], []
    for row in overlap.itertuples(index=False):
        day = row.date
        if pd.Timestamp(day).strftime("%Y-%m") not in targets:
            continue
        if pd.Timestamp(row.provider_update).strftime("%Y-%m") != pd.Timestamp(day).strftime("%Y-%m"):
            rejected.append(dict(signal_date=day, source_update=row.provider_update, reason="stale_source_membership"))
            continue
        frame = pd.read_csv(private / f"baostock_hs300_{pd.Timestamp(day):%Y-%m-%d}.csv", dtype=str)
        frame["con_code"] = canonical_codes(frame.code.str[3:] + "." + frame.code.str[:2].str.upper(), aliases)
        frame["index_code"], frame["signal_date"] = "000300.SH", day
        frame["source"] = "BaoStock query_hs300_stocks(requested signal_date)"
        supplements.append(frame[["index_code", "signal_date", "con_code", "updateDate", "source"]])
    membership = pd.concat(supplements, ignore_index=True)
    assert not membership.duplicated(["index_code", "signal_date", "con_code"]).any()
    membership.to_csv(private / "index_membership_candidates.csv", index=False, encoding="utf-8-sig")
    passed_anchors = overlap[overlap.overlap_local_snapshot & overlap.only_baostock.eq(0) & overlap.only_local.eq(0)]
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
                   course_root=str(course), industry_source=str(industry_source),
                   historical_source="StockClassifyUse_stock_live.xls (existing local official-source download)",
                   source_event_rows=raw_event_rows, normalized_event_rows=len(history) + len(unknown), events_for_known_identities=len(history),
                   unmatched_event_rows=len(unknown), catalogue_l1_count=int(catalogue.l2_name.isna().sum()),
                   legacy_l1_codes=legacy.index.tolist(),
                   identity_aliases=len(aliases), valuation_rows_reidentified=reidentified,
                   equivalent_valuation_alias_keys_collapsed=duplicate_keys,
                   valuation_key_conflicts=0, latest_industry_coverage=rows[-1],
                   hs300_candidate_months=int(membership.signal_date.nunique()),
                   matching_local_anchor_dates=passed_anchors.date.tolist(), rejected_membership_months=rejected,
                   no_factor_results=True,
                   limitations=["Historical source updated_at is not publication time; current reconstructed history may be revised.",
                                "Legacy L1 groups must retain their historical identity; 2021 catalogue does not define their names.",
                                "Membership candidates and industry event inputs are not a passed full research sample."])
    (public / "local_sources_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--industry-source", type=Path, required=True)
    args = parser.parse_args()
    main(args.course_root.resolve(), args.industry_source.resolve())
