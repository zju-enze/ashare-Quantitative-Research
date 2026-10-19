"""Run the explicitly assigned S2 repetitions, optionally until a local cutoff."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from datetime import datetime, timezone
import json
from multiprocessing import Pool, TimeoutError
from pathlib import Path
from src.simulation import STAGES, run_repetition

ROOT = Path(__file__).resolve().parent


def assignments(manifest):
    _, _, _, repeats, scenarios = STAGES['S2']
    expected = {(s, r) for s in scenarios for r in range(repeats)}
    groups = {}
    for role in ('local', 'remote', 'preserved'):
        ranges = manifest[role]
        assert set(ranges) <= set(scenarios), role
        assert all(0 <= start <= end <= repeats for start, end in ranges.values())
        groups[role] = {(s, r) for s, (start, end) in ranges.items() for r in range(start, end)}
    assert not (groups['local'] & groups['remote'] or groups['local'] & groups['preserved']
                or groups['remote'] & groups['preserved']), 'Overlapping ownership'
    assert set.union(*groups.values()) == expected, 'Incomplete S2 ownership'
    return groups


def run_shard(root, manifest, role):
    assigned = sorted(assignments(manifest)[role], key=lambda t: (t[1], t[0]))
    assert json.loads((root / 'results/simulation/S1_status.json').read_text())['status'] == 'complete'
    deadline = datetime.fromisoformat(manifest['local_stop_at']) if role == 'local' else None
    workers = manifest[role + '_workers']
    output = root / 'results/simulation' / ('S2_' + role + '_shard_status.json')
    def completed():
        return [(s, r) for s, r in assigned
                if (root / '.local/simulation/S2' / s / f'{r:04d}.parquet').exists()]
    existing = set(completed())
    tasks = [('S2', s, r, str(root / '.local/simulation')) for s, r in assigned if (s, r) not in existing]
    state = dict(stage='S2', role=role, status='running', planned=len(assigned), workers=workers,
                 stop_at=deadline.isoformat() if deadline else None, engineering_change='ENG-007')
    def save(status):
        state.update(status=status, completed=len(completed()), updated_at=datetime.now(timezone.utc).isoformat())
        tmp = output.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, indent=2)); tmp.replace(output)
    save('running')
    if deadline and datetime.now(timezone.utc) >= deadline:
        save('deadline_reached'); return
    try:
        with Pool(workers) as pool:
            pending = pool.imap_unordered(run_repetition, tasks, chunksize=1)
            remaining = len(tasks)
            while remaining:
                seconds = (deadline - datetime.now(timezone.utc)).total_seconds() if deadline else 30
                if seconds <= 0:
                    pool.terminate(); break
                try:
                    pending.next(timeout=min(seconds, 15))
                    remaining -= 1
                    if remaining % 8 == 0:
                        save('running'); print(json.dumps(state), flush=True)
                except TimeoutError:
                    save('running')
        save('complete' if not remaining else 'deadline_reached')
    except BaseException as exc:
        state['error'] = f'{type(exc).__name__}: {exc}'
        save('interrupted_or_error'); raise
    print(json.dumps(state), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--role', choices=['local', 'remote'], required=True)
    args = parser.parse_args()
    run_shard(ROOT, json.loads(args.manifest.read_text(encoding='utf8')), args.role)
