"""Run/resume one predeclared C2 or C3 stage; F0/C1 snapshots remain immutable."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
from time import perf_counter

import pandas as pd

import run_calibration_v2 as c1
from src.calibration_scale_dh import (initialize, load_checkpoint, run_repetition,
    stage_acceptance, summarize, task_keys, validate_protocol, write_json)

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (*c1.SOURCE_FILES, "run_scale_calibration_v2.py", "src/calibration_scale_dh.py")
GEOMETRY_FILES = ("U.parquet", "H.parquet", "freeze.json")


def require_previous(root, stage):
    previous = "C1" if stage == "C2" else "C2"
    folder = root/"results_v2/simulation"
    state = json.loads((folder/f"{previous}_status.json").read_text(encoding="utf-8"))
    check = json.loads((folder/f"{previous}_validation.json").read_text(encoding="utf-8"))
    if (state["status"] != "complete"
            or state[f"{previous}_acceptance"] not in ("strict_pass", "tolerated_pass")
            or check["status"] != "passed_engineering_and_summary_reconciliation"
            or check["statistical_acceptance"] != state[f"{previous}_acceptance"]):
        raise RuntimeError(f"{previous} is not complete, independently checked and passing")


def prepare_run(root, stage, protocol):
    validate_protocol(protocol, stage)
    c1.verify_snapshot(root, root/".local/dh_v2/simulation/C1")
    frozen = json.loads((root/"results_v2/F0_FREEZE.json").read_text(encoding="utf-8"))
    if frozen["method_freeze_at"] != protocol["method_freeze_at"]:
        raise RuntimeError("F0 ledger and protocol differ")
    folder = root/".local/dh_v2/simulation"/stage
    keys = task_keys(protocol, stage)
    manifest = dict(stage=stage, planned=len(keys), tasks=[dict(scenario=s, repetition=r) for s, r in keys])
    market = root/".local/production"/protocol["market"]["input_run_id"]
    if (folder/"execution.json").exists():
        for name in SOURCE_FILES:
            if (root/name).read_bytes() != (folder/"source"/name).read_bytes():
                raise RuntimeError(f"{stage} source differs: {name}; preserve existing results")
        if json.loads((folder/"environment.json").read_text(encoding="utf-8")) != c1.environment():
            raise RuntimeError(f"{stage} runtime differs")
        if json.loads((folder/"tasks.json").read_text(encoding="utf-8")) != manifest:
            raise RuntimeError(f"{stage} task manifest differs")
        if stage == "C3":
            for name in GEOMETRY_FILES:
                if (market/name).read_bytes() != (folder/"geometry"/name).read_bytes():
                    raise RuntimeError(f"Frozen C3 membership/calendar differs: {name}")
    else:
        if any(folder.glob("*/*.json")) or any(folder.glob("*/*.pairs.parquet")):
            raise RuntimeError(f"{stage} has checkpoints without a completed execution snapshot")
        if stage == "C3":
            c1.market_input_evidence(root, protocol)
            u = pd.read_parquet(market/"U.parquet")
            sizes = u.groupby("L2").size()
            if len(sizes) != 131 or sizes.max() != 121:
                raise RuntimeError("C3 membership differs from the predeclared geometry")
            (folder/"geometry").mkdir(parents=True, exist_ok=True)
            for name in GEOMETRY_FILES:
                shutil.copy2(market/name, folder/"geometry"/name)
        for name in SOURCE_FILES:
            target = folder/"source"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/name, target)
        write_json(folder/"environment.json", c1.environment())
        write_json(folder/"tasks.json", manifest)
        write_json(folder/"execution.json", dict(stage=stage, implementation_recorded_at=c1.now(),
            method_freeze_at=protocol["method_freeze_at"], engineering_change="ENG-013",
            authority="active user goal: continue the plan to full computation and results",
            statistical_specification="unchanged F0 method and predeclared stage", remote_used=False))
    return folder, keys


def collect_checkpoints(folder, stage, keys):
    records = {}
    for key in keys:
        metric = load_checkpoint(folder, stage, *key)
        if metric is not None:
            records[key] = metric
    return records


def save_outputs(output, status, records, keys, protocol, stage):
    ordered = [records[key] for key in keys if key in records]
    summary = summarize(ordered, protocol, stage)
    acceptance = stage_acceptance(summary)
    status.update(completed=len(ordered), updated_at=c1.now(),
                  kernel_calls=sum(x["kernel_calls"] for x in ordered))
    status[f"{stage}_acceptance"] = acceptance
    stages = [acceptance]
    for previous in (("C1",) if stage == "C2" else ("C1", "C2")):
        previous_state = json.loads((output/f"{previous}_status.json").read_text(encoding="utf-8"))
        stages.append(previous_state[f"{previous}_acceptance"])
    status["overall_protocol_acceptance"] = (
        "fail" if "fail" in stages else
        "incomplete_C3_not_run" if stage == "C2" else
        "incomplete" if "incomplete" in stages else
        "inconclusive" if "inconclusive" in stages else
        "strict_pass" if all(s == "strict_pass" for s in stages) else "tolerated_pass")
    for name, frame in ((f"{stage}_panels.csv", pd.DataFrame(ordered)),
                        (f"{stage}_summary.csv", summary)):
        temporary = output/(name+".tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(output/name)
    write_json(output/f"{stage}_status.json", status)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stage", choices=["C2", "C3"], required=True)
    result.add_argument("--workers", type=int, default=4)
    result.add_argument("--max-new", type=int, help="Limit one invocation, retain the full planned denominator")
    result.add_argument("--summarize-only", action="store_true")
    return result


def main():
    args = parser().parse_args()
    if args.workers < 1 or (args.max_new is not None and args.max_new < 1):
        raise ValueError("workers and max-new must be positive")
    stage, output = args.stage, ROOT/"results_v2/simulation"
    protocol = json.loads((ROOT/c1.PROTOCOL).read_text(encoding="utf-8"))
    require_previous(ROOT, stage)
    folder, keys = prepare_run(ROOT, stage, protocol)
    records = collect_checkpoints(folder, stage, keys)
    state_path = output/f"{stage}_status.json"
    status = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    invocation = dict(started_at=c1.now(), pid=os.getpid(), workers=args.workers,
                      reused_panels=len(records), max_new=args.max_new, summarize_only=args.summarize_only)
    status.setdefault("invocations", []).append(invocation)
    status.update(stage=stage, kind="formal_calibration", method_version=protocol["version"],
        method_freeze_at=protocol["method_freeze_at"], status="running", planned=len(keys),
        repeats_per_scenario=protocol["simulation"]["stages"][stage]["repeats"],
        workers=args.workers, blas_threads=1, environment=c1.environment(),
        local_checkpoints=str(folder.relative_to(ROOT)), full_market_test="not_run", remote_used=False)
    save_outputs(output, status, records, keys, protocol, stage)
    remaining = [key for key in keys if key not in records]
    selected = [] if args.summarize_only else remaining[:args.max_new]
    print(f"{stage}: reused={len(records)}/{len(keys)}, new={len(selected)}, workers={args.workers}", flush=True)
    start, pool, futures = perf_counter(), None, {}
    try:
        if selected:
            pool = ProcessPoolExecutor(max_workers=args.workers, initializer=initialize, initargs=(str(folder),))
            futures = {pool.submit(run_repetition, (stage, *key, str(folder))): key for key in selected}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    records[key] = future.result()
                except BaseException:
                    invocation["failed_task"] = dict(scenario=key[0], repetition=key[1])
                    raise
                if len(records) % (25 if stage == "C2" else 1) == 0 or len(records) == len(keys):
                    invocation["elapsed_seconds"] = perf_counter()-start
                    save_outputs(output, status, records, keys, protocol, stage)
                    print(f"{stage}: {len(records)}/{len(keys)}; this invocation {perf_counter()-start:.1f}s", flush=True)
            pool.shutdown(wait=True)
            pool = None
        status["status"] = "complete" if len(records) == len(keys) else "partial"
        invocation.update(status=status["status"], newly_completed=len(records)-invocation["reused_panels"],
                          elapsed_seconds=perf_counter()-start, completed_at=c1.now())
        status["execution_wall_seconds"] = sum(x.get("elapsed_seconds", 0.) for x in status["invocations"]
                                               if not x["summarize_only"])
        if status["status"] == "complete":
            status["completed_at"] = c1.now()
        save_outputs(output, status, records, keys, protocol, stage)
        print(json.dumps({k: status[k] for k in ("status", "completed", "kernel_calls",
                                                f"{stage}_acceptance", "execution_wall_seconds")}), flush=True)
    except BaseException as error:
        for future in futures:
            future.cancel()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        records = collect_checkpoints(folder, stage, keys)
        invocation.update(status="interrupted_or_error", error=f"{type(error).__name__}: {error}",
                          elapsed_seconds=perf_counter()-start, completed_at=c1.now())
        status["status"] = "interrupted_or_error"
        save_outputs(output, status, records, keys, protocol, stage)
        raise


if __name__ == "__main__":
    main()
