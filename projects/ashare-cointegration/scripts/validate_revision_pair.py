"""Audit saved supplementary results, with four independently checked paths."""
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[key]='1'
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.adfvalues import mackinnonp
from src.dgp_calibration import generate_pair
from src.revision_pair import METHODS,SCENARIOS
from src.simulation_dh import write_json
from tests.test_engine_dh import literal_reference


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['engineering','formal'],required=True)
    args=parser.parse_args()
    output=ROOT/'results_revision/pair_comparison'
    private=ROOT/'.local/revision_pair'
    protocol=json.loads((output/'experiment_protocol.json').read_text())
    phase=protocol['phases'][args.phase]
    spec=json.loads((private/'source/results_review/dgp_fixed_nu_2021_2025/dgp_spec.json').read_text())
    status=json.loads((output/f'{args.phase}_status.json').read_text())
    files=sorted((private/args.phase/'batches').glob('*.parquet'))
    data=pd.concat([pd.read_parquet(path) for path in files],ignore_index=True)
    total=phase['repetitions_per_scenario']
    expected={(scenario,r,method) for scenario in SCENARIOS
              for r in range(total) for method in METHODS}
    assert status['status']=='complete' and len(data)==len(expected)
    assert not data[['scenario','repetition','method']].duplicated().any()
    assert set(zip(data.scenario,data.repetition,data.method))==expected
    assert data.phase.eq(args.phase).all()
    assert data.master_seed.eq(protocol['master_seed']).all()
    assert data.seed_stream.eq(phase['seed_stream']).all()
    assert data.scenario_index.eq(data.scenario.map({s:i for i,s in enumerate(SCENARIOS)})).all()
    assert data.true_alternative.eq(data.scenario.str.endswith('COINT')).all()
    assert data.heavy_tail.eq(data.scenario.str.startswith('HEAVY')).all()
    assert data.p.between(0,1).all()
    valid=data.status.isin(['valid','tail_unresolved'])
    assert data.loc[~valid,'p'].eq(1).all()
    np.testing.assert_allclose(data.loc[valid,'p'],data.loc[valid,'p_raw'],rtol=0,atol=0)
    good=data.loc[valid]
    for method,lag in [('EG-fixed-1',1),('DH-fixed-1',1),('DH-fixed-7',7)]:
        assert good.loc[good.method.eq(method),'used_lag'].eq(lag).all()
    assert good.n_effective.eq(protocol['n_obs']-good.used_lag-1).all()
    eg=good.loc[good.method.str.startswith('EG')]
    expected_p=np.array([mackinnonp(stat,regression='c',N=2) for stat in eg.statistic])
    np.testing.assert_allclose(eg.p,expected_p,rtol=1e-12,atol=0)
    dh=good.loc[good.method.str.startswith('DH')]
    np.testing.assert_allclose(dh.log_p,-dh.statistic/2,rtol=0,atol=1e-12)
    np.testing.assert_allclose(dh.p,np.exp(dh.log_p),rtol=1e-12,atol=0)

    summary=pd.read_csv(output/f'{args.phase}_summary.csv')
    assert len(summary)==32
    for row in summary.itertuples():
        group=data.loc[data.scenario.eq(row.scenario)&data.method.eq(row.method)]
        count=int(group.p.lt(row.alpha).sum())
        assert len(group)==row.repetitions==total and count==row.rejections
        ci=binomtest(count,total).proportion_ci(confidence_level=.95,method='exact')
        np.testing.assert_allclose([row.rate,row.mcse,row.lower_95,row.upper_95],
            [count/total,np.sqrt((count/total)*(1-count/total)/total),ci.low,ci.high],
            rtol=0,atol=1e-10)
    paired=pd.read_csv(output/f'{args.phase}_paired.csv')
    assert len(paired)==16
    for row in paired.itertuples():
        methods=('EG-fixed-1','DH-fixed-1') if row.comparison=='primary' else ('EG-AIC','DH-fixed-7')
        wide=data.loc[data.scenario.eq(row.scenario)].pivot(index='repetition',columns='method',values='p')
        a,b=wide[methods[0]].lt(row.alpha),wide[methods[1]].lt(row.alpha)
        n10,n01=int((a&~b).sum()),int((b&~a).sum())
        delta=(n10-n01)/total
        variance=((n10+n01)-total*delta*delta)/(total-1)
        assert [row.EG_only,row.DH_only,row.both,row.neither]==[
            n10,n01,int((a&b).sum()),int((~a&~b).sum())]
        np.testing.assert_allclose([row.difference_EG_minus_DH,row.paired_mcse],
                                   [delta,np.sqrt(variance/total)],rtol=0,atol=1e-12)

    checked=[]
    for scenario_index,scenario in enumerate(SCENARIOS):
        repetition=0 if args.phase=='engineering' else total-1
        entropy=[protocol['master_seed'],phase['seed_stream'],scenario_index,repetition]
        scenario_spec=protocol['scenarios'][scenario]
        values=generate_pair(spec,protocol['n_obs'],np.random.SeedSequence(entropy),
                             cointegrated=scenario_spec['cointegrated'],
                             heavy_tail=scenario_spec['heavy_tail'])
        a,b=values.T
        selected=data.loc[data.scenario.eq(scenario)&data.repetition.eq(repetition)].set_index('method')
        for method,lag,autolag in [('EG-fixed-1',1,None),('EG-AIC',None,'aic')]:
            stat,p,_=coint(a,b,trend='c',maxlag=lag,autolag=autolag)
            row=selected.loc[method]
            if row.status in ('valid','tail_unresolved'):
                np.testing.assert_allclose([row.statistic,row.p],[stat,p],rtol=1e-9,atol=1e-10)
        for method,lag in [('DH-fixed-1',1),('DH-fixed-7',7)]:
            reference=literal_reference(a,b,lag)
            row=selected.loc[method]
            assert row.status=='valid'
            np.testing.assert_allclose([row.statistic,row.p],
                                       [reference['Q'],reference['p']],rtol=1e-8,atol=1e-10)
        checked.append(dict(scenario=scenario,repetition=repetition,methods=4))
    inventory=json.loads((output/'reuse_inventory.json').read_text(encoding='utf-8'))
    for item in inventory['artifacts']:
        assert (ROOT/item['path']).read_bytes()==(private/'reused_evidence'/item['path']).read_bytes(),item['path']
    paths=data.drop_duplicates(['scenario','repetition'])
    serial_wall=float(paths.dgp_seconds.sum()+data.seconds.sum())
    serial_cpu=float(paths.dgp_cpu_seconds.sum()+data.cpu_seconds.sum())
    result=dict(status='passed',phase=args.phase,checked_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        paths=len(paths),test_rows=len(data),summary_rows=len(summary),paired_rows=len(paired),
        all_expected_keys=True,all_legacy_artifacts_unchanged=True,
        numerical_unavailable=int((~valid).sum()),zero_p_rows=int(data.p.eq(0).sum()),
        regenerated_paths_for_independent_check=checked,
        independent_recomputed_test_cases=16,full_retest=False,
        serial_equivalent_task_seconds=serial_wall,serial_equivalent_cpu_seconds=serial_cpu)
    if args.phase=='engineering':
        result['formal_four_worker_cpu_seconds_projection']=serial_cpu/len(paths)*20000/4
        result['projection_limit']='20-path timing extrapolation; not a guaranteed elapsed-time bound'
    write_json(output/f'{args.phase}_validation.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
