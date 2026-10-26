"""Apply documented academic valuation continuation to confirmed held suspension exits."""

from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np
import pandas as pd

from reconcile_suspension_actions import ex_reference


def reference_tick(price):
    return float(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main():
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    audit = pd.read_csv(private / "suspension_valuation_audit.csv", dtype={"ts_code": str, "trade_date": str, "last_trade_date": str})
    receipt = json.loads((private / "suspension_action_fetches.json").read_text(encoding="utf-8"))["requests"]
    requests = {(r["ts_code"], r["trade_date"]): r for r in receipt}
    special = json.loads((private / "special_corporate_actions.json").read_text(encoding="utf-8"))
    references = pd.read_csv(private / "suspension_reference_quotes.csv", dtype={"ts_code": str, "trade_date": str}).set_index(["ts_code", "trade_date"])
    rows = []
    for key in audit.itertuples(index=False):
        price, factor, value = key.last_close, key.last_adj, np.nan
        kind, sources = "unresolved", ""
        if key.assessment == "constant_adjustment_candidate":
            kind = "last_trade_carry_no_factor_change"
            value = price * factor
        elif key.assessment == "corporate_action_review":
            request = requests[(key.ts_code, key.trade_date)]
            distributions = pd.concat([pd.read_csv(private / p, dtype=str) for p in request["dividend_files"]], ignore_index=True)
            dates = distributions.dividOperateDate.str.replace("-", "", regex=False)
            distributions = distributions[dates.gt(key.last_trade_date) & dates.le(key.trade_date)].sort_values("dividOperateDate")
            manual = [e for e in special if e["ts_code"] == key.ts_code and key.last_trade_date < e["event_date"] <= key.trade_date]
            if manual:
                assert len(manual) == 1 and distributions.empty
                event = manual[0]
                assert event["publication_date"] <= event["event_date"] <= key.trade_date
                assert event["record_date"] >= key.last_trade_date
                kind, sources = event["kind"], event["source_url"]
                if kind == "share_transfer_without_ex_reference":
                    value = price * factor * (1 + event["shares_per_old_share"])
                    # Existing-share consideration increases held units; the issuer explicitly prohibits ex-reference repricing.
                    price = value / factor
                elif kind == "special_cash_dividend":
                    price = reference_tick(price - event["cash_per_share"])
                    factor, value = key.endpoint_adj, price * key.endpoint_adj
                elif kind == "rights_issue":
                    price = reference_tick((price + event["rights_per_share"] * event["subscription_price"]) / (1 + event["rights_per_share"]))
                    factor, value = key.endpoint_adj, price * key.endpoint_adj
            elif len(distributions):
                for event in distributions.itertuples(index=False):
                    assert pd.notna(event.dividPlanDate) and event.dividPlanDate <= event.dividOperateDate
                    components = [getattr(event, field) for field in ["dividCashPsBeforeTax", "dividStocksPs", "dividReserveToStockPs"]]
                    components = [0.0 if pd.isna(v) else float(v) for v in components]
                    assert all(v >= 0 for v in components)
                    price = reference_tick(ex_reference(price, *components))
                factor, value = key.endpoint_adj, price * key.endpoint_adj
                kind, sources = "distribution_adjusted_reference", ";".join(request["dividend_files"])
            else:
                reference = references.loc[(key.ts_code, key.trade_date)]
                if key.factor_3dp_unique == 1 and request["relevant_factor_events"] == 0 and reference.endpoint_close == key.last_close:
                    kind = "precision_only_keep_last_adjusted_value"
                    sources = request["factor_source"]
                    value = price * factor
        assert not np.isfinite(value) or value > 0
        rows.append(dict(ts_code=key.ts_code, trade_date=key.trade_date, last_trade_date=key.last_trade_date,
                         reference_value_per_old_share=price, factor_used=factor, adjusted_value=value,
                         vendor_endpoint_factor=key.endpoint_adj, valuation_kind=kind, event_sources=sources,
                         tradable_at_endpoint=False))
    result = pd.DataFrame(rows)
    assert len(result) == len(audit) and not result.duplicated(["ts_code", "trade_date"]).any()
    result.to_parquet(private / "suspension_valuations.parquet", index=False)
    summary = dict(checked_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), endpoints=len(result),
                   resolved=int(result.adjusted_value.notna().sum()), unresolved=int(result.adjusted_value.isna().sum()),
                   kinds=result.valuation_kind.value_counts().to_dict(),
                   scope="Held suspension exits only; original data and frozen signal samples unchanged",
                   limitations=["Academic endpoint valuations, not executable exit prices.",
                                "Pre-tax distribution/reference-price convention follows adjusted-price research; no investor-specific tax, subscription funding or trading model.",
                                "Entry-to-endpoint returns have not been calculated by this script; no whole holding-period return is set to zero."])
    (root / "outputs/repairs/suspension_valuations.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
