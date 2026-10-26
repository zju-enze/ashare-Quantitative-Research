"""Reclassify the original P1 endpoint gaps using acquired evidence, without computing returns."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from prepare_local_repairs import canonical_codes


def classify_keys(frame):
    conflict = frame.status_conflict | (frame.price_present & frame.suspended)
    return np.select(
        # BaoStock also returns status 0 on observed delisting dates; lifecycle takes precedence.
        [conflict, frame.price_present, frame.delisted, frame.suspended],
        ["conflicting_evidence", "quote_present", "terminal_event_unresolved", "confirmed_suspension"],
        default="unexplained_missing_quote",
    )


def main(course):
    root = Path(__file__).resolve().parents[1]
    private, public = root / ".local/data_repairs", root / "outputs/repairs"
    data = course / "data/offline"
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str)
    issues = pd.read_csv(root / ".local/preflight/endpoint_issues.csv", dtype=str)
    issues.ts_code = canonical_codes(issues.ts_code, aliases)
    issues = issues.drop_duplicates(["ts_code", "signal_month"])
    keys = pd.concat([
        issues[["ts_code", side + "_date"]].rename(columns={side + "_date": "trade_date"})
        for side in ["entry", "exit"]
    ]).drop_duplicates()
    dates = keys.trade_date.unique().tolist()
    for name, column, flag in [("daily", "close", "price_present"), ("adj_factor", "adj_factor", "adj_present")]:
        frame = pq.read_table(data / (name + ".parquet"), columns=["ts_code", "trade_date", column],
                              filters=[("trade_date", "in", dates)]).to_pandas()
        frame.ts_code = canonical_codes(frame.ts_code, aliases)
        frame[flag] = np.isfinite(frame[column]) & frame[column].gt(0)
        # This audit checks presence only; conflicting adjustment scales are not spliced into returns.
        presence = frame.groupby(["ts_code", "trade_date"], as_index=False)[flag].any()
        keys = keys.merge(presence, how="left", on=["ts_code", "trade_date"], validate="one_to_one")
        keys[flag] = keys[flag].eq(True)

    offline = pd.read_parquet(data / "suspend_d.parquet")
    offline.ts_code = canonical_codes(offline.ts_code, aliases)
    offline = offline[offline.suspend_type.eq("S") & offline.suspend_timing.isna()].copy()
    offline["status"], offline["source"] = "0", "offline_full_day_S"
    local = pd.read_csv(private / "endpoint_status_from_local_market.csv", dtype=str)
    local = local.rename(columns={"tradestatus": "status"})
    local["source"] = "existing_local_BaoStock_daily"
    remote = pd.read_csv(private / "endpoint_market_status.csv", dtype=str).rename(columns={"tradeStatus": "status"})
    remote["source"] = "acquired_BaoStock_market_status"
    columns = ["ts_code", "trade_date", "status", "source"]
    evidence = pd.concat([f[columns] for f in [offline, local, remote]], ignore_index=True)
    evidence = evidence[evidence.status.notna()]
    evidence.ts_code = canonical_codes(evidence.ts_code, aliases)
    assert evidence.status.isin(["0", "1"]).all()
    by_key = evidence.groupby(["ts_code", "trade_date"])
    status = by_key.agg(status_values=("status", lambda v: ",".join(sorted(set(v)))),
                        status_sources=("source", lambda v: ",".join(sorted(set(v)))))
    keys = keys.merge(status, how="left", on=["ts_code", "trade_date"], validate="one_to_one")
    keys["suspended"] = keys.status_values.eq("0")
    keys["status_conflict"] = keys.status_values.eq("0,1")
    basic = pd.read_parquet(data / "stock_basic.parquet")
    basic.ts_code = canonical_codes(basic.ts_code, aliases)
    assert basic.ts_code.is_unique
    keys = keys.merge(basic[["ts_code", "delist_date"]], how="left", on="ts_code", validate="many_to_one")
    keys["delisted"] = False
    dated = keys.delist_date.notna()
    keys.loc[dated, "delisted"] = keys.loc[dated, "delist_date"].le(keys.loc[dated, "trade_date"])
    keys["classification"] = classify_keys(keys)
    keys.to_csv(private / "endpoint_reclassification.csv", index=False, encoding="utf-8-sig")

    periods = issues[["ts_code", "signal_month", "entry_date", "exit_date", "in_hs300", "in_zz500"]].copy()
    for side in ["entry", "exit"]:
        view = keys[["ts_code", "trade_date", "classification", "adj_present"]].rename(columns={
            "trade_date": side + "_date", "classification": side + "_classification", "adj_present": side + "_adj_present"})
        periods = periods.merge(view, on=["ts_code", side + "_date"], how="left", validate="many_to_one")
    periods["disposition"] = np.select(
        [periods.entry_classification.eq("confirmed_suspension"),
         periods.entry_classification.eq("terminal_event_unresolved"),
         periods.entry_classification.ne("quote_present"),
         periods.exit_classification.ne("quote_present"),
         ~periods.entry_adj_present | ~periods.exit_adj_present],
        ["entry_ineligible_confirmed_suspension", "entry_ineligible_after_delisting", "entry_evidence_unresolved",
         "exit_valuation_unresolved", "adjustment_unresolved"], default="both_endpoints_present")
    assert periods.disposition.notna().all()
    periods.to_csv(private / "period_reclassification.csv", index=False, encoding="utf-8-sig")
    monthly = periods.groupby(["signal_month", "disposition"]).size().rename("stock_periods").reset_index()
    monthly.to_csv(public / "endpoint_reclassification_by_month.csv", index=False, encoding="utf-8-sig")
    counts = periods.disposition.value_counts().to_dict()
    assert sum(counts.values()) == len(periods)
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
                   scope="Original P1 flagged stock-periods only; not a rebuilt universe or factor result",
                   stock_periods=len(periods), unique_endpoint_keys=len(keys),
                   endpoint_classifications=keys.classification.value_counts().to_dict(),
                   period_dispositions=counts,
                   missing_adjustment_keys=int((~keys.adj_present).sum()),
                   limitations=["Confirmed suspension does not supply an exit valuation.",
                                "No terminal-event policy has been applied.",
                                "New industry coverage and close-entry eligibility require a later full P1 rerun."])
    (public / "endpoint_reclassification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    main(parser.parse_args().course_root.resolve())
