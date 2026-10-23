"""ENG-007: transfer the local shard, then finish and summarize S2 remotely."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import pandas as pd
from run_s2_shard import assignments

ROOT = Path(__file__).resolve().parent
REMOTE = '/home/qzwx2026/experiments/ashare-cointegration/repo/projects/ashare-cointegration'
MANIFEST = 'results/simulation/S2_split_20261019.json'
TRANSFER = '.local/s2-split-20261019'


def checkpoint_paths(folder, scenario, repetition):
    return folder / scenario / f'{repetition:04d}.parquet', folder / scenario / f'{repetition:04d}.pairs.parquet'


def import_checkpoints(incoming, destination, allowed):
    files = [p for p in incoming.glob('*/*.parquet') if not p.name.endswith('.pairs.parquet')]
    for path in files:
        scenario, repetition = path.parent.name, int(path.stem)
        assert (scenario, repetition) in allowed, 'Checkpoint outside local assignment'
        metrics, pairs = checkpoint_paths(incoming, scenario, repetition)
        m, p = pd.read_parquet(metrics), pd.read_parquet(pairs)
        assert len(m) == 39 and set(m.stage) == {'S2'} and set(m.scenario) == {scenario}
        assert set(m.repetition) == {repetition} and not m.duplicated(['domain','family','method']).any()
        assert len(p) == 1740 and not p.duplicated(['A','B']).any()
        target, target_pairs = checkpoint_paths(destination, scenario, repetition)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            pd.testing.assert_frame_equal(m, pd.read_parquet(target), check_exact=True)
            pd.testing.assert_frame_equal(p, pd.read_parquet(target_pairs), check_exact=True)
        else:
            shutil.copyfile(pairs, target_pairs)
            tmp = target.with_suffix('.tmp'); shutil.copyfile(metrics, tmp); tmp.replace(target)
    return len(files)


def coordinate(role):
    manifest = json.loads((ROOT / MANIFEST).read_text(encoding='utf8'))
    groups = assignments(manifest)
    transfer = ROOT / TRANSFER; transfer.mkdir(parents=True, exist_ok=True)
    status_path = ROOT / 'results/simulation' / f'S2_{role}_coordination.json'
    state = dict(role=role, engineering_change='ENG-007')
    def save(status, **fields):
        state.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(), **fields)
        tmp=status_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(status_path)
    try:
        save('computing_shard')
        subprocess.run([sys.executable,'-u',str(ROOT/'run_s2_shard.py'),'--manifest',str(ROOT/MANIFEST),'--role',role], check=True)
        if role == 'local':
            save('packing_completed_checkpoints')
            archive = transfer / 'local_completed.tar'
            completed = []
            with tarfile.open(archive,'w') as tar:
                for scenario, repetition in sorted(groups['local']):
                    metrics, pairs = checkpoint_paths(ROOT/'.local/simulation/S2',scenario,repetition)
                    if metrics.exists():
                        assert pairs.exists()
                        for path in (pairs,metrics): tar.add(path,arcname=f'{scenario}/{path.name}')
                        completed.append([scenario,repetition])
            save('uploading',completed=len(completed),archive_bytes=archive.stat().st_size)
            options=['-o','BatchMode=yes','-o','ConnectTimeout=15']
            subprocess.run(['scp',*options,str(archive),f'qzwx2026:{REMOTE}/{TRANSFER}/local_completed.tar'],check=True,timeout=180)
            marker=transfer/'local_ready.json'
            marker.write_text(json.dumps(dict(completed=completed,completed_count=len(completed),
                uploaded_at=datetime.now(timezone.utc).isoformat(),local_status=json.loads(
                    (ROOT/'results/simulation/S2_local_shard_status.json').read_text())),indent=2))
            subprocess.run(['scp',*options,str(ROOT/'results/simulation/S2_local_shard_status.json'),
                f'qzwx2026:{REMOTE}/results/simulation/S2_local_shard_status.json'],check=True,timeout=30)
            subprocess.run(['scp',*options,str(marker),f'qzwx2026:{REMOTE}/{TRANSFER}/local_ready.json'],check=True,timeout=30)
            save('uploaded_remote_will_merge',completed=len(completed))
        else:
            marker=transfer/'local_ready.json'
            save('waiting_for_local_upload')
            while not marker.exists(): time.sleep(15)
            save('importing_local_checkpoints')
            incoming=transfer/'incoming';incoming.mkdir(exist_ok=True)
            with tarfile.open(transfer/'local_completed.tar') as tar: tar.extractall(incoming,filter='data')
            imported=import_checkpoints(incoming,ROOT/'.local/simulation/S2',groups['local'])
            ready=json.loads(marker.read_text())
            assert imported==ready['completed_count']
            save('finishing_remaining_and_summarizing',imported_local=imported)
            subprocess.run([sys.executable,'-u',str(ROOT/'run_simulation.py'),'--stage','S2','--workers','2'],check=True)
            final=json.loads((ROOT/'results/simulation/S2_status.json').read_text())
            summary=pd.read_csv(ROOT/'results/simulation/S2_summary.csv')
            assert final['status']=='complete' and final['completed']==2000
            assert len(summary)==156 and summary.B.eq(500).all()
            save('complete',imported_local=imported,completed=2000,summary_rows=len(summary))
            research=ROOT/'RESEARCH_STATUS.json';record=json.loads(research.read_text(encoding='utf8'))
            record['stage1_calibration'].update(status='S1_S2_complete_diagnostics_refresh_pending',S2=final,
                snapshot_at=state['updated_at'],remaining=['Refresh final calibration diagnostics and scientific report'])
            record['remote_execution_plan']['status']='S2_complete'
            research.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            with (ROOT/'ENGINEERING_CHANGES.md').open('a',encoding='utf8') as log:
                log.write(f"\n### ENG-007 自动汇总完成记录\n\n时间：{state['updated_at']}；导入本机{imported}份正式检查点，远端S2合并完成2,000/2,000，汇总156行且每组B=500。结果位于results/simulation/S2_summary.csv。第二、第三研究阶段未启动。\n")
    except BaseException as exc:
        save('error',error=f'{type(exc).__name__}: {exc}')
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--role',choices=['local','remote'],required=True)
    coordinate(parser.parse_args().role)
