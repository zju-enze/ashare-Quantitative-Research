"""Run/resume only the supplementary V1-R/V2-R paired experiments."""
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import platform
import shutil
from time import perf_counter
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import scipy
import statsmodels
from src.simulation_dh import write_json
from src.revision_pair import (METHODS, SCENARIOS, initialize, run_batch,
    checkpoint_path, validate_checkpoint, summarize, paired_comparisons)

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'.local/revision_pair'
OUTPUT=ROOT/'results_revision/pair_comparison'
SOURCE_FILES=('run_pair_comparison.py','src/revision_pair.py','src/dgp_calibration.py',
              'src/engine.py','src/engine_dh.py','src/engine_dh_market.py',
              'src/simulation_dh.py','src/simulation.py',
              'results_review/dgp_fixed_nu_2021_2025/dgp_spec.json')


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def prepare():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(version='V1R-V2R-pair-supplement-1',master_seed=20261021,n_obs=1212,
        dgp_version='empirical-pair-dgp-1',stock_ADF_precheck=False,
        methods=list(METHODS),scenarios={name:dict(cointegrated=name.endswith('COINT'),
                                                heavy_tail=name.startswith('HEAVY'))
                                      for name in SCENARIOS},
        phases={'engineering':{'repetitions_per_scenario':5,'batch_size':5,'seed_stream':20},
                'formal':{'repetitions_per_scenario':5000,'batch_size':100,'seed_stream':21}},
        primary_alpha=.05,auxiliary_alpha=.01,
        intervals='pointwise two-sided 95% Clopper-Pearson',
        paired_mcse='sample SD of paired rejection-indicator differences / sqrt(B)',
        formal_reuses_engineering_statistics=False,legacy_rows_in_new_denominators=0)
    saved=OUTPUT/'experiment_protocol.json'
    if saved.exists():
        if json.loads(saved.read_text(encoding='utf-8'))!=protocol:
            raise RuntimeError('Protocol differs; preserve existing run')
    else:
        write_json(saved,protocol)
    for name in SOURCE_FILES:
        source,snapshot=ROOT/name,PRIVATE/'source'/name
        if snapshot.exists():
            if source.read_bytes()!=snapshot.read_bytes():
                raise RuntimeError(f'Frozen supplementary source differs: {name}')
        else:
            snapshot.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,snapshot)
    environment=dict(python=platform.python_version(),numpy=np.__version__,
        scipy=scipy.__version__,pandas=pd.__version__,statsmodels=statsmodels.__version__,
        blas_threads=1)
    saved=OUTPUT/'environment.json'
    if saved.exists() and json.loads(saved.read_text())!=environment:
        raise RuntimeError('Runtime differs; do not mix supplementary checkpoints')
    if not saved.exists():
        write_json(saved,environment)
    spec=json.loads((PRIVATE/'source'/SOURCE_FILES[-1]).read_text(encoding='utf-8'))
    return protocol,spec


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['engineering','formal'],required=True)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--summarize-only',action='store_true')
    args=parser.parse_args()
    if args.workers<1:
        raise ValueError('workers must be positive')
    protocol,spec=prepare()
    if args.phase=='formal':
        evidence=OUTPUT/'engineering_validation.json'
        if not evidence.exists() or json.loads(evidence.read_text())['status']!='passed':
            raise RuntimeError('Engineering validation is required before formal execution')
    phase=protocol['phases'][args.phase]
    total,batch=phase['repetitions_per_scenario'],phase['batch_size']
    tasks=[(name,start,min(start+batch,total)) for start in range(0,total,batch)
           for name in SCENARIOS]
    folder=PRIVATE/args.phase
    folder.mkdir(parents=True,exist_ok=True)
    pending=[];reused_paths=0
    for task in tasks:
        path=checkpoint_path(folder,task)
        if path.exists():
            validate_checkpoint(path,task,protocol,args.phase)
            reused_paths+=task[2]-task[1]
        else:
            pending.append(task)
    status_path=OUTPUT/f'{args.phase}_status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {'invocations':[]}
    invocation=dict(started_at=now(),workers=args.workers,reused_paths=reused_paths,
                    new_paths=0,summarize_only=args.summarize_only)
    status['invocations'].append(invocation)
    status.update(phase=args.phase,status='running',planned_paths=4*total,
                  planned_test_calls=16*total,completed_paths=reused_paths,
                  completed_test_calls=4*reused_paths)
    write_json(status_path,status)
    start=perf_counter()
    if pending and not args.summarize_only:
        with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,
                                 initargs=(spec,protocol,str(folder),args.phase)) as pool:
            futures={pool.submit(run_batch,task):task for task in pending}
            for future in as_completed(futures):
                result=future.result()
                invocation['new_paths']+=result['paths']
                status['completed_paths']+=result['paths']
                status['completed_test_calls']=4*status['completed_paths']
                status['elapsed_seconds']=perf_counter()-start
                write_json(status_path,status)
                print(f"{args.phase}: {status['completed_paths']}/{4*total} paths; "
                      f"{status['elapsed_seconds']:.1f}s",flush=True)
    frames=[]
    for task in tasks:
        path=checkpoint_path(folder,task)
        if path.exists():
            frames.append(validate_checkpoint(path,task,protocol,args.phase))
    if frames:
        data=pd.concat(frames,ignore_index=True)
        summarize(data).to_csv(OUTPUT/f'{args.phase}_summary.csv',index=False)
        paired_comparisons(data).to_csv(OUTPUT/f'{args.phase}_paired.csv',index=False)
    invocation.update(completed_at=now(),elapsed_seconds=perf_counter()-start)
    status.update(status='complete' if len(frames)==len(tasks) else 'incomplete',
                  completed_paths=sum(len(frame)//4 for frame in frames),
                  completed_test_calls=sum(len(frame) for frame in frames),
                  completed_at=now())
    write_json(status_path,status)
    print(json.dumps(status),flush=True)


if __name__=='__main__':
    main()
