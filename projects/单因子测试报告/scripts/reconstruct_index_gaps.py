"""Reconstruct two CSI 300 gaps from a reviewed official announcement chain."""

import argparse
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from prepare_local_repairs import canonical_codes


def main(course):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    review = json.loads((private / "csi_notices/review.json").read_text(encoding="utf-8"))
    for period in ["december_2022", "january_february_2023"]:
        item = review[period]
        assert len(set(item["notice_ids"])) == item["reported_total"]
    for notice in review["january_february_2023"]["broad_equity_adjustment_attachments"]:
        sheets = pd.read_excel(private / f"csi_notices/{notice}.xlsx", sheet_name=None, dtype=str)
        for frame in sheets.values():
            index_codes = frame.iloc[:, 0].dropna().str.strip().str.zfill(6)
            assert not index_codes.isin(["000300", "399300"]).any(), f"Unprocessed CSI 300 change in {notice}"
    baseline = pq.read_table(course / "data/offline/index_weight.parquet", columns=["index_code", "trade_date", "con_code"],
                             filters=[("index_code", "=", "000300.SH"), ("trade_date", "=", "20221230")]).to_pandas()
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str)
    baseline.con_code = canonical_codes(baseline.con_code, aliases)
    assert len(baseline) == 300 and baseline.con_code.is_unique
    march = pd.read_csv(private / "baostock_hs300_2023-03-31.csv", dtype=str)
    march_codes = canonical_codes(march.code.str[3:] + "." + march.code.str[:2].str.upper(), aliases)
    assert set(march_codes) == set(baseline.con_code), "Later corroborating snapshot differs; review intervening changes"
    frames = []
    for date in review["target_dates"]:
        frame = baseline[["index_code", "con_code"]].copy()
        frame["signal_date"], frame["baseline_date"] = date, "20221230"
        frame["source"] = "CSI official announcement chain: no applicable constituent change"
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    result.to_csv(private / "index_membership_csi_reconstruction.csv", index=False, encoding="utf-8-sig")
    summary = dict(source=review["source"], reviewed_on=review["reviewed_on"],
                   target_dates=review["target_dates"], baseline_date="20221230", members_per_date=300,
                   official_notices_reviewed=86, adjustment_attachments_checked=6,
                   baseline_equals_march_snapshot=True, limitations=review["limitations"],
                   status="Two month membership gaps reconstructed; other P1 gates remain open")
    (root / "outputs/repairs/hs300_reconstruction.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    main(parser.parse_args().course_root.resolve())
