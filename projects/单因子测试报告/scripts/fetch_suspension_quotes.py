"""Fetch unadjusted reference quotes only for suspension endpoints with factor changes."""

import argparse
import json
from pathlib import Path
import socket
import sys

import pandas as pd


def main(client):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    cache = private / "suspension_quotes"
    cache.mkdir(exist_ok=True)
    targets = pd.read_csv(private / "suspension_valuation_audit.csv", dtype=str)
    targets = targets[targets.assessment.eq("corporate_action_review")]
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str).set_index("new_code")
    local = pd.read_csv(private / "endpoint_status_from_local_market.csv", dtype=str).set_index(["ts_code", "trade_date"])
    sys.path.insert(0, str(client))
    socket.setdefaulttimeout(25)
    import baostock as bs
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(login.error_msg)
    log = []
    try:
        for number, key in enumerate(targets.itertuples(index=False), 1):
            raw = key.ts_code
            if raw in aliases.index:
                alias = aliases.loc[raw]
                if pd.notna(alias.switch_date) and pd.Timestamp(key.trade_date) < pd.Timestamp(alias.switch_date):
                    raw = alias.old_code
            assert raw.endswith((".SH", ".SZ"))
            path = cache / f"{key.ts_code}_{key.trade_date}.csv"
            start, end = pd.Timestamp(key.last_trade_date).strftime("%Y-%m-%d"), pd.Timestamp(key.trade_date).strftime("%Y-%m-%d")
            code = raw[-2:].lower() + "." + raw[:6]
            existing_source = None
            if path.exists():
                frame = pd.read_csv(path, dtype=str)
                fetched = False
            elif (key.ts_code, key.trade_date) in local.index:
                existing_source = local.loc[(key.ts_code, key.trade_date), "source_file"]
                frame = pd.read_csv(existing_source, dtype=str)
                frame = frame[frame.date.between(start, end)]
                fetched = False
            else:
                existing = root.parent / "ashare-cointegration/.local/market" / code / "raw.csv"
                if existing.exists():
                    candidate = pd.read_csv(existing, dtype=str)
                    if {start, end} <= set(candidate.date):
                        existing_source = str(existing)
                        frame = candidate[candidate.date.between(start, end)]
                if existing_source:
                    fetched = False
                else:
                    frame = None
            if not path.exists() and not existing_source:
                rs = bs.query_history_k_data_plus(code, "date,code,close,preclose,volume,tradestatus,isST,adjustflag",
                                                 start_date=start, end_date=end, frequency="d", adjustflag="3")
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
                if rs.error_code != "0":
                    raise RuntimeError(f"{code} {end}: {rs.error_code} {rs.error_msg}")
                frame = pd.DataFrame(rows, columns=rs.fields)
                assert len(frame), f"No reference quotes for {code} {start}..{end}"
                assert frame.date.is_unique and frame.code.eq(code).all() and frame.adjustflag.eq("3").all()
                temporary = path.with_suffix(".csv.part")
                frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                temporary.replace(path)
                fetched = True
            anchor, endpoint = frame[frame.date.eq(start)], frame[frame.date.eq(end)]
            assert len(anchor) == len(endpoint) == 1, f"Missing requested endpoints for {code}"
            anchor, endpoint = anchor.iloc[0], endpoint.iloc[0]
            log.append(dict(ts_code=key.ts_code, trade_date=key.trade_date, raw_query_code=code,
                            last_trade_date=key.last_trade_date, rows=len(frame), fetched=fetched,
                            anchor_close=float(anchor.close), original_anchor_close=float(key.last_close),
                            anchor_status=anchor.tradestatus, endpoint_close=float(endpoint.close),
                            endpoint_preclose=float(endpoint.preclose), endpoint_status=endpoint.tradestatus,
                            anchor_matches=abs(float(anchor.close)-float(key.last_close)) < 0.0001,
                            source_file=existing_source or str(path.relative_to(private))))
            receipt = dict(api="BaoStock query_history_k_data_plus adjustflag=3", requested=len(targets), completed=len(log),
                           updated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), requests=log)
            (private / "suspension_quote_fetches.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            if number == 1 or number % 20 == 0 or number == len(targets):
                print(f"Reference quotes {number}/{len(targets)}: {key.ts_code} {end}", flush=True)
    finally:
        bs.logout()
    result = pd.DataFrame(log)
    result.to_csv(private / "suspension_reference_quotes.csv", index=False, encoding="utf-8-sig")
    summary = dict(completed=True, endpoints=len(result), matching_last_traded_quotes=int(result.anchor_matches.sum()),
                   endpoint_status_counts=result.endpoint_status.value_counts().to_dict(),
                   limitation="Suspended reference quotes are valuations, not executable prices; corporate-action reconciliation remains separate")
    (root / "outputs/repairs/suspension_quote_acquisition.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baostock-client", type=Path, required=True)
    main(parser.parse_args().baostock_client.resolve())
