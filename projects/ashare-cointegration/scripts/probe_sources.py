"""Fetch only 2021–2025 quotes and historical metadata from free primary sources."""
from pathlib import Path
import sys
import json
import socket
from datetime import datetime, timezone
import baostock as bs
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".local" / "sources"


def query(result):
    if result.error_code != "0":
        raise RuntimeError(result.error_code + ": " + result.error_msg)
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    frame = pd.DataFrame(rows, columns=result.fields)
    if result.error_code != "0":
        raise RuntimeError(result.error_code + ": " + result.error_msg)
    return frame


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    socket.setdefaulttimeout(40)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(login.error_msg)
    try:
        for name, call in [
            ("calendar", lambda: bs.query_trade_dates("2021-01-01","2025-12-31")),
            ("stock_basic", bs.query_stock_basic),
            ("stock_asof_20251231", lambda: bs.query_all_stock("2025-12-31")),
            ("probe_raw_000001", lambda: bs.query_history_k_data_plus(
                "sz.000001","date,code,close,preclose,volume,tradestatus,isST",
                "2021-01-01","2025-12-31",frequency="d",adjustflag="3")),
            ("probe_hfq_000001", lambda: bs.query_history_k_data_plus(
                "sz.000001","date,code,close","2021-01-01","2025-12-31",frequency="d",adjustflag="1")),
            ("probe_factors_000001", lambda: bs.query_adjust_factor(
                "sz.000001","1990-01-01","2025-12-31"))]:
            path = DEST / (name+".csv")
            if path.exists():
                print(name,"cached",flush=True)
                continue
            frame = query(call())
            frame.to_csv(path,index=False)
            path.with_suffix(".json").write_text(json.dumps(
                dict(retrieved_at=datetime.now(timezone.utc).isoformat(),
                     source="BaoStock 0.9.4",rows=len(frame),query=name,
                     price_window=["2021-01-01","2025-12-31"]),indent=2))
            print(name,len(frame),flush=True)
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
