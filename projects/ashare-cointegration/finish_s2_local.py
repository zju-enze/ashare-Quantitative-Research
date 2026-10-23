"""Finish S2 locally after the existing batch, retaining the authorized cutoff."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import subprocess
import pandas as pd
from run_s2_shard import run_shard
from src.simulation import STAGES,summarize

ROOT=Path(__file__).resolve().parent


def summarize_checkpoints(root,partial_status):
    _,_,_,repeats,scenarios=STAGES['S2']
    expected={(s,r) for s in scenarios for r in range(repeats)}
    frames=[];keys=set()
    for path in sorted((root/'.local/simulation/S2').glob('*/*.parquet')):
        if path.name.endswith('.pairs.parquet'):continue
        key=(path.parent.name,int(path.stem))
        assert key in expected and key not in keys
        frame=pd.read_parquet(path)
        assert set(frame.stage)=={'S2'} and set(frame.scenario)=={key[0]} and set(frame.repetition)=={key[1]}
        assert not frame.duplicated(['domain','family','method']).any()
        frames.append(frame);keys.add(key)
    summary=summarize(pd.concat(frames,ignore_index=True))
    complete=keys==expected
    if complete:assert len(summary)==156 and summary.B.eq(500).all()
    out=root/'results/simulation';tmp=out/'S2_summary.tmp.csv'
    summary.to_csv(tmp,index=False);tmp.replace(out/'S2_summary.csv')
    state=dict(stage='S2',status='complete' if complete else partial_status,completed=len(keys),planned=2000,
        workers=32,execution_target='local',engineering_change='ENG-008',
        updated_at=datetime.now(timezone.utc).isoformat(),local_stop_at='2026-10-19T17:45:00+08:00')
    if not complete and partial_status=='held_by_user':state['hold_reason']='Local computing window ended; explicit authorization required to resume.'
    tmp=out/'S2_status.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(out/'S2_status.json')
    return state


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wait-pid',type=int);args=parser.parse_args()
    path=ROOT/'results/simulation/S2_local_takeover_status.json'
    def save(status,**fields):
        state=dict(status=status,engineering_change='ENG-008',updated_at=datetime.now(timezone.utc).isoformat(),**fields)
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(path)
    try:
        if args.wait_pid:
            save('waiting_for_existing_local_batch',batch_pid=args.wait_pid)
            subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
                f'Wait-Process -Id {args.wait_pid} -ErrorAction SilentlyContinue'],check=True)
        save('finishing_all_missing_locally')
        manifest=json.loads((ROOT/'results/simulation/S2_local_20261019.json').read_text())
        run_shard(ROOT,manifest,'local')
        save('summarizing_local_results')
        final=summarize_checkpoints(ROOT,'held_by_user')
        save(final['status'],completed=final['completed'],planned=2000)
        path_status=ROOT/'RESEARCH_STATUS.json';record=json.loads(path_status.read_text(encoding='utf8'))
        record['recorded_at']=final['updated_at']
        record['stage1_calibration'].update(S2=final,snapshot_at=final['updated_at'],
            status='S1_S2_complete_diagnostics_refresh_pending' if final['status']=='complete' else 'S2_local_held_at_deadline',
            remaining=['Refresh final calibration diagnostics and scientific report'] if final['status']=='complete' else ['Resume missing S2 repetitions only after renewed authorization'])
        path_status.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        doc=ROOT/'ENGINEERING_CHANGES.md';text=doc.read_text(encoding='utf8')
        text=re.sub(r'^\|S2\|.*$',f"|S2|本机统一计算与汇总；远端保持停止|{final['completed']}/2,000，{final['status']}|",text,count=1,flags=re.MULTILINE)
        text+=f"\n### ENG-008 自动结束记录\n\n时间：{final['updated_at']}；本机S2状态{final['status']}，完成{final['completed']}/2,000。汇总位于results/simulation/S2_summary.csv；远端未恢复。\n"
        doc.write_text(text,encoding='utf8')
        readme=ROOT/'README.md';text=readme.read_text(encoding='utf8')
        text=text.replace('ENG-008 local execution: running.',f"ENG-008 local execution: {final['status']} ({final['completed']}/2,000).")
        readme.write_text(text,encoding='utf8')
    except BaseException as exc:
        save('error',error=f'{type(exc).__name__}: {exc}');raise


if __name__=='__main__':main()
