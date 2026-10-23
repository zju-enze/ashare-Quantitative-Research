"""Verify saved calibration coverage, refresh summaries, and export final evidence."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
from datetime import datetime,timezone
import subprocess
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import coint
from src.simulation import STAGES,summarize,panel

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/simulation'


def main():
    all_summaries=[];audit={};runtime=[]
    for stage,(_,groups,size,repeats,scenarios) in STAGES.items():
        folder=ROOT/'.local/simulation'/stage
        paths=sorted(p for p in folder.glob('*/*.parquet') if not p.name.endswith('.pairs.parquet'))
        expected={(s,r) for s in scenarios for r in range(repeats)}
        assert {(p.parent.name,int(p.stem)) for p in paths}==expected and len(paths)==len(expected)
        assert len(list(folder.glob('*/*.pairs.parquet')))==len(expected)
        expected_families={('GLOBAL','GLOBAL')}|{('L2',f'G{g}') for g in range(groups)}|{
            ('L3',f'G{g}L{j}') for g in range(groups) for j in range(2)}
        expected_rows={(d,f,m) for d,f in expected_families for m in ('BF','Holm','BH')}
        frames=[]
        for path in paths:
            frame=pd.read_parquet(path);s,r=path.parent.name,int(path.stem)
            assert path.with_name(path.stem+'.pairs.parquet').exists()
            assert set(frame.stage)=={stage} and set(frame.scenario)=={s} and set(frame.repetition)=={r}
            assert len(frame)==len(expected_rows) and set(zip(frame.domain,frame.family,frame.method))==expected_rows
            assert frame[['seconds','numerical_count','tail_zero_count']].nunique().eq(1).all()
            runtime.append(dict(stage=stage,scenario=s,repetition=r,seconds=float(frame.seconds.iloc[0]),
                numerical_count=int(frame.numerical_count.iloc[0]),tail_zero_count=int(frame.tail_zero_count.iloc[0])))
            frames.append(frame)
        data=pd.concat(frames,ignore_index=True);result=summarize(data)
        assert result.B.eq(repeats).all()
        old=pd.read_csv(OUT/f'{stage}_summary.csv')
        unchanged=[c for c in result if not c.endswith('_MCSE')]
        pd.testing.assert_frame_equal(old[unchanged],result[unchanged],check_dtype=False,rtol=1e-12,atol=1e-14)
        result.to_csv(OUT/f'{stage}_summary.csv',index=False);all_summaries.append(result)
        audit[stage]=dict(completed=len(paths),planned=len(expected),repeats_per_scenario=repeats,
            scenarios=scenarios,metrics_and_pair_files_complete=True,unique_family_rows_per_panel=len(expected_rows),
            point_estimates_and_alarm_decisions_unchanged=True)
        print(stage,len(paths),'complete checkpoints verified',flush=True)
    totals=pd.DataFrame(runtime).groupby(['stage','scenario']).agg(panels=('repetition','size'),
        panel_seconds_mean=('seconds','mean'),panel_seconds_median=('seconds','median'),panel_seconds_max=('seconds','max'),
        numerical_count=('numerical_count','sum'),tail_zero_count=('tail_zero_count','sum')).reset_index()
    totals.to_csv(OUT/'runtime_and_numerical_summary.csv',index=False)
    summary=pd.concat(all_summaries,ignore_index=True)
    summary[(summary.domain=='L2') & (summary.method=='Holm')].to_csv(OUT/'fixed_L2_Holm_final.csv',index=False)
    summary[summary.main_alarm].to_csv(OUT/'main_alarm_families.csv',index=False)
    diagnostic=pd.read_csv(OUT/'increment_and_gate_diagnostics.csv')
    for stage,(_,_,_,repeats,scenarios) in STAGES.items():
        part=diagnostic[diagnostic.stage==stage]
        assert part.B.eq(repeats).all() and set(part.scenario)==set(scenarios)
        assert len(part)==len(all_summaries[list(STAGES).index(stage)])
    checks=[]
    for stage,scenario in [('S1','N5'),('S1','N6'),('S1','N7'),('S2','N1'),('S2','N5'),('S2','N6')]:
        for path in sorted((ROOT/'.local/simulation'/stage/scenario).glob('*.pairs.parquet')):
            full=pd.read_parquet(path)
            selected=full[full.reject_L2_Holm & ~full.true_alternative & full.compute_status.eq('valid')]
            if selected.empty:continue
            row=selected.sort_values('candidate_id').iloc[0];repetition=int(path.name.split('.')[0])
            _,truth,values=panel(stage,scenario,repetition)
            assert not truth.true_alternative.any()
            stat,pvalue,_=coint(values[row.A],values[row.B],trend='c',autolag='aic',maxlag=None)
            np.testing.assert_allclose([stat,pvalue],[row.EG_stat,row.p_raw],rtol=1e-10,atol=1e-13)
            checks.append(dict(stage=stage,scenario=scenario,repetition=repetition,candidate_id=row.candidate_id,
                saved_stat=float(row.EG_stat),library_stat=float(stat),saved_p=float(row.p_raw),library_p=float(pvalue)))
            break
        else:raise AssertionError('Expected alarm rejection not found')
    (OUT/'alarm_investigation_final.json').write_text(json.dumps(dict(status='sampled_rejections_match_real_coint',
        cases=checks,scope='First saved valid false Holm rejection in each newly alarming stage/scenario; not an exhaustive proof.',
        conclusion='No mismatch in sampled EG results. Retain all finite-sample calibration warnings; do not tune the market specification.'),indent=2))
    fig,axes=plt.subplots(2,1,figsize=(11,7),layout='constrained')
    for ax,stage,scenarios in [(axes[0],'S1',[f'N{i}' for i in range(8)]+['M0','M1']),
                              (axes[1],'S2',['N1','N5','N6','M1'])]:
        part=summary[(summary.stage==stage)&(summary.domain=='L2')&(summary.method=='Holm')]
        for g in range(4):
            f=part[part.family==f'G{g}'].set_index('scenario').loc[scenarios]
            x=np.arange(len(scenarios))+(g-1.5)*.12
            ax.errorbar(x,f.FWER,yerr=[f.FWER-f.FWER_Wilson_low,f.FWER_Wilson_high-f.FWER],
                fmt='o',ms=4,capsize=2,label=f'G{g}')
        ax.axhline(.05,color='black',ls='--',lw=1,label='Nominal 0.05')
        ax.set_xticks(range(len(scenarios)),scenarios);ax.set_ylim(0,.7)
        ax.set_title(f'{stage}: fixed L2 families, Holm FWER');ax.set_ylabel('FWER');ax.legend(ncol=5,fontsize=8)
    fig.suptitle('Pointwise 95% Wilson intervals; families are not independent replications')
    fig.savefig(ROOT/'results/figures/calibration_fwer.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.8),layout='constrained')
    scenarios=[f'A{i}' for i in range(6)]+['M0','M1']
    for metric,color,label in [('power','#23699d','Unconditional power'),('conditional_power_mean','#d07724','Power among surviving alternatives')]:
        table=summary if metric=='power' else diagnostic
        part=table[(table.stage=='S1')&(table.domain=='L2')&(table.method=='Holm')]
        for g in range(4):
            f=part[part.family==f'G{g}'].set_index('scenario').loc[scenarios]
            ax.scatter(np.arange(len(scenarios))+(g-1.5)*.07+(-.18 if metric=='power' else .18),f[metric],
                s=20,color=color,label=label if g==0 else None)
    ax.set_xticks(range(len(scenarios)),scenarios);ax.set_ylim(0,1.04);ax.set_ylabel('Power')
    ax.set_title('S1 Holm power: four fixed L2 families per scenario');ax.legend(fontsize=8)
    fig.savefig(ROOT/'results/figures/calibration_power.png',dpi=160);plt.close(fig)
    acceptance=dict(status='passed',checked_at=datetime.now(timezone.utc).isoformat(),stages=audit,
        total_panels=sum(v['completed'] for v in audit.values()),diagnostics_complete=True,
        binary_MCSE='sqrt(r*(1-r)/B); other MCSE uses repetition-level sample SD/sqrt(B)',
        recomputed_EG_for_completion=False,alarm_recheck_samples=len(checks),
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    (OUT/'final_acceptance.json').write_text(json.dumps(acceptance,indent=2))
    print(json.dumps(acceptance),flush=True)


if __name__=='__main__':main()
