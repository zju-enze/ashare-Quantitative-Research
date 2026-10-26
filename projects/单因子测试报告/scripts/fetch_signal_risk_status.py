"""Fill historical risk-status gaps from source daily isST records, not current names."""

import argparse
import json
from pathlib import Path
import socket
import sys

import pandas as pd

from fetch_suspension_actions import read_response


def main(client):
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    cache = private / "signal_risk"
    cache.mkdir(exist_ok=True)
    issues = pd.read_csv(root / ".local/preflight_repaired/state_issues.csv", dtype=str)
    needed = issues[issues.name_unknown.eq("True") & issues.entry_state.eq("tradable")][["ts_code", "signal_date"]].drop_duplicates()
    sys.path.insert(0, str(client))
    socket.setdefaulttimeout(25)
    import baostock as bs
    if bs.login().error_code != "0":
        raise RuntimeError("BaoStock login failed")
    records, requests = [], []
    try:
        for code, keys in needed.groupby("ts_code"):
            raw = code[-2:].lower() + "." + code[:6]
            start, end = keys.signal_date.min(), keys.signal_date.max()
            path = cache / f"{code}_{start}_{end}.csv"
            existing = root.parent / "ashare-cointegration/.local/market" / raw / "raw.csv"
            frame, source = None, None
            if path.exists():
                frame, source = pd.read_csv(path, dtype=str), str(path.relative_to(private))
            elif existing.exists():
                local = pd.read_csv(existing, dtype=str)
                local_dates = local.date.str.replace("-", "", regex=False)
                if set(keys.signal_date) <= set(local_dates):
                    frame, source = local[local_dates.between(start, end)], str(existing)
            if frame is None:
                frame = read_response(bs.query_history_k_data_plus(raw, "date,code,close,volume,tradestatus,isST",
                    start_date=pd.Timestamp(start).strftime("%Y-%m-%d"), end_date=pd.Timestamp(end).strftime("%Y-%m-%d"),
                    frequency="d", adjustflag="3"))
                assert frame.code.eq(raw).all() and frame.date.is_unique
                temporary = path.with_suffix(".csv.part")
                frame.to_csv(temporary, index=False, encoding="utf-8-sig")
                temporary.replace(path)
                source = str(path.relative_to(private))
            frame["signal_date"] = frame.date.str.replace("-", "", regex=False)
            hit = keys.merge(frame[["signal_date", "isST", "tradestatus"]], on="signal_date", how="left", validate="one_to_one")
            assert hit.isST.dropna().isin(["0", "1"]).all()
            hit["source_file"] = source
            records.append(hit)
            requests.append(dict(ts_code=code, start_date=start, end_date=end, requested_signals=len(keys),
                                 matched=int(hit.isST.notna().sum()), source_file=source))
            print(f"Signal risk {code}: {hit.isST.notna().sum()}/{len(keys)}", flush=True)
    finally:
        bs.logout()
    result = pd.concat(records, ignore_index=True)
    result.to_csv(private / "signal_risk_status.csv", index=False, encoding="utf-8-sig")
    (private / "signal_risk_fetches.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = dict(requested=len(result), matched=int(result.isST.notna().sum()),
                   risk_status_counts=result.isST.value_counts(dropna=False).to_dict(),
                   scope="Only signal dates with missing historical name records; vendor historical isST, not current-name inference")
    (root / "outputs/repairs/signal_risk_status.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baostock-client", type=Path, required=True)
    main(parser.parse_args().baostock_client.resolve())
