"""Resumable free-source acquisition, bounded strictly to the formation period."""
import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key]="1"
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import json
import socket
import pandas as pd
import baostock as bs
from scripts.probe_sources import query
from src.data import initial_universe,audit_quotes

ROOT=Path(__file__).resolve().parent


def login():
    socket.setdefaulttimeout(60)
    response=bs.login()
    if response.error_code!="0": raise RuntimeError(response.error_msg)


def fetch(task):
    code,calendar=task
    folder=ROOT/".local"/"market"/code;folder.mkdir(parents=True,exist_ok=True)
    status=folder/"status.json"
    if status.exists():
        saved=json.loads(status.read_text())
        if saved["status"]=="complete":return saved
    def read_or_fetch(name,call):
        path=folder/(name+".csv")
        if path.exists():return pd.read_csv(path,dtype=str,keep_default_na=False)
        df=query(call())
        temporary=path.with_suffix(".tmp");df.to_csv(temporary,index=False);temporary.replace(path)
        return df
    raw=read_or_fetch("raw",lambda:bs.query_history_k_data_plus(code,
        "date,code,close,preclose,volume,tradestatus,isST","2021-01-01","2025-12-31",
        frequency="d",adjustflag="3"))
    preliminary,reasons,_=audit_quotes(raw,None,None,calendar)
    if not reasons:
        hfq=read_or_fetch("hfq",lambda:bs.query_history_k_data_plus(code,"date,code,close",
            "2021-01-01","2025-12-31",frequency="d",adjustflag="1"))
        factors=read_or_fetch("factors",lambda:bs.query_adjust_factor(code,"1990-01-01","2025-12-31"))
        info,reasons,adjusted=audit_quotes(raw,hfq,factors,calendar)
        if adjusted is not None:
            pd.DataFrame({"date":calendar,"adjusted_close":adjusted}).to_parquet(folder/"adjusted.parquet",index=False)
    else:
        info=preliminary
    result=dict(code=code,status="complete",retrieved_at=datetime.now(timezone.utc).isoformat(),
                source="BaoStock 0.9.4",exclusion_tags=reasons,**info)
    tmp=status.with_suffix(".tmp");tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(status)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--workers",type=int,default=8)
    args=parser.parse_args()
    basic,catalogue,calendar=initial_universe(ROOT/".local"/"sources")
    out=ROOT/"results";out.mkdir(exist_ok=True)
    basic.to_parquet(ROOT/".local"/"initial_universe.parquet",index=False)
    eligible=basic.loc[basic.primary_exclusion.isna()]
    codes=eligible.code.tolist()
    progress=dict(status="running",planned_stocks=len(codes),completed_stocks=0,
                  calendar_days=len(calendar),workers=args.workers,errors=[])
    def save():
        progress["updated_at"]=datetime.now(timezone.utc).isoformat()
        (out/"acquisition_status.json").write_text(json.dumps(progress,indent=2))
    save()
    with ProcessPoolExecutor(max_workers=args.workers,initializer=login) as pool:
        futures={pool.submit(fetch,(code,calendar)):code for code in codes}
        for future in as_completed(futures):
            code=futures[future]
            try:
                future.result();progress["completed_stocks"]+=1
            except Exception as exc:
                progress["errors"].append(dict(code=code,error=type(exc).__name__+": "+str(exc)))
            if (progress["completed_stocks"]+len(progress["errors"]))%50==0:
                save();print(f"{progress['completed_stocks']}/{len(codes)}; errors={len(progress['errors'])}",flush=True)
    progress["status"]="complete" if not progress["errors"] else "incomplete_errors"
    save()


if __name__=="__main__":
    main()
