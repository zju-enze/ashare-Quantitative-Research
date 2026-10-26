"""Value the reviewed share-swap cases under RESEARCH_SPEC 15/15.1; no cash-option optimisation."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def main(course):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    terms = pd.read_csv(private / "merger_terms.csv", dtype={"old_code": str, "target_code": str, "publication_date": str}).set_index("old_code")
    queue = pd.read_csv(private / "terminal_event_candidates.csv", dtype=str)
    queue = queue[~queue.signal_names.str.contains("退", na=False)]
    assert terms.index.is_unique and set(terms.index) == set(queue.ts_code)
    data = course / "data/offline"
    targets = terms.target_code.unique().tolist()
    prices = pq.read_table(data / "daily.parquet", columns=["ts_code", "trade_date", "close", "vol"],
                           filters=[("ts_code", "in", targets)]).to_pandas()
    factors = pq.read_table(data / "adj_factor.parquet", columns=["ts_code", "trade_date", "adj_factor"],
                            filters=[("ts_code", "in", targets)]).to_pandas()
    basic = pd.read_parquet(data / "stock_basic.parquet").set_index("ts_code")
    estimates = pd.read_parquet(private / "suspension_valuations.parquet").set_index(["ts_code", "trade_date"])
    rows = []
    for key in queue.itertuples(index=False):
        term = terms.loc[key.ts_code]
        assert term.publication_date <= key.exit_date
        ratio, old_factor = float(term.new_shares_per_old_share), float(key.last_adj_factor)
        assert np.isfinite(ratio * old_factor) and ratio > 0 and old_factor > 0
        target = term.target_code
        observed = prices[prices.ts_code.eq(target) & prices.trade_date.le(key.exit_date) & prices.vol.gt(0)].sort_values("trade_date")
        if term.valuation_method == "approved_unlisted_right_carry":
            assert observed.empty and basic.loc[target, "list_date"] > key.exit_date
            equivalent = float(key.last_close)
            target_price = equivalent / ratio
            source_date, kind = key.last_trade_date, "approved_unlisted_share_right_carry"
        else:
            adjustment = factors[factors.ts_code.eq(target) & factors.trade_date.between(key.last_trade_date, key.exit_date)]
            # All observed merger targets have no post-last-old-trade factor event; avoid inventing a general action engine.
            assert adjustment.adj_factor.nunique() == 1, f"Target action needs review: {target} {key.exit_date}"
            quote = observed.iloc[-1]
            if quote.trade_date == key.exit_date:
                target_price, source_date, kind = float(quote.close), quote.trade_date, "swap_to_target_actual_close"
            else:
                estimate = estimates.loc[(target, key.exit_date)]
                assert np.isfinite(estimate.adjusted_value) and not estimate.tradable_at_endpoint
                target_price = float(estimate.reference_value_per_old_share)
                source_date, kind = estimate.last_trade_date, "swap_to_supported_target_suspension_value"
            equivalent = ratio * target_price
        assert equivalent > 0 and source_date <= key.exit_date
        rows.append(dict(ts_code=key.ts_code, trade_date=key.exit_date, target_code=target,
                         new_shares_per_old_share=ratio, target_reference_value=target_price,
                         target_reference_date=source_date, old_equivalent_value=equivalent,
                         old_factor_used=old_factor, adjusted_value=equivalent * old_factor,
                         valuation_kind=kind, publication_date=term.publication_date, source_url=term.source_url))
    result = pd.DataFrame(rows)
    assert len(result) == len(queue) and not result.duplicated(["ts_code", "trade_date"]).any()
    result.to_parquet(private / "merger_valuations.parquet", index=False)
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), resolved_stock_periods=len(result),
                   kinds=result.valuation_kind.value_counts().to_dict(), method_version="0.5",
                   scope="Reviewed stock consideration only; no cash-option eligibility assumed, no later quote used",
                   limitations="Two user-approved unlisted-right estimates and five supported suspended-target estimates are not executable cash exits.")
    (root / "outputs/repairs/merger_valuations.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    main(parser.parse_args().course_root.resolve())
