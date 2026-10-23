"""Single-worker deployment check using supplied synthetic arrays, never S2 panels."""
import os
for variable in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
from concurrent.futures import ProcessPoolExecutor
import ctypes
import importlib.metadata as metadata
import json
import platform
import tempfile
import warnings
import numpy as np
import pandas as pd
import scipy
from statsmodels.tsa.stattools import coint
from src.engine import applicability,candidates,correct,eg_audit,test_pair

ROOT=Path(__file__).resolve().parents[1]


def blas_threads():
    results=[]
    for package in ("numpy","scipy"):
        folder=Path(np.__file__).parent.parent/(package+".libs")
        for path in folder.glob("*openblas*"):
            lib=ctypes.CDLL(str(path))
            for symbol in ("scipy_openblas_get_num_threads64_","scipy_openblas_get_num_threads",
                           "openblas_get_num_threads64_","openblas_get_num_threads"):
                try: getter=getattr(lib,symbol)
                except AttributeError: continue
                getter.restype=ctypes.c_int
                results.append(dict(package=package,library=path.name,threads=getter()))
                break
    assert {r["package"] for r in results}=={"numpy","scipy"},"BLAS getter unavailable"
    assert all(r["threads"]==1 for r in results),"BLAS must use one thread"
    return results


def compare(expected,actual,path=""):
    if isinstance(expected,dict):
        assert expected.keys()==actual.keys(),path
        for key in expected: compare(expected[key],actual[key],path+"/"+key)
    elif isinstance(expected,list):
        assert len(expected)==len(actual),path
        for i,(a,b) in enumerate(zip(expected,actual)): compare(a,b,path+"/"+str(i))
    elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
        atol=1e-10 if "p_" in path or path.endswith("/p") else 1e-8
        np.testing.assert_allclose(actual,expected,atol=atol,rtol=1e-10,err_msg=path)
    else:
        assert expected==actual,path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reference",type=Path)
    args=parser.parse_args()
    installed={}
    for line in (ROOT/"requirements.lock.txt").read_text(encoding="utf-8-sig").splitlines():
        name,version=line.split("==")
        installed[name]=metadata.version(name)
        assert installed[name]==version,f"Dependency mismatch: {name}"
    assert sys.version_info[:2]==(3,11)
    data=np.load(args.fixture)
    values={name:data[name] for name in data.files}
    cases={}
    for name in ("independent","negative","tail","collinear"):
        a,b=values[name],values["base"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            actual=coint(a,b,trend="c",autolag="aic",maxlag=None)
        audit=eg_audit(a,b)
        np.testing.assert_allclose(audit["EG_stat"],actual[0],atol=1e-8,rtol=1e-10)
        np.testing.assert_allclose(audit["p_library"],actual[1],atol=1e-10)
        cases[name]=audit
    bad=values["base"].copy();bad[8]=np.nan
    cases["nonfinite"]=eg_audit(bad,values["base"])
    assert cases["collinear"]["p_zero_origin"]=="near_collinearity_forced"
    assert cases["tail"]["p_zero_origin"]=="mackinnon_boundary"
    assert cases["nonfinite"]["placeholder_reason"]=="nonfinite_input"
    u=pd.DataFrame([dict(ts_code=name,name=name,L2="G",L3="L0" if i<2 else "L1")
                    for i,name in enumerate(("base","independent","negative","tail"))])
    registry=candidates(u)
    gates={s:applicability(values[s]) for s in u.ts_code}
    tasks=[(r,values[r["A"]],values[r["B"]],gates[r["A"]],gates[r["B"]])
           for r in registry.to_dict("records")]
    serial=[test_pair(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=1) as pool:
        single_worker=list(pool.map(test_pair,tasks))
    compare(serial,single_worker)
    full,main=correct(pd.DataFrame(serial))
    assert len(full)==6
    assert not main.empty and (main.beta<0).any(),"Synthetic negative-beta discovery missing"
    with tempfile.TemporaryDirectory() as directory:
        file=Path(directory)/"roundtrip.parquet";full.to_parquet(file,index=False)
        pd.testing.assert_frame_equal(full,pd.read_parquet(file))
    # JSON serialization makes nullable correction fields portable across both OSes.
    rows=json.loads(full.to_json(orient="records",double_precision=15))
    numerics=dict(cases=cases,gates=gates,corrected_rows=rows,
                  main_ids=main.candidate_id.tolist())
    if args.reference:
        expected=json.loads(args.reference.read_text(encoding="utf8"))
        assert expected["packages"]==installed
        compare(expected["numerics"],numerics)
    result=dict(status="passed",python=sys.version,platform=platform.platform(),
                packages=installed,worker_count=1,blas=blas_threads(),
                synthetic_only=True,formal_simulation_panels_executed=0,
                reference_compared=bool(args.reference),numerics=numerics)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({k:result[k] for k in ["status","worker_count","blas",
                     "formal_simulation_panels_executed","reference_compared"]}))


if __name__=="__main__":
    main()
