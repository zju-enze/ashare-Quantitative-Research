"""Compare disclosed distributions with suspended reference prices; no portfolio returns."""

import json
from pathlib import Path

import pandas as pd


def ex_reference(last_price, cash_per_share, stock_per_share, reserve_per_share):
    return (last_price - cash_per_share) / (1 + stock_per_share + reserve_per_share)


def main():
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    values = pd.read_csv(private / "suspension_valuation_audit.csv", dtype={"ts_code": str, "trade_date": str})
    references = pd.read_csv(private / "suspension_reference_quotes.csv", dtype={"ts_code": str, "trade_date": str})
    values = values.merge(references, on=["ts_code", "trade_date"], validate="one_to_one", suffixes=("", "_reference"))
    requests = json.loads((private / "suspension_action_fetches.json").read_text(encoding="utf-8"))["requests"]
    records = {(r["ts_code"], r["trade_date"]): r for r in requests}
    rows = []
    for key in values.itertuples(index=False):
        receipt = records[(key.ts_code, key.trade_date)]
        events = pd.concat([pd.read_csv(private / p, dtype=str) for p in receipt["dividend_files"]], ignore_index=True)
        dates = events.dividOperateDate.str.replace("-", "", regex=False)
        events = events[dates.gt(str(key.last_trade_date)) & dates.le(key.trade_date)].copy()
        events = events.sort_values("dividOperateDate")
        assert not events.duplicated(["code", "dividOperateDate"]).any()
        price = key.last_close
        announced = True
        for event in events.itertuples(index=False):
            announced &= pd.notna(event.dividPlanDate) and event.dividPlanDate <= event.dividOperateDate
            components = [getattr(event, c) for c in ["dividCashPsBeforeTax", "dividStocksPs", "dividReserveToStockPs"]]
            components = [0.0 if pd.isna(v) else float(v) for v in components]
            price = ex_reference(price, *components)
        implied_reference = key.last_close * key.last_adj / key.endpoint_adj
        rows.append(dict(ts_code=key.ts_code, trade_date=key.trade_date,
                         last_trade_date=key.last_trade_date, last_close=key.last_close,
                         distribution_events=len(events), preannounced=announced if len(events) else None,
                         baostock_factor_events=receipt["relevant_factor_events"],
                         theoretical_reference=price, local_factor_implied_reference=implied_reference,
                         price_difference=price-implied_reference, baostock_reference=key.endpoint_close,
                         last_adj=key.last_adj, endpoint_adj=key.endpoint_adj,
                         dividend_sources=";".join(receipt["dividend_files"])))
    result = pd.DataFrame(rows)
    result.to_csv(private / "suspension_action_reconciliation.csv", index=False, encoding="utf-8-sig")
    summary = dict(endpoints=len(result), with_distribution_events=int(result.distribution_events.gt(0).sum()),
                   without_distribution_events=int(result.distribution_events.eq(0).sum()),
                   event_announcement_date_missing_or_late=int(result.preannounced.eq(False).sum()),
                   absolute_price_difference_quantiles=result.price_difference.abs().quantile([0, .5, .9, 1]).to_dict(),
                   limitations="Diagnostic comparison only. No tolerance-based acceptance or price imputation applied; unresolved rights/merger events require specific evidence.")
    (root / "outputs/repairs/suspension_action_reconciliation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
