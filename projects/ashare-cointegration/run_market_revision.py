"""Run the revised log-price EG/DH specifications on the frozen market candidates."""
import os
for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

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
import pyarrow
import scipy
import statsmodels
from statsmodels.stats.multitest import multipletests

from src.engine import applicability, VALID
from src.revision_pair import METHODS, run_methods
from src.simulation_dh import write_json

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / ".local/production/formation-2021-2025-v2"
RUN = ROOT / ".local/revision_market/formation-2021-2025-log-20261023"
OUTPUT = ROOT / "results_revision/market_20261023"
SOURCE_FILES = ("run_market_revision.py", "src/revision_pair.py", "src/engine.py",
                "src/engine_dh.py", "src/engine_dh_market.py", "src/simulation_dh.py")
INPUT_FILES = ("prices.npy", "U.parquet", "H.parquet", "catalogue.parquet", "freeze.json")
VALUES = CODES = FOLDER = None
EVIDENCE_SCOPE = "nominal_discoveries_full_family_calibration_not_completed"


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def initialize(folder):
    global VALUES, CODES, FOLDER
    FOLDER = Path(folder)
    VALUES = np.load(FOLDER / "log_prices.npy", mmap_mode="r")
    universe = pd.read_parquet(FOLDER / "U.parquet")
    CODES = {code: i for i, code in enumerate(universe.ts_code)}


def diagnose_stock(code):
    return code, applicability(VALUES[:, CODES[code]])


def batch_path(folder, batch_id):
    return Path(folder) / "batches" / f"{batch_id:04d}.parquet"


def check_batch(frame, candidates):
    expected = {(row["candidate_id"], method) for row in candidates for method in METHODS}
    if len(frame) != len(expected) or set(zip(frame.candidate_id, frame.method)) != expected:
        raise ValueError("Incomplete or duplicate market checkpoint")
    if not frame.p.between(0, 1).all():
        raise ValueError("Invalid checkpoint p values")
    metadata = {row["candidate_id"]: row for row in candidates}
    for key in ("A", "B", "L2", "M_L2", "M_GLOBAL"):
        expected_values = frame.candidate_id.map(lambda cid: metadata[cid][key])
        if not frame[key].eq(expected_values).all():
            raise ValueError(f"Checkpoint candidate metadata differs: {key}")


def work_batch(task):
    batch_id, candidates = task
    path = batch_path(FOLDER, batch_id)
    if path.exists():
        check_batch(pd.read_parquet(path), candidates)
        return {"batch": batch_id, "pairs": len(candidates), "reused": True}
    rows = []
    for candidate in candidates:
        values = np.column_stack((VALUES[:, CODES[candidate["A"]]],
                                  VALUES[:, CODES[candidate["B"]]]))
        values.setflags(write=False)
        # The descriptive log-price relation is saved, never used as a selection filter.
        design = np.column_stack((values[:, 1], np.ones(len(values))))
        beta, intercept = np.linalg.lstsq(design, values[:, 0], rcond=None)[0]
        for result in run_methods(values):
            rows.append(dict(candidate, **result, log_ols_intercept=float(intercept),
                             log_ols_beta=float(beta)))
    frame = pd.DataFrame(rows)
    check_batch(frame, candidates)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)
    return {"batch": batch_id, "pairs": len(candidates), "reused": False}


def correct_methods(frame, registry):
    result = []
    expected_ids = set(registry.candidate_id)
    if registry.candidate_id.duplicated().any():
        raise ValueError("Duplicate frozen candidate")
    for method in METHODS:
        table = frame.loc[frame.method.eq(method)].copy().reset_index(drop=True)
        if len(table) != len(registry) or set(table.candidate_id) != expected_ids:
            raise ValueError(f"Incomplete method coverage: {method}")
        if not table.M_GLOBAL.eq(len(registry)).all():
            raise ValueError("GLOBAL family size changed")
        if not table.status.isin([*VALID, "numerically_ineligible"]).all():
            raise ValueError("Unexplained numerical status")
        unavailable = ~table.status.isin(VALID)
        if not table.loc[unavailable, "p"].eq(1.).all():
            raise ValueError("Numerical placeholders must retain p=1")
        if not np.isfinite(table.p.to_numpy(float)).all() or not table.p.between(0, 1).all():
            raise ValueError("Invalid correction input")
        for domain, groups in (
            ("GLOBAL", [("GLOBAL", table.index)]),
            ("L2", table.groupby("L2", sort=True).groups.items()),
        ):
            table[f"p_{domain}_Holm"] = np.nan
            table[f"reject_{domain}_Holm"] = False
            for _, indices in groups:
                if not table.loc[indices, f"M_{domain}"].eq(len(indices)).all():
                    raise ValueError(f"Incomplete {domain} family")
                reject, adjusted, _, _ = multipletests(
                    table.loc[indices, "p"].to_numpy(float), .05, method="holm")
                table.loc[indices, f"p_{domain}_Holm"] = adjusted
                table.loc[indices, f"reject_{domain}_Holm"] = reject
        result.append(table)
    return pd.concat(result, ignore_index=True)


def prepare():
    universe = pd.read_parquet(INPUT / "U.parquet")
    registry = pd.read_parquet(INPUT / "H.parquet")
    prices = np.load(INPUT / "prices.npy", mmap_mode="r")
    freeze = json.loads((INPUT / "freeze.json").read_text(encoding="utf-8"))
    if (len(universe), len(registry), prices.shape) != (2984, 67678, (1212, 2984)):
        raise ValueError("Frozen market scope differs from the authorized design")
    if not universe.ts_code.is_unique or registry.candidate_id.duplicated().any():
        raise ValueError("Duplicate frozen security or candidate")
    if (not np.isfinite(prices).all() or np.any(prices <= 0)
            or len(freeze["calendar"]) != len(prices)):
        raise ValueError("Finite positive aligned prices are required for log conversion")
    if not (set(registry.A) | set(registry.B)) <= set(universe.ts_code):
        raise ValueError("Candidate stock is absent from the frozen price matrix")
    protocol = dict(
        version="V1-V2-log-market-20261023-1", input_run_id=INPUT.name,
        formation=freeze["formation"], price_observations=1212,
        stocks=2984, candidates=67678, price_input="natural_log_of_frozen_adjusted_prices",
        direction="frozen_A_on_B", methods=list(METHODS),
        primary_methods=["EG-fixed-1", "DH-fixed-1"],
        sensitivity_methods=["EG-AIC", "DH-fixed-7"],
        stock_ADF_entry_gate=False,
        applicability_diagnostics="ADF on each log price and its difference, diagnostic only",
        correction=dict(method="Holm", alpha=.05, domains=["L2", "GLOBAL"],
                        same_domains_for_every_method=True, selected_primary_domain=None,
                        unavailable_p=1, full_families_retained=True),
        evidence_scope=EVIDENCE_SCOPE, calibration_completed=False,
        no_beta_half_life_or_future_return_filter=True, batch_pairs=1000,
        independent_reference_candidate_positions=[0, 9668, 19336, 29004, 38672, 48340, 58008, 67677])
    environment = dict(python=platform.python_version(), numpy=np.__version__,
                       pandas=pd.__version__, scipy=scipy.__version__,
                       statsmodels=statsmodels.__version__, pyarrow=pyarrow.__version__, blas_threads=1)
    RUN.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path, value in ((RUN / "protocol.json", protocol), (RUN / "environment.json", environment)):
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
            raise RuntimeError(f"Frozen market configuration differs: {path.name}")
        if not path.exists():
            write_json(path, value)
    for parent, names, destination in (
        (INPUT, INPUT_FILES, RUN),
        (ROOT, SOURCE_FILES, RUN / "source"),
    ):
        for name in names:
            src, dst = parent / name, destination / name
            if dst.exists():
                if src.read_bytes() != dst.read_bytes():
                    raise RuntimeError(f"Frozen market source/input differs: {name}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    log_prices = np.log(prices)
    if (RUN / "log_prices.npy").exists():
        if not np.array_equal(np.load(RUN / "log_prices.npy"), log_prices):
            raise RuntimeError("Saved log input differs")
    else:
        np.save(RUN / "log_prices.npy", log_prices)
    for name in ("protocol.json", "environment.json"):
        shutil.copy2(RUN / name, OUTPUT / name)
    return universe, registry, protocol


def summarize(full, diagnostics, state):
    catalogue = pd.read_parquet(RUN / "catalogue.parquet")
    l2_catalogue = catalogue.loc[catalogue.level.eq("L2")].set_index("industry_code")
    full["L2_name"] = full.L2.map(l2_catalogue.L2_name)
    full["I1_A_diagnostic"] = full.A.map(lambda code: diagnostics[code]["status"])
    full["I1_B_diagnostic"] = full.B.map(lambda code: diagnostics[code]["status"])
    full["both_I1_compatible_diagnostic"] = (
        full.A.map(lambda code: diagnostics[code]["compatible"])
        & full.B.map(lambda code: diagnostics[code]["compatible"]))
    full["evidence_scope"] = EVIDENCE_SCOPE
    full.to_parquet(RUN / "full_results.parquet", index=False)
    summary, families, overlaps = [], [], []
    columns = ["candidate_id", "A", "B", "name_A", "name_B", "L2", "L2_name", "L3_A", "L3_B",
               "layer", "method", "statistic", "p_raw", "p", "log_p", "status",
               "used_lag", "n_effective", "p_L2_Holm", "p_GLOBAL_Holm",
               "reject_L2_Holm", "reject_GLOBAL_Holm", "M_L2", "M_GLOBAL",
               "log_ols_intercept", "log_ols_beta", "I1_A_diagnostic", "I1_B_diagnostic",
               "both_I1_compatible_diagnostic", "p_zero_origin", "evidence_scope"]
    for method in METHODS:
        group = full.loc[full.method.eq(method)]
        summary.append(dict(
            method=method, candidates=len(group), effective=int(group.status.isin(VALID).sum()),
            numerical_unavailable=int((~group.status.isin(VALID)).sum()),
            zero_p=int(group.p.eq(0).sum()), raw_p_below_005=int(group.p.lt(.05).sum()),
            L2_Holm=int(group.reject_L2_Holm.sum()), GLOBAL_Holm=int(group.reject_GLOBAL_Holm.sum()),
            min_raw_p=float(group.p.min()), kernel_wall_seconds=float(group.seconds.sum()),
            kernel_cpu_seconds=float(group.cpu_seconds.sum())))
        for domain in ("L2", "GLOBAL"):
            discoveries = group.loc[group[f"reject_{domain}_Holm"]].sort_values("candidate_id")
            discoveries[columns].to_csv(OUTPUT / f"{method}_{domain}_Holm.csv",
                                       index=False, encoding="utf-8-sig")
            parts = dict(tuple(group.groupby("L2", sort=True)))
            grouped = ([("GLOBAL", group)] if domain == "GLOBAL" else
                       [(family, parts.get(family, group.iloc[:0])) for family in l2_catalogue.index])
            for family, part in grouped:
                families.append(dict(method=method, domain=domain, family=family,
                                     candidates=len(part), effective=int(part.status.isin(VALID).sum()),
                                     discoveries=int(part[f"reject_{domain}_Holm"].sum()),
                                     state="tested" if len(part) else "empty_family"))
    for domain in ("L2", "GLOBAL"):
        flag = f"reject_{domain}_Holm"
        a = set(full.loc[full.method.eq("EG-fixed-1") & full[flag], "candidate_id"])
        b = set(full.loc[full.method.eq("DH-fixed-1") & full[flag], "candidate_id"])
        overlaps.append(dict(domain=domain, EG=len(a), DH=len(b), intersection=len(a & b),
                             EG_only=len(a-b), DH_only=len(b-a), union=len(a | b)))
        comparison = full.pivot(index="candidate_id", columns="method", values=flag)
        comparison.reset_index().to_csv(OUTPUT / f"method_comparison_{domain}.csv", index=False)
    pd.DataFrame(summary).to_csv(OUTPUT / "summary.csv", index=False)
    pd.DataFrame(families).to_csv(OUTPUT / "families.csv", index=False)
    pd.DataFrame(overlaps).to_csv(OUTPUT / "overlap.csv", index=False)
    diagnostic_summary = dict(
        stocks=len(diagnostics), compatible=sum(d["compatible"] for d in diagnostics.values()),
        role="diagnostic_only_not_a_filter",
        candidate_pairs_both_compatible=int(full.loc[full.method.eq(METHODS[0]),
                                                   "both_I1_compatible_diagnostic"].sum()))
    write_json(OUTPUT / "applicability_summary.json", diagnostic_summary)
    completion = dict(
        status="computation_complete_validation_pending", completed_at=now(),
        candidates=67678, methods=len(METHODS), test_calls=len(full),
        new_stock_ADF_diagnostics=len(diagnostics), stock_ADF_entry_gate=False,
        evidence_scope=EVIDENCE_SCOPE, full_family_calibration_completed=False,
        summary=summary, overlaps=overlaps, applicability=diagnostic_summary,
        execution=state, independent_validation="pending")
    write_json(OUTPUT / "COMPLETION.json", completion)
    lines = ["# V1 / V2修订设计全市场结果", "", f"完成时间：{completion['completed_at']}。",
             "", "本次使用2021—2025年冻结对数复权价格，遍历2,984股的67,678个同业候选对。",
             "四个规格全部执行，无逐股ADF入场门槛；各L2内与全部候选Holm校正并列报告，名义水平5%。",
             "结果属于名义发现，完整共享股票图的错误控制校准仍未完成。", "",
             "|方法|候选数|有效|数值不可用|原始p<0.05|L2-Holm|GLOBAL-Holm|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        lines.append(f"|{row['method']}|{row['candidates']}|{row['effective']}|"
                     f"{row['numerical_unavailable']}|{row['raw_p_below_005']}|"
                     f"{row['L2_Holm']}|{row['GLOBAL_Holm']}|")
    lines += ["", "原始p<0.05仅作诊断，不能当成经过多重校正的发现。L2各家族发现的并集不等于全市场5%错误控制。",
              "", "## 股票对证据清单", ""]
    for method in METHODS:
        lines.append(f"- {method}：[L2内Holm]({method}_L2_Holm.csv) · "
                     f"[全局Holm]({method}_GLOBAL_Holm.csv)")
    lines += ["", "## 可追溯结果", "",
              "- [统计汇总](summary.csv)、[各家族汇总](families.csv)、[两主方法重合](overlap.csv)。",
              "- [运行协议](protocol.json)、[环境](environment.json)、[完成记录](COMPLETION.json)。",
              "- [逐股适用性诊断汇总](applicability_summary.json)：仅作诊断，不筛除候选。",
              "", "完整逐对表及检查点留在本机私有运行目录。未使用2026价格、收益、beta符号或半衰期筛选。",
              "独立核对结果另见validation.json。本报告不将名义发现写作已验证真实协整或可交易关系。"]
    (OUTPUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    started = perf_counter()
    universe, registry, protocol = prepare()
    records = registry.to_dict("records")
    tasks = [(i//1000, records[i:i+1000]) for i in range(0, len(records), 1000)]
    previous = json.loads((OUTPUT / "status.json").read_text(encoding="utf-8")) if (OUTPUT / "status.json").exists() else {}
    state = dict(status="running", started_at=now(), workers=args.workers, blas_threads=1,
                 candidates=len(registry), planned_test_calls=len(registry)*len(METHODS),
                 completed_pairs=0, reused_pairs=0, invocations=previous.get("invocations", []))
    write_json(OUTPUT / "status.json", state)
    try:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize, initargs=(str(RUN),)) as pool:
            diagnostic_start = perf_counter()
            diagnostic_path = RUN / "stock_ADF_diagnostics.json"
            if diagnostic_path.exists():
                diagnostics = json.loads(diagnostic_path.read_text(encoding="utf-8"))
                if set(diagnostics) != set(universe.ts_code):
                    raise ValueError("Incomplete saved stock diagnostics")
            else:
                diagnostics = dict(pool.map(diagnose_stock, universe.ts_code.tolist(), chunksize=16))
                write_json(diagnostic_path, diagnostics)
            state["diagnostic_elapsed_seconds"] = perf_counter()-diagnostic_start
            print(f"Stock diagnostics complete: {len(diagnostics)} (not used as a gate)", flush=True)
            pair_start = perf_counter()
            futures = [pool.submit(work_batch, task) for task in tasks]
            for future in as_completed(futures):
                result = future.result()
                state["completed_pairs"] += result["pairs"]
                state["reused_pairs"] += result["pairs"] if result["reused"] else 0
                state["updated_at"] = now()
                write_json(OUTPUT / "status.json", state)
                print(f"Pairs {state['completed_pairs']}/{len(registry)}; four specifications", flush=True)
            state["pair_stage_wall_seconds"] = perf_counter()-pair_start
        frames = []
        for batch_id, candidates in tasks:
            frame = pd.read_parquet(batch_path(RUN, batch_id))
            check_batch(frame, candidates)
            frames.append(frame)
        full = correct_methods(pd.concat(frames, ignore_index=True), registry)
        state.update(status="complete", completed_at=now(),
                     completed_test_calls=len(full), elapsed_seconds=perf_counter()-started)
        state["invocations"].append({k:v for k,v in state.items() if k != "invocations"})
        summarize(full, diagnostics, state)
        state["elapsed_seconds"] = perf_counter()-started
        state["invocations"][-1]["elapsed_seconds"] = state["elapsed_seconds"]
        write_json(OUTPUT / "status.json", state)
        completion = json.loads((OUTPUT / "COMPLETION.json").read_text(encoding="utf-8"))
        completion["execution"] = state
        write_json(OUTPUT / "COMPLETION.json", completion)
        print(json.dumps(dict(status=state["status"], pairs=len(registry), tests=len(full),
                              elapsed_seconds=state["elapsed_seconds"]), ensure_ascii=False), flush=True)
    except BaseException:
        state.update(status="interrupted_or_failed", stopped_at=now())
        write_json(OUTPUT / "status.json", state)
        raise


if __name__ == "__main__":
    main()
