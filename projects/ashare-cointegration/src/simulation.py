"""Predeclared panel DGPs and fixed-family diagnostics, independent of market results."""
from pathlib import Path
from time import perf_counter
import numpy as np
import pandas as pd
from scipy.signal import lfilter
from statsmodels.stats.proportion import proportion_confint
from .engine import applicability, candidates, correct, test_pair, METHODS

SCENARIOS = [f"N{i}" for i in range(8)] + [f"A{i}" for i in range(6)] + ["M0","M1"]
STAGES = {"S0": (0,2,4,5,SCENARIOS), "S1": (1,4,10,1000,SCENARIOS),
          "S2": (2,4,30,500,["N1","N5","N6","M1"])}


def panel(stage, scenario, repetition, nobs=1212):
    sid, groups, size, _, _ = STAGES[stage]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [20261018,sid,SCENARIOS.index(scenario),repetition])))
    burn = 2000
    count = 1 + groups + groups*size
    shape = (burn+nobs,count)
    innovations = (rng.standard_t(5,size=shape)*np.sqrt(3/5)
                   if scenario in ("N3","N7") else rng.normal(size=shape))
    if scenario in ("N2","N7"):
        innovations = lfilter([np.sqrt(.75)],[1,-.5],innovations,axis=0)
    if scenario == "N4":
        h = np.ones(count)
        for t in range(burn+nobs):
            innovations[t] *= np.sqrt(h)
            h = .05 + .05*innovations[t]**2 + .90*h
    innovations = innovations[burn:].copy()
    if scenario in ("N5","N7","M1"):
        innovations[nobs//2:] *= 3
    if scenario == "N6":
        innovations[:nobs//4] *= 3
    trends = innovations.cumsum(axis=0)
    trends -= trends[0]
    phi, sigma, lam = .5,.25,.1 if scenario=="N1" else 1.
    if scenario.startswith("A"):
        aid = int(scenario[1:]);phi=(.80,.95,.99)[aid//2];sigma=(.25,1.)[aid%2]
    elif scenario.startswith("M"):
        phi,sigma=.95,1.
    e = lfilter([np.sqrt(1-phi**2)],[1,-phi],rng.normal(size=(burn+nobs,groups*size)),axis=0)[burn:]
    records, values, clusters = [], {}, {}
    for g in range(groups):
        for j in range(size):
            code = f"S{g:02d}{j:03d}"
            cluster = (0 if scenario.startswith("A") else
                       (j%5//2 if j%5<4 else j) if scenario.startswith("M") else j)
            c = .8+.4*j/(size-1)
            x = 10000+5*(g*size+j) + c*(trends[:,0]+trends[:,1+g]+
                lam*trends[:,1+groups+g*size+cluster]) + sigma*e[:,g*size+j]
            if not np.isfinite(x).all() or x[0]==0:
                raise ArithmeticError("Invalid generated panel; do not redraw")
            values[code] = 100*x/x[0]
            records.append(dict(ts_code=code,name=code,L2=f"G{g}",L3=f"G{g}L{j//(size//2)}"))
            clusters[code] = cluster
    u = pd.DataFrame(records);h = candidates(u)
    h["true_alternative"] = [clusters[a]==clusters[b] for a,b in zip(h.A,h.B)]
    return u,h,values


def family_metrics(table):
    rows = []
    for domain,key in [("L3","L3_family"),("L2","L2"),("GLOBAL",None)]:
        groups = [("GLOBAL",table)] if key is None else table.groupby(key)
        for family,group in groups:
            truth = group.true_alternative.to_numpy(bool)
            for method in METHODS:
                reject = group[f"reject_{domain}_{method}"].to_numpy(bool)
                R,V,A = int(reject.sum()),int((reject & ~truth).sum()),int(truth.sum())
                rows.append(dict(domain=domain,family=family,method=method,R=R,V=V,A=A,
                    false_any=int(V>0),FDP=V/max(R,1),
                    power=float((reject & truth).sum()/A) if A else np.nan,
                    raw_null_rejection=float((group.p_for_adjustment.to_numpy()[~truth]<.05).mean()) if (~truth).any() else np.nan,
                    applicable_pair_fraction=float(group.EG_executed.mean())))
    return pd.DataFrame(rows)


def run_repetition(task):
    stage,scenario,repetition,outdir = task
    folder = Path(outdir)/stage/scenario; folder.mkdir(parents=True,exist_ok=True)
    destination = folder/f"{repetition:04d}.parquet"
    if destination.exists():
        return pd.read_parquet(destination)
    start = perf_counter()
    u,h,values = panel(stage,scenario,repetition)
    gates = {s:applicability(values[s]) for s in u.ts_code}
    results = [test_pair((r,values[r["A"]],values[r["B"]],gates[r["A"]],gates[r["B"]]))
               for r in h.to_dict("records")]
    full,_ = correct(pd.DataFrame(results))
    metrics = family_metrics(full)
    metrics["stage"]=stage;metrics["scenario"]=scenario;metrics["repetition"]=repetition
    metrics["stock_I1_fraction"]=np.mean([x["compatible"] for x in gates.values()])
    metrics["numerical_count"]=(full.compute_status=="numerically_ineligible").sum()
    metrics["tail_zero_count"]=(full.compute_status=="tail_unresolved").sum()
    metrics["seconds"]=perf_counter()-start
    for domain in ("L2","L3"):
        for method in METHODS:
            mask=(metrics.domain==domain)&(metrics.method==method)
            metrics.loc[mask,"any_local_family_false"]=int(metrics.loc[mask,"V"].gt(0).any())
    full.to_parquet(folder/f"{repetition:04d}.pairs.parquet",index=False)
    tmp = destination.with_suffix(".tmp");metrics.to_parquet(tmp,index=False);tmp.replace(destination)
    return metrics


def summarize(metrics):
    rows=[]
    for keys,g in metrics.groupby(["stage","scenario","domain","family","method"]):
        row=dict(zip(["stage","scenario","domain","family","method"],keys))
        B=len(g); row["B"]=B
        for field,label in [("false_any","FWER"),("FDP","FDR"),("power","power"),
                            ("raw_null_rejection","raw_null_rejection"),
                            ("stock_I1_fraction","stock_I1_fraction"),
                            ("applicable_pair_fraction","applicable_pair_fraction"),
                            ("any_local_family_false","any_local_family_FWER")]:
            x=g[field].dropna()
            row[label]=float(x.mean()) if len(x) else None
            row[label+"_MCSE"]=float(x.std(ddof=1)/np.sqrt(len(x))) if len(x)>1 else None
        lo,hi=proportion_confint(int(g.false_any.sum()),B,alpha=.05,method="wilson")
        row.update(FWER_Wilson_low=float(lo),FWER_Wilson_high=float(hi),
                   main_alarm=bool(keys[2]=="L2" and keys[4]=="Holm" and lo>.05))
        rows.append(row)
    return pd.DataFrame(rows)
