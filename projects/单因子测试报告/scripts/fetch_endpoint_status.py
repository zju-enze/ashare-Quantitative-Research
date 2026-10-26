"""Fetch daily market status only for endpoint gaps not explained by local records."""

import argparse
import json
from pathlib import Path
import socket
import sys

import pandas as pd

from prepare_local_repairs import canonical_codes, collapse_equal_alias_rows


def read_status_snapshot(bs, day):
    for attempt in range(2):
        rs = bs.query_all_stock(day=day)
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        if rs.error_code == "0":
            return pd.DataFrame(rows, columns=rs.fields)
        if rs.error_code != "10001001" or attempt:
            raise RuntimeError(f"{day}: {rs.error_code} {rs.error_msg}")
        # The free session expired during the observed long fetch; renew once, retaining completed files.
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(login.error_msg)


def main(course, client):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local" / "data_repairs"
    public = root / "outputs" / "repairs"
    aliases = pd.read_csv(private / "security_aliases.csv", dtype=str)
    issues = pd.read_csv(root / ".local" / "preflight" / "endpoint_issues.csv", dtype=str)
    parts = []
    for endpoint in ["entry", "exit"]:
        part = issues[issues[endpoint + "_price_ok"].eq("False")][["ts_code", endpoint + "_date"]]
        parts.append(part.rename(columns={endpoint + "_date": "trade_date"}))
    keys = pd.concat(parts).drop_duplicates()
    keys.ts_code = canonical_codes(keys.ts_code, aliases)
    local = pd.read_csv(private / "endpoint_status_from_local_market.csv", dtype=str)
    susp = pd.read_parquet(course / "data" / "offline" / "suspend_d.parquet")
    susp.ts_code = canonical_codes(susp.ts_code, aliases)
    known_susp = susp[susp.suspend_type.eq("S") & susp.suspend_timing.isna()][["ts_code", "trade_date"]]
    known = pd.concat([local[["ts_code", "trade_date"]], known_susp]).drop_duplicates()
    remaining = keys.merge(known.assign(known=True), on=["ts_code", "trade_date"], how="left")
    remaining = remaining[remaining.known.isna() & remaining.ts_code.str.endswith((".SH", ".SZ"))]
    repaired_issues = root / ".local/preflight_repaired/state_issues.csv"
    if repaired_issues.exists():
        extra = pd.read_csv(repaired_issues, dtype=str)
        extra = extra[extra.entry_state.eq("unknown")][["ts_code", "entry_date"]].rename(columns={"entry_date": "trade_date"})
        remaining = pd.concat([remaining[["ts_code", "trade_date"]], extra], ignore_index=True).drop_duplicates()
    dates = sorted(remaining.trade_date.unique())
    remaining.to_csv(private / "status_request_keys.csv", index=False, encoding="utf-8-sig")
    sys.path.insert(0, str(client))
    socket.setdefaulttimeout(25)
    import baostock as bs
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(login.error_msg)
    log, matches = [], []
    try:
        for number, date in enumerate(dates, 1):
            iso = pd.Timestamp(date).strftime("%Y-%m-%d")
            path = private / f"baostock_market_status_{iso}.csv"
            if path.exists():
                frame = pd.read_csv(path, dtype=str)
                fetched = False
            else:
                # Use the SDK's row iterator; get_data() uses removed pandas.append when paginating.
                frame = read_status_snapshot(bs, iso)
                assert len(frame) and frame.code.is_unique
                assert frame.tradeStatus.isin(["0", "1"]).all()
                temporary = path.with_suffix(".csv.part")
                frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                temporary.replace(path)
                fetched = True
            assert frame.code.is_unique and frame.tradeStatus.isin(["0", "1"]).all()
            market_rows = len(frame)
            frame["ts_code"] = canonical_codes(frame.code.str[3:] + "." + frame.code.str[:2].str.upper(), aliases)
            frame["trade_date"] = date
            target = remaining[remaining.trade_date.eq(date)][["ts_code", "trade_date"]]
            frame = frame[frame.ts_code.isin(target.ts_code)]
            frame = collapse_equal_alias_rows(frame, ["ts_code", "trade_date"], ["tradeStatus"])
            hit = target.merge(frame, on=["ts_code", "trade_date"], how="left", validate="one_to_one")
            matches.append(hit)
            log.append(dict(date=date, market_rows=market_rows, request_keys=len(target),
                            matched_keys=int(hit.tradeStatus.notna().sum()), fetched=fetched, file=path.name))
            receipt = dict(api="BaoStock query_all_stock", requested_dates=len(dates), completed_dates=len(log),
                           updated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(), requests=log)
            (private / "market_status_fetches.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            if number == 1 or number % 10 == 0 or number == len(dates):
                print(f"Market status {number}/{len(dates)}: {date}, matched {hit.tradeStatus.notna().sum()}/{len(target)}", flush=True)
    finally:
        bs.logout()
    result = pd.concat(matches, ignore_index=True)
    result.to_csv(private / "endpoint_market_status.csv", index=False, encoding="utf-8-sig")
    summary = dict(completed=True, requested_dates=len(dates), request_keys=len(remaining),
                   matched_keys=int(result.tradeStatus.notna().sum()),
                   daily_status_counts=result.tradeStatus.value_counts(dropna=False).to_dict(),
                   scope="Original endpoint gaps plus unknown entry states from repaired preflight when available",
                   limitation="Daily trading status does not identify every intraday halt or a missing terminal value")
    (public / "endpoint_status_acquisition.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--baostock-client", type=Path, required=True)
    args = parser.parse_args()
    main(args.course_root.resolve(), args.baostock_client.resolve())
