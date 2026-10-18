"""Targeted checks against two official, preselected company announcements."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from decimal import Decimal,ROUND_HALF_UP
import json
import pandas as pd
import baostock as bs
from collect_market import ROOT,login,fetch

CASES=[
    ("sh.601166","2024-07-09","1.04","0",
     "https://download.cib.com.cn/netbank/download/cn/announcements/20240703/20240703_2.pdf"),
    ("sz.300750","2023-04-26","2.52","0.8",
     "https://static.cninfo.com.cn/finalpage/2023-04-18/1216457838.PDF"),
]


def main():
    calendar=pd.read_csv(ROOT/".local/sources/calendar.csv",dtype=str)
    dates=calendar.loc[calendar.is_trading_day=="1","calendar_date"].tolist()
    rows=[]
    for code,date,cash,transfer,url in CASES:
        folder=ROOT/".local/market"/code
        if not (folder/"status.json").exists():
            login()
            try:fetch((code,dates))
            finally:bs.logout()
        d=pd.read_csv(folder/"raw.csv",dtype=str);f=pd.read_csv(folder/"factors.csv",dtype=str)
        i=d.index[d.date==date][0]
        previous=Decimal(d.loc[i-1,"close"]);reported=Decimal(d.loc[i,"preclose"])
        expected=((previous-Decimal(cash))/(1+Decimal(transfer))).quantize(Decimal(".01"),rounding=ROUND_HALF_UP)
        rows.append(dict(code=code,ex_date=date,cash_per_share=cash,capital_transfer_per_share=transfer,
            previous_close=str(previous),reported_ex_reference=str(reported),expected_reference=str(expected),
            exact_reference_match=reported==expected,factor_event_present=bool(f.dividOperateDate.eq(date).any()),
            official_source=url,scope="targeted case; not exhaustive independent corporate-action verification"))
    (ROOT/"results/corporate_action_cases.json").write_text(json.dumps(rows,indent=2))
    if not all(r["exact_reference_match"] and r["factor_event_present"] for r in rows):
        raise RuntimeError("Official corporate-action case mismatch")
    print("Official cash-dividend and capital-transfer cases passed")


if __name__=="__main__":
    main()
