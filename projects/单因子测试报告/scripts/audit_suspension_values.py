"""Find last traded quotes and adjustment events for confirmed suspension endpoints."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def main(course):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    keys = pd.read_csv(private / "endpoint_reclassification.csv", dtype={"ts_code": str, "trade_date": str})
    keys = keys[keys.classification.eq("confirmed_suspension")]
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str)
    old_by_new = dict(zip(aliases.new_code, aliases.old_code))
    codes = set(keys.ts_code) | set(aliases.loc[aliases.new_code.isin(keys.ts_code), "old_code"])
    data = course / "data/offline"
    prices = pq.read_table(data / "daily.parquet", columns=["ts_code", "trade_date", "close", "vol"],
                           filters=[("ts_code", "in", sorted(codes))]).to_pandas()
    factors = pq.read_table(data / "adj_factor.parquet", columns=["ts_code", "trade_date", "adj_factor"],
                            filters=[("ts_code", "in", sorted(codes))]).to_pandas()
    prices = prices[np.isfinite(prices.close) & prices.close.gt(0) & prices.vol.gt(0)]
    prices = {c: f.sort_values("trade_date") for c, f in prices.groupby("ts_code")}
    factors = {c: f.sort_values("trade_date").set_index("trade_date").adj_factor for c, f in factors.groupby("ts_code")}
    rows = []
    for key in keys.itertuples(index=False):
        # Use one raw ticker's complete factor series; do not mix alias-specific factor levels.
        raw = key.ts_code if key.ts_code in prices else old_by_new.get(key.ts_code)
        row = dict(ts_code=key.ts_code, trade_date=key.trade_date, raw_source_code=raw,
                   assessment="missing_last_quote_or_factor")
        if raw not in prices or raw not in factors:
            rows.append(row)
            continue
        quote = prices[raw]
        i = quote.trade_date.searchsorted(key.trade_date, side="left") - 1
        if i < 0:
            rows.append(row)
            continue
        quote = quote.iloc[i]
        row.update(last_trade_date=quote.trade_date, last_close=float(quote.close))
        adjustment = factors[raw]
        assert adjustment.index.is_unique
        if quote.trade_date not in adjustment.index or key.trade_date not in adjustment.index:
            rows.append(row)
            continue
        interval = adjustment.loc[quote.trade_date:key.trade_date]
        valid = np.isfinite(interval).all() and interval.gt(0).all()
        row.update(last_adj=float(interval.iloc[0]), endpoint_adj=float(interval.iloc[-1]),
                   interval_factor_values=int(interval.nunique()), interval_factor_rows=len(interval))
        if valid:
            row["assessment"] = "constant_adjustment_candidate" if interval.nunique() == 1 else "corporate_action_review"
        assert quote.trade_date < key.trade_date
        rows.append(row)
    result = pd.DataFrame(rows)
    assert len(result) == len(keys) and not result.duplicated(["ts_code", "trade_date"]).any()
    result.to_csv(private / "suspension_valuation_audit.csv", index=False, encoding="utf-8-sig")
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), endpoints=len(result),
                   assessments=result.assessment.value_counts().to_dict(),
                   rule="Last positive-volume quote, strictly before endpoint, and one raw-ticker factor series throughout",
                   limitations=["Candidate audit only: no price imputation or returns computed.",
                                "Unchanged vendor factors support absence of recorded adjustment events, not an independent corporate-action audit.",
                                "Changed factors require event-specific valuation evidence before any carry-forward."])
    (root / "outputs/repairs/suspension_valuation_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    main(parser.parse_args().course_root.resolve())
