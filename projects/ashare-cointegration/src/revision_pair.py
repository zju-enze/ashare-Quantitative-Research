"""Supplementary paired EG/DH comparison, reusing the existing kernels."""
from pathlib import Path
from time import perf_counter, process_time
import warnings
import numpy as np
import pandas as pd
from scipy.stats import beta as beta_distribution
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.adfvalues import _tau_mins

from .engine import eg_audit as legacy_eg_audit
from .engine_dh_market import _audit_used_prefix as dh_audit
from .dgp_calibration import generate_pair

METHODS = ('EG-fixed-1', 'DH-fixed-1', 'EG-AIC', 'DH-fixed-7')
SCENARIOS = ('PAIR_NULL', 'PAIR_COINT', 'HEAVY_NULL', 'HEAVY_COINT')
SPEC = None
PROTOCOL = None
FOLDER = None
PHASE = None


def eg_fixed_audit(a, b):
    """Use the locked coint implementation, retaining v1's zero-value policy."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        statistic, probability, _ = coint(a, b, trend='c', maxlag=1, autolag=None)
    warning_names = ';'.join(type(w.message).__name__ for w in caught)
    row = dict(EG_stat=float(statistic), p_raw=None, p_for_adjustment=1.,
               compute_status='numerically_ineligible', used_lag=None,
               N_effective=None, placeholder_reason=None,
               p_zero_origin=None, warning_class=warning_names)
    if 'CollinearityWarning' in warning_names:
        row.update(placeholder_reason='near_collinearity',
                   p_zero_origin='near_collinearity_forced')
        return row
    if not np.isfinite(statistic) or not np.isfinite(probability) or not 0 <= probability <= 1:
        row['placeholder_reason'] = 'nonfinite_stat_or_invalid_p'
        return row
    row.update(p_raw=float(probability), p_for_adjustment=float(probability),
               compute_status='valid', used_lag=1, N_effective=len(a)-2)
    if probability == 0:
        row.update(compute_status='tail_unresolved',
                   p_zero_origin='mackinnon_boundary' if statistic < _tau_mins['c'][1]
                   else 'normal_cdf_zero')
    return row


def run_methods(values):
    a, b = values[:, 0], values[:, 1]
    rows = []
    for method in METHODS:
        started, cpu = perf_counter(), process_time()
        if method == 'EG-fixed-1':
            audit = eg_fixed_audit(a, b)
        elif method == 'EG-AIC':
            audit = legacy_eg_audit(a, b)
        else:
            audit = dh_audit(a, b, lags=1 if method == 'DH-fixed-1' else 7)
        wall, cpu_seconds = perf_counter()-started, process_time()-cpu
        is_eg = method.startswith('EG')
        rows.append(dict(method=method, statistic=audit.get('EG_stat' if is_eg else 'Q'),
                         p_raw=audit['p_raw'], p=audit['p_for_adjustment'],
                         log_p=audit.get('log_p'), status=audit['compute_status'],
                         used_lag=audit.get('used_lag' if is_eg else 'lags'),
                         n_effective=audit['N_effective'],
                         placeholder_reason=audit['placeholder_reason'],
                         p_zero_origin=audit['p_zero_origin'],
                         warning_class=audit.get('warning_class',''),
                         seconds=wall, cpu_seconds=cpu_seconds))
    return rows


def initialize(spec, protocol, folder, phase):
    global SPEC, PROTOCOL, FOLDER, PHASE
    SPEC, PROTOCOL, FOLDER, PHASE = spec, protocol, Path(folder), phase


def checkpoint_path(folder, task):
    scenario, start, stop = task
    return Path(folder) / 'batches' / f'{scenario}_{start:05d}_{stop:05d}.parquet'


def validate_checkpoint(path, task, protocol, phase):
    scenario, start, stop = task
    frame = pd.read_parquet(path)
    expected = {(r,m) for r in range(start,stop) for m in METHODS}
    if (len(frame) != len(expected) or
            set(zip(frame.repetition,frame.method)) != expected or
            not frame.scenario.eq(scenario).all() or not frame.phase.eq(phase).all() or
            not frame.master_seed.eq(protocol['master_seed']).all() or
            not frame.seed_stream.eq(protocol['phases'][phase]['seed_stream']).all() or
            not frame.p.between(0,1).all()):
        raise ValueError(f'Incomplete or mismatched checkpoint: {path}')
    return frame


def run_batch(task):
    path = checkpoint_path(FOLDER,task)
    if path.exists():
        frame = validate_checkpoint(path,task,PROTOCOL,PHASE)
        return dict(task=task, paths=frame.repetition.nunique(), reused=True)
    scenario, start, stop = task
    scenario_index = SCENARIOS.index(scenario)
    scenario_spec = PROTOCOL['scenarios'][scenario]
    stream = PROTOCOL['phases'][PHASE]['seed_stream']
    rows = []
    for repetition in range(start,stop):
        entropy = [PROTOCOL['master_seed'], stream, scenario_index, repetition]
        began, cpu = perf_counter(), process_time()
        values = generate_pair(SPEC, PROTOCOL['n_obs'], np.random.SeedSequence(entropy),
                               cointegrated=scenario_spec['cointegrated'],
                               heavy_tail=scenario_spec['heavy_tail'])
        dgp_seconds, dgp_cpu = perf_counter()-began, process_time()-cpu
        if values.shape != (PROTOCOL['n_obs'],2) or not np.isfinite(values).all():
            raise ArithmeticError(f'Invalid generated path: {scenario}/{repetition}')
        values.setflags(write=False)
        for result in run_methods(values):
            result.update(phase=PHASE,scenario=scenario,scenario_index=scenario_index,
                          repetition=repetition,master_seed=PROTOCOL['master_seed'],
                          seed_stream=stream,true_alternative=scenario_spec['cointegrated'],
                          heavy_tail=scenario_spec['heavy_tail'],dgp_seconds=dgp_seconds,
                          dgp_cpu_seconds=dgp_cpu)
            rows.append(result)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix('.tmp.parquet')
    pd.DataFrame(rows).to_parquet(temporary,index=False)
    temporary.replace(path)
    return dict(task=task,paths=stop-start,reused=False)


def confidence_interval(count, total):
    return (float(beta_distribution.ppf(.025,count,total-count+1)) if count else 0.,
            float(beta_distribution.ppf(.975,count+1,total-count)) if count<total else 1.)


def summarize(frame):
    rows=[]
    for (scenario,method),group in frame.groupby(['scenario','method'],sort=False):
        for alpha in (.05,.01):
            total=len(group);count=int(group.p.lt(alpha).sum());rate=count/total
            low,high=confidence_interval(count,total)
            rows.append(dict(scenario=scenario,method=method,alpha=alpha,
                             metric='power' if group.true_alternative.iloc[0] else 'type_I_error',
                             repetitions=total,rejections=count,rate=rate,
                             lower_95=low,upper_95=high,mcse=np.sqrt(rate*(1-rate)/total),
                             numerical_unavailable=int((~group.status.isin(['valid','tail_unresolved'])).sum()),
                             zero_p_count=int(group.p.eq(0).sum()),
                             lag_median=float(group.used_lag.median()),
                             lag_max=float(group.used_lag.max()),
                             method_seconds=float(group.seconds.sum())))
    return pd.DataFrame(rows)


def paired_comparisons(frame):
    output=[]
    for scenario,group in frame.groupby('scenario',sort=False):
        wide=group.pivot(index='repetition',columns='method',values='p')
        for label,eg,dh in [('primary','EG-fixed-1','DH-fixed-1'),
                            ('working_specs','EG-AIC','DH-fixed-7')]:
            for alpha in (.05,.01):
                a,b=wide[eg].lt(alpha).to_numpy(),wide[dh].lt(alpha).to_numpy()
                difference=a.astype(float)-b.astype(float)
                output.append(dict(scenario=scenario,comparison=label,alpha=alpha,
                    repetitions=len(wide),EG_only=int(np.sum(a & ~b)),
                    DH_only=int(np.sum(b & ~a)),both=int(np.sum(a & b)),
                    neither=int(np.sum(~a & ~b)),difference_EG_minus_DH=float(difference.mean()),
                    paired_mcse=float(difference.std(ddof=1)/np.sqrt(len(difference)))))
    return pd.DataFrame(output)
