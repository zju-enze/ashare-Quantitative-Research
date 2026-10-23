"""Derive gate/increment diagnostics from completed, saved simulation panels."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from src.simulation import STAGES

ROOT=Path(__file__).resolve().parents[1]


def diagnostics(full):
    records=[]
    for domain,key in [("L3","L3_family"),("L2","L2"),("GLOBAL",None)]:
        groups=[("GLOBAL",full)] if key is None else full.groupby(key)
        for family,g in groups:
            truth=g.true_alternative.to_numpy(bool)
            excluded=(g.compute_status=="precheck_placeholder").to_numpy()
            prior=np.zeros(len(g),dtype=bool)
            for method in ("BF","Holm","BH"):
                reject=g[f"reject_{domain}_{method}"].to_numpy(bool)
                assert not (prior & ~reject).any(),"Non-nested methods on same family"
                increment=reject & ~prior
                records.append(dict(domain=domain,family=family,method=method,
                    increment_true=int((increment & truth).sum()),
                    increment_false=int((increment & ~truth).sum()),
                    alternatives=int(truth.sum()),gate_excluded_alternatives=int((truth & excluded).sum()),
                    conditional_power=float((reject & truth).sum()/(truth & ~excluded).sum())
                        if (truth & ~excluded).any() else np.nan))
                prior=reject
    return pd.DataFrame(records)


def main():
    output=ROOT/"results/simulation";summaries=[];counts={}
    for stage in STAGES:
        paths=sorted(p for p in (ROOT/".local/simulation"/stage).glob("*/*.parquet")
                     if ".pairs." not in p.name)
        rows=[]
        for p in paths:
            full=pd.read_parquet(p.with_name(p.stem+".pairs.parquet"))
            result=diagnostics(full)
            result["scenario"]=p.parent.name;result["repetition"]=int(p.stem)
            rows.append(result)
        counts[stage]={"completed_panels":len(paths),
                       "planned_panels":STAGES[stage][3]*len(STAGES[stage][4])}
        if not rows:continue
        data=pd.concat(rows,ignore_index=True)
        for keys,g in data.groupby(["scenario","domain","family","method"]):
            row=dict(zip(["scenario","domain","family","method"],keys),stage=stage,B=len(g))
            for field in ("increment_true","increment_false","alternatives",
                          "gate_excluded_alternatives","conditional_power"):
                values=g[field].dropna()
                row[field+"_mean"]=float(values.mean()) if len(values) else None
                row[field+"_MCSE"]=float(values.std(ddof=1)/np.sqrt(len(values))) if len(values)>1 else None
            summaries.append(row)
    pd.DataFrame(summaries).to_csv(output/"increment_and_gate_diagnostics.csv",index=False)
    (output/"diagnostics_snapshot.json").write_text(json.dumps(dict(
        recorded_at=datetime.now(timezone.utc).isoformat(),coverage=counts,
        interpretation="Gate-excluded true alternatives are not a measured counterfactual power loss. Conditional power uses surviving alternatives; primary power remains unconditional.",
        increments="BF core; Holm minus BF; BH minus Holm; computed per fixed family and panel"),indent=2))
    print(counts)


if __name__=="__main__":
    main()
