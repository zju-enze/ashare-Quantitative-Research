import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key]="1"
from pathlib import Path
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from datetime import datetime,timezone
import pandas as pd
from src.simulation import STAGES,run_repetition,summarize

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=STAGES,required=True)
    parser.add_argument("--workers",type=int,default=8)
    args=parser.parse_args()
    state_path=ROOT/"results"/"simulation"/(args.stage+"_status.json")
    if state_path.exists() and json.loads(state_path.read_text())["status"]=="held_by_user":
        print(f"{args.stage}: held by user; no simulation started. Explicit release is required.",flush=True)
        return
    _,_,_,B,scenarios=STAGES[args.stage]
    local=ROOT/".local"/"simulation"
    output=ROOT/"results"/"simulation";output.mkdir(parents=True,exist_ok=True)
    # Later stages depend on engineering completion, not favourable rejection rates.
    if args.stage!="S0":
        previous="S0" if args.stage=="S1" else "S1"
        state=json.loads((output/(previous+"_status.json")).read_text())
        if state["status"]!="complete":
            raise RuntimeError("Prior simulation stage not complete")
    results=[];total=B*len(scenarios)
    status=dict(stage=args.stage,status="running",completed=0,planned=total,
                repeats_per_scenario=B,workers=args.workers)
    def save():
        status["completed"]=len(results);status["updated_at"]=datetime.now(timezone.utc).isoformat()
        tmp=output/(args.stage+"_status.tmp")
        tmp.write_text(json.dumps(status,indent=2));tmp.replace(output/(args.stage+"_status.json"))
        if results:
            summarize(pd.concat(results,ignore_index=True)).to_csv(output/(args.stage+"_summary.csv"),index=False)
    save()
    try:
        tasks=[(args.stage,s,b,str(local)) for s in scenarios for b in range(B)]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(run_repetition,t) for t in tasks]
            for f in as_completed(futures):
                results.append(f.result())
                if len(results)%16==0 or len(results)==total:
                    save();print(f"{args.stage}: {len(results)}/{total}",flush=True)
        status["status"]="complete";save()
    except BaseException as exc:
        status["status"]="interrupted_or_error";status["error"]=type(exc).__name__+": "+str(exc)
        save();raise


if __name__=="__main__":
    main()
