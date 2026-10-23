"""Separate binary64 conversion/operation error from exact source-record identity."""
from decimal import Decimal,localcontext
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--run-id",default="formation-2021-2025-v2")
    args=parser.parse_args();run=ROOT/".local/production"/args.run_id
    u=pd.read_parquet(run/"U.parquet");values=np.load(run/"prices.npy",mmap_mode="r")
    rows=[]
    with localcontext() as context:
        context.prec=60
        unit=Decimal(2)**-53
        gamma6=6*unit/(1-6*unit)
        for i,row in enumerate(u.itertuples()):
            folder=ROOT/".local/market"/row.code
            raw=pd.read_csv(folder/"raw.csv",dtype=str);factors=pd.read_csv(folder/"factors.csv",dtype=str)
            raw["date_dt"]=pd.to_datetime(raw.date)
            factors["date_dt"]=pd.to_datetime(factors.dividOperateDate)
            expanded=pd.merge_asof(raw,factors.sort_values("date_dt")[["date_dt","backAdjustFactor"]],
                                   on="date_dt",direction="backward")
            seed=Decimal(row.seed_factor);max_error=Decimal(0);max_ratio=Decimal(0)
            for p,f,actual in zip(expanded.close,expanded.backAdjustFactor,values[:,i]):
                exact=Decimal(p)*Decimal(f)/seed
                error=abs(Decimal.from_float(float(actual))-exact)
                bound=gamma6*abs(exact)
                assert error<=bound,"Binary64 coordinate differs beyond operation bound"
                max_error=max(max_error,error);max_ratio=max(max_ratio,error/bound)
            rows.append(dict(ts_code=row.ts_code,max_absolute_error=float(max_error),
                             max_fraction_of_bound=float(max_ratio)))
    pd.DataFrame(rows).to_csv(run/"float_coordinate_audit.csv",index=False)
    summary=dict(status="passed",run_id=args.run_id,stocks=len(rows),rows=int(values.size),
                 reference="60-digit Decimal P*F/F_first from original response strings",
                 relative_error_bound="gamma_6 = 6u/(1-6u), u=2^-53; positive normal binary64 inputs",
                 max_absolute_error=max(r["max_absolute_error"] for r in rows),
                 max_fraction_of_bound=max(r["max_fraction_of_bound"] for r in rows),
                 scope="Binary conversion and arithmetic only; does not relax zero-tolerance native Decimal identity or quantify latent supplier rounding")
    (ROOT/"results/float_coordinate_audit.json").write_text(json.dumps(summary,indent=2))
    print(summary)


if __name__=="__main__":
    main()
