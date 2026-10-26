"""Acquire distribution/event records for the bounded suspension valuation exceptions."""

import argparse
import json
from pathlib import Path
import socket
import sys

import pandas as pd


def read_response(response):
    rows = []
    while response.error_code == "0" and response.next():
        rows.append(response.get_row_data())
    if response.error_code != "0":
        raise RuntimeError(f"{response.error_code}: {response.error_msg}")
    return pd.DataFrame(rows, columns=response.fields)


def main(client):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    dividend_dir, factor_dir = private / "dividends", private / "adjustment_events"
    dividend_dir.mkdir(exist_ok=True)
    factor_dir.mkdir(exist_ok=True)
    targets = pd.read_csv(private / "suspension_reference_quotes.csv", dtype=str)
    local = pd.read_csv(private / "endpoint_status_from_local_market.csv", dtype=str).set_index(["ts_code", "trade_date"])
    sys.path.insert(0, str(client))
    socket.setdefaulttimeout(25)
    import baostock as bs
    if bs.login().error_code != "0":
        raise RuntimeError("BaoStock login failed")
    log = []
    try:
        for number, key in enumerate(targets.itertuples(index=False), 1):
            code = key.raw_query_code
            files = []
            fetched = 0
            for year in range(int(key.last_trade_date[:4]), int(key.trade_date[:4]) + 1):
                path = dividend_dir / f"{code}_{year}.csv"
                if not path.exists():
                    frame = read_response(bs.query_dividend_data(code, year=str(year), yearType="operate"))
                    assert frame.empty or frame.code.eq(code).all()
                    temporary = path.with_suffix(".csv.part")
                    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                    temporary.replace(path)
                    fetched += 1
                files.append(str(path.relative_to(private)))
            path = factor_dir / f"{key.ts_code}_{key.trade_date}.csv"
            existing = None
            if (key.ts_code, key.trade_date) in local.index:
                candidate = Path(local.loc[(key.ts_code, key.trade_date), "source_file"]).with_name("factors.csv")
                if candidate.exists():
                    existing = candidate
            if existing:
                frame = pd.read_csv(existing, dtype=str)
                source = str(existing)
            elif path.exists():
                frame = pd.read_csv(path, dtype=str)
                source = str(path.relative_to(private))
            else:
                frame = read_response(bs.query_adjust_factor(code,
                    start_date=pd.Timestamp(key.last_trade_date).strftime("%Y-%m-%d"),
                    end_date=pd.Timestamp(key.trade_date).strftime("%Y-%m-%d")))
                assert frame.empty or frame.code.eq(code).all()
                temporary = path.with_suffix(".csv.part")
                frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                temporary.replace(path)
                fetched += 1
                source = str(path.relative_to(private))
            dates = frame.dividOperateDate.str.replace("-", "", regex=False)
            relevant = frame[dates.gt(key.last_trade_date) & dates.le(key.trade_date)]
            log.append(dict(ts_code=key.ts_code, trade_date=key.trade_date, last_trade_date=key.last_trade_date,
                            dividend_files=files, factor_source=source, relevant_factor_events=len(relevant), fetched_requests=fetched))
            (private / "suspension_action_fetches.json").write_text(json.dumps(dict(
                api="BaoStock dividend operate-year and adjustment event queries", requested_endpoints=len(targets),
                completed_endpoints=len(log), updated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
                requests=log), ensure_ascii=False, indent=2), encoding="utf-8")
            if number == 1 or number % 20 == 0 or number == len(targets):
                print(f"Suspension actions {number}/{len(targets)}", flush=True)
    finally:
        bs.logout()
    summary = dict(completed=True, endpoints=len(log), fetched_requests=sum(r["fetched_requests"] for r in log),
                   endpoints_with_factor_events=sum(r["relevant_factor_events"] > 0 for r in log),
                   scope="Bounded to suspended endpoints with changes in original cumulative factors; no return calculation")
    (root / "outputs/repairs/suspension_action_acquisition.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baostock-client", type=Path, required=True)
    main(parser.parse_args().baostock_client.resolve())
