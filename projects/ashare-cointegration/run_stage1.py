"""Freeze the complete input and families, then resume fixed-specification inference."""
import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key]="1"
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ProcessPoolExecutor
import argparse
import json
import shutil
import subprocess
import numpy as np
import pandas as pd
import statsmodels
from src.data import initial_universe,ORDINARY_CODE_PATTERN
from src.engine import applicability,candidates,correct,test_pair,VALID,METHODS
from src.reporting import charts

ROOT=Path(__file__).resolve().parent
VALUES=None
GATES=None
CODES=None
EXCLUSION_ORDER=["instrument_or_uncovered_market","identity","listing_history","end_2025_survival_or_unknown",
                 "end_2025_ST_or_unknown","classification","raw_data_and_continuity","adjustment"]


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path,value):
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf8")
    temporary.replace(path)


def initialize(run):
    global VALUES,GATES,CODES
    run=Path(run)
    VALUES=np.load(run/"prices.npy",mmap_mode="r")
    CODES={c:i for i,c in enumerate(pd.read_parquet(run/"U.parquet").ts_code)}
    GATES=json.loads((run/"ADF.json").read_text()) if (run/"ADF.json").exists() else None


def diagnose_stock(code):
    return code,applicability(VALUES[:,CODES[code]])


def diagnose_pair(row):
    return test_pair((row,VALUES[:,CODES[row["A"]]],VALUES[:,CODES[row["B"]]],
                      GATES[row["A"]],GATES[row["B"]]))


def freeze(run):
    run.mkdir(parents=True,exist_ok=True)
    if (run/"freeze.json").exists():
        # Frozen inputs and the statistical kernel determine reusable batch results.
        for p in [ROOT/"experiment_protocol.json",ROOT/"src"/"engine.py"]:
            if p.read_bytes()!=(run/"source"/p.name).read_bytes():
                raise RuntimeError("Frozen code/protocol differs: start a new run ID after documenting correction")
        return
    acquisition=json.loads((ROOT/"results"/"acquisition_status.json").read_text())
    if acquisition["status"]!="complete" or acquisition["errors"]:
        raise RuntimeError("Market acquisition has unresolved tasks")
    basic,catalogue,calendar=initial_universe(ROOT/".local"/"sources")
    all_rows=[];prices={}
    for row in basic.to_dict("records"):
        if not row["exclusion_tags"]:
            folder=ROOT/".local"/"market"/row["code"]
            info=json.loads((folder/"status.json").read_text(encoding="utf8"))
            if info["status"]!="complete":
                raise RuntimeError("Incomplete security "+row["code"])
            for name in ("raw","hfq","factors"):
                path=folder/(name+".csv")
                if path.exists() and not pd.read_csv(path,usecols=["code"],dtype=str).code.eq(row["code"]).all():
                    raise RuntimeError("Source security key mismatch: "+str(path))
            row["exclusion_tags"]+=info.pop("exclusion_tags")
            row.update(info)
            if not row["exclusion_tags"]:
                values=pd.read_parquet(folder/"adjusted.parquet")
                if values.date.tolist()!=calendar:
                    raise RuntimeError("Frozen input calendar mismatch")
                prices[row["ts_code"]]=values.adjusted_close.to_numpy()
        row["exclusion_tags"]=sorted(set(row["exclusion_tags"]),key=EXCLUSION_ORDER.index)
        row["primary_exclusion"]=row["exclusion_tags"][0] if row["exclusion_tags"] else None
        all_rows.append(row)
    audit=pd.DataFrame(all_rows)
    universe=audit.loc[audit.primary_exclusion.isna()].sort_values("ts_code").reset_index(drop=True)
    if universe.empty:
        raise RuntimeError("No audited universe; resolve source-wide issues before reporting zero discoveries")
    registry=candidates(universe)
    audit.to_parquet(run/"stock_audit.parquet",index=False)
    universe.to_parquet(run/"U.parquet",index=False)
    registry.to_parquet(run/"H.parquet",index=False)
    catalogue.to_parquet(run/"catalogue.parquet",index=False)
    np.save(run/"prices.npy",np.column_stack([prices[c] for c in universe.ts_code]))
    (run/"source").mkdir(exist_ok=True)
    for p in [ROOT/"experiment_protocol.json",ROOT/"run_stage1.py",*sorted((ROOT/"src").glob("*.py"))]:
        shutil.copy2(p,run/"source"/p.name)
    write_json(run/"freeze.json",dict(frozen_at=now(),formation=["2021-01-01","2025-12-31"],
        calendar=calendar,stocks=len(universe),candidates=len(registry),
        T=int((registry.layer=="T").sum()),C=int((registry.layer=="C").sum()),
        source_git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        input_snapshot="prices.npy + U.parquet + H.parquet; copied before ADF",
        protocol_source="source/experiment_protocol.json",code_snapshot="source/",
        calibration_status="separate; see results/simulation"))


def report(run,full,main):
    output=ROOT/"results";audit=pd.read_parquet(run/"stock_audit.parquet")
    # Index/fund codes can share six digits with stocks; their industry is not applicable.
    industry_columns=[c for c in ("L1","L2","L3","L1_name","L2_name","L3_name") if c in audit]
    audit.loc[audit.primary_exclusion.eq("instrument_or_uncovered_market"),industry_columns]=None
    audit.to_parquet(run/"stock_audit_report.parquet",index=False)
    catalogue=pd.read_parquet(run/"catalogue.parquet")
    alarms=[]
    for stage in ("S0","S1","S2"):
        path=output/"simulation"/(stage+"_summary.csv")
        if path.exists():
            summary=pd.read_csv(path)
            alarms.extend(stage+"/"+s for s in summary.loc[summary.main_alarm,"scenario"].unique())
    alarm_note=("已执行的预定机制触发固定L2-Holm FWER警报："+", ".join(alarms)+
        "。具体重复数、家族和Wilson区间见各阶段summary.csv；这是有限机制诊断，不改变主规格。"
        if alarms else "当前没有已记录的主方法校准警报；未完成校准不记为通过。")
    names=catalogue.set_index("industry_code")
    main["L2_name"]=main.L2.map(names.L2_name) if "L2_name" in names else main.L2
    for side in ("A","B"):
        main[f"L3_{side}_name"]=main[f"L3_{side}"].map(names.L3_name) if "L3_name" in names else main[f"L3_{side}"]
    counts=full.compute_status.isin(VALID).groupby(full.L2).sum()
    main["L2_valid_EG"]=main.L2.map(counts)
    main["formation_start"]="2021-01-01";main["formation_end"]="2025-12-31"
    main["calibration_warning"]=alarm_note
    main.to_csv(output/"main_evidence.csv",index=False,encoding="utf-8-sig")
    families=[]
    for domain,level,key in [("L3","L3","L3_family"),("L2","L2","L2"),("GLOBAL",None,None)]:
        ids=catalogue.loc[catalogue.level==level,"industry_code"].tolist() if level else ["GLOBAL"]
        for family in ids:
            group=full if key is None else full.loc[full[key]==family]
            valid=int(group.compute_status.isin(VALID).sum())
            pre=int((group.compute_status=="precheck_placeholder").sum())
            num=int((group.compute_status=="numerically_ineligible").sum())
            if len(group)!=valid+pre+num:raise RuntimeError("Terminal status accounting mismatch")
            for method in METHODS:
                families.append(dict(domain=domain,family=family,method=method,M_plan=len(group),
                    valid_EG=valid,precheck_placeholders=pre,numerical_placeholders=num,
                    discoveries=int(group[f"reject_{domain}_{method}"].fillna(False).sum()),
                    state="empty_family" if not len(group) else "all_placeholders" if not valid else "tested"))
    pd.DataFrame(families).to_csv(output/"families.csv",index=False)
    flows=[]
    for domain in ["GLOBAL","L2","L3"]:
        groups=[("GLOBAL",audit)] if domain=="GLOBAL" else audit.fillna({domain:"UNKNOWN"}).groupby(domain)
        for family,g in groups:
            remaining=len(g)
            for reason in EXCLUSION_ORDER:
                removed=int(g.primary_exclusion.eq(reason).sum())
                flows.append(dict(domain=domain,family=family,step=reason,entering=remaining,
                                  newly_excluded=removed,remaining=remaining-removed,
                                  all_tag_count=int(g.exclusion_tags.map(lambda t:reason in t).sum())))
                remaining-=removed
    pd.DataFrame(flows).to_csv(output/"stock_flow.csv",index=False)
    overlaps=[]
    for support,subset in [("T",full.loc[full.layer=="T"]),("H",full)]:
        views=[(d,m) for d in (["L3","L2","GLOBAL"] if support=="T" else ["L2","GLOBAL"]) for m in METHODS]
        for i,(d,m) in enumerate(views):
            a=set(subset.loc[subset[f"reject_{d}_{m}"].fillna(False),"candidate_id"])
            for e,n in views[i:]:
                b=set(subset.loc[subset[f"reject_{e}_{n}"].fillna(False),"candidate_id"])
                overlaps.append(dict(support=support,view_A=d+"_"+m,view_B=e+"_"+n,
                    size_A=len(a),size_B=len(b),intersection=len(a&b),A_only=len(a-b),B_only=len(b-a),
                    Jaccard=len(a&b)/len(a|b) if a|b else None))
    pd.DataFrame(overlaps).to_csv(output/"view_overlap.csv",index=False)
    ledger=json.loads((run/"freeze.json").read_text())
    expected=full.loc[full.compute_status.isin(VALID)&full.reject_L2_Holm.fillna(False)].copy()
    pd.testing.assert_frame_equal(main[expected.columns].reset_index(drop=True),expected.reset_index(drop=True))
    write_json(output/"production_acceptance.json",dict(status="passed",checked_at=now(),
        run=str(run.relative_to(ROOT)),stocks=ledger["stocks"],candidates=len(full),discoveries=len(main),
        full_H_covered=True,all_L2_accounted=True,main_exactly_L2_Holm=True,
        stage2="planned_deferred",stage3="planned_deferred"))
    text=f"""# 第一阶段统计报告

形成期：2021—2025；日历 {len(ledger['calendar'])} 日。
审计后股票池 U={ledger['stocks']}；候选 H={len(full)}，T={ledger['T']}，C={ledger['C']}。
主清单共 {len(main)} 对，见 main_evidence.csv，未按 beta、GLOBAL 结果或未来应用条件过滤。
其中T层 {int((main.layer=='T').sum())} 对、C层 {int((main.layer=='C').sum())} 对；
非正beta {int((main.beta<=0).sum()) if 'beta' in main else 0} 对，按同一规则保留。

H中有效名义EG {int(full.compute_status.isin(VALID).sum())} 对；
预检占位 {int((full.compute_status=='precheck_placeholder').sum())} 对；
数值占位 {int((full.compute_status=='numerically_ineligible').sum())} 对。
有限统计量尾部零 {int((full.compute_status=='tail_unresolved').sum())} 对，逐行保留来源与警示。

主结果是**各二级行业分别按名义0.05校正后的发现汇总**，不声明合并全市场FWER为5%。
在既定样本、模型规格和多重校正规则下，主表各对拒绝无协整原假设，获得协整证据。
名义校正发现，预定校准诊断尚未完成；实际模拟进度与警报见 simulation/。
**{alarm_note}**
不能把清单解释为已经实证验证的5%错误控制；未完成机制不记为通过，
也不按BH的FWER判定其FDR控制失效。已作的实现排查见simulation/中的独立记录。

完整逐对结果、冻结 U/H、逐股 ADF 与逐证券排除记录位于本地 {run.relative_to(ROOT).as_posix()}。
families.csv 保留空家族、全部占位、零发现和各校正域；stock_flow.csv 包括 UNKNOWN。
view_overlap.csv 在T共同支持上比较九视角，在H上比较六视角。

行业来自当前申万官方历史变迁记录重建，不是2025当时归档快照。价格采用BaoStock记录值的
累计后复权坐标。原生坐标先以Decimal验证 raw×factor 与直接接口逐行完全相等，再除以同一首日因子；
该零误差恒等校验不推断供应商未公开的潜在因子舍入规则，也不等于独立核实所有公司行动。
样本限于来源覆盖的沪深市场、2025年底存续且满足五年严格连续交易条件的普通A股。
北交所未覆盖；不能外推至所有A股。

EG使用statsmodels 0.15.0的价格水平、常数项、AIC、maxlag=None路径及近似渐近MacKinnon p值。
Holm理论保证以输入p值有效为前提；BH还需要相应依赖条件。多重校正不修复模型错设或尾部近似误差。
近共线强制零作为数值占位；有限统计量的尾部零保留名义值并警示。未拒绝不证明无协整。
这些关系不证明永久均衡、未来收敛或交易盈利；第二、第三阶段均planned_deferred。
"""
    (output/"STAGE1_REPORT.md").write_text(text,encoding="utf8")
    examples=charts(run,full,main,output)
    with (output/"STAGE1_REPORT.md").open("a",encoding="utf8") as handle:
        handle.write("\n## 校正视角与形成期个案图\n\n![校正发现数](figures/correction_counts.png)\n\n")
        for image in examples:
            handle.write(f"![形成期关系示例]({image.relative_to(output).as_posix()})\n\n")
        handle.write("个案图按L2与candidate_id顺序选取前三个有发现行业的首对，仅用于检查形成期拟合与残差；完整发现见CSV。\n" if examples else "无主发现，未绘制个案图。\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default="formation-2021-2025-v2")
    parser.add_argument("--workers",type=int,default=8)
    args=parser.parse_args()
    if Path(args.run_id).name!=args.run_id:raise ValueError("run-id must be one directory name")
    if statsmodels.__version__!="0.15.0":raise RuntimeError("Frozen statsmodels 0.15.0 required")
    protocol=json.loads((ROOT/"experiment_protocol.json").read_text(encoding="utf8"))
    assert protocol["formation"]==["2021-01-01","2025-12-31"],"Unsupported formation specification"
    assert protocol["universe"]["ordinary_code_pattern"]==ORDINARY_CODE_PATTERN,"Instrument scope mismatch"
    assert protocol["primary_result"]=={"domain":"L2","method":"holm","alpha":.05},"Unsupported primary rule"
    for key,value in {"trend":"c","autolag":"aic","maxlag":None,"directions_per_pair":1}.items():
        assert protocol["cointegration"][key]==value,"Protocol/EG implementation mismatch"
    for key,value in {"regression":"c","autolag":"AIC","maxlag":None,"alpha":.05}.items():
        assert protocol["unit_root_diagnostic"][key]==value,"Protocol/ADF implementation mismatch"
    run=ROOT/".local"/"production"/args.run_id
    freeze(run)
    universe=pd.read_parquet(run/"U.parquet");registry=pd.read_parquet(run/"H.parquet")
    status=dict(status="running",run_id=args.run_id,started_at=now(),candidates=len(registry),completed=0)
    write_json(ROOT/"results"/"production_status.json",status)
    try:
        if not (run/"ADF.json").exists():
            with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(run),)) as pool:
                gates=dict(pool.map(diagnose_stock,universe.ts_code,chunksize=8))
            for gate in gates.values():
                gate.update(input_version=args.run_id,statsmodels_version=statsmodels.__version__)
            write_json(run/"ADF.json",gates)
        (run/"batches").mkdir(exist_ok=True)
        with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(run),)) as pool:
            for start in range(0,len(registry),1000):
                chunk=registry.iloc[start:start+1000]
                destination=run/"batches"/f"{start:09d}.parquet"
                if not destination.exists():
                    rows=list(pool.map(diagnose_pair,chunk.to_dict("records"),chunksize=16))
                    temporary=destination.with_suffix(".tmp")
                    pd.DataFrame(rows).to_parquet(temporary,index=False);temporary.replace(destination)
                status.update(completed=min(start+1000,len(registry)),updated_at=now())
                write_json(ROOT/"results"/"production_status.json",status)
                print(f"EG {status['completed']}/{len(registry)}",flush=True)
        if len(registry):
            raw=pd.concat([pd.read_parquet(p) for p in sorted((run/"batches").glob("*.parquet"))],ignore_index=True)
        else:
            raw=registry.assign(compute_status=pd.Series(dtype=str),p_for_adjustment=pd.Series(dtype=float))
        if raw.candidate_id.tolist()!=registry.candidate_id.tolist():
            raise RuntimeError("Candidate registry coverage/order mismatch")
        raw["input_version"]=args.run_id
        raw["statsmodels_version"]=statsmodels.__version__
        raw["code_version"]=json.loads((run/"freeze.json").read_text())["source_git_commit"]
        raw["L3_applicable"]=raw.layer.eq("T")
        raw["GLOBAL_family"]="GLOBAL"
        full,main=correct(raw)
        full.to_parquet(run/"full_results.parquet",index=False)
        report(run,full,main)
        status.update(status="complete",discoveries=len(main),completed_at=now())
        write_json(ROOT/"results"/"production_status.json",status)
    except BaseException as exc:
        status.update(status="interrupted_or_error",error=type(exc).__name__+": "+str(exc),updated_at=now())
        write_json(ROOT/"results"/"production_status.json",status)
        raise


if __name__=="__main__":
    main()
