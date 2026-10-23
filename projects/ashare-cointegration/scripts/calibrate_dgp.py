"""Fixed-nu AR-GARCH estimation on saved proxies; no simulated observations."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.local/diagnostics_runtime/arch-8.0.0'))
for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS',
            'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import argparse
import json
import time
import warnings
import numpy as np
import pandas as pd
from arch import arch_model
from scipy.optimize import minimize

from src.dgp_calibration import moment_multiplier, volatility_coefficients

SOURCE = ROOT / '.local/review/student_t_2021_2025'
PRIVATE = ROOT / '.local/review/dgp_fixed_nu_2021_2025'
OUTPUT = ROOT / 'results_review/dgp_fixed_nu_2021_2025'
NU = {'market_proxy': 6., 'industry_proxy': 7., 'specific_proxy': 4.5}
MOMENT_LIMIT = 1 - 1e-6
SERIES = None


def now():
    return datetime.now().astimezone().isoformat()


def initialize():
    global SERIES
    SERIES = np.load(SOURCE / 'series.npy', mmap_mode='r')


def likelihood_setup(values):
    model = arch_model(values, mean='AR', lags=1, vol='GARCH',
                       p=1, q=1, dist='StudentsT', rescale=False)
    model._adjust_sample(None, None)
    residuals = model.resids(model.starting_values())
    backcast = model.volatility.backcast(residuals)
    var_bounds = model.volatility.variance_bounds(residuals)
    sigma2 = np.zeros(len(residuals))
    return model, backcast, var_bounds, sigma2, residuals


def fit_series(old):
    started = time.perf_counter()
    values = np.asarray(SERIES[:, int(old['series_index'])])
    scale = float(old['scale'])
    nu = NU[old['kind']]
    model, backcast, var_bounds, sigma2, residuals = likelihood_setup(values / scale)
    omega_bounds = model.volatility.bounds(residuals)[0]
    bounds = [(None, None), (-1 + 1e-6, 1 - 1e-6),
              tuple(np.log(omega_bounds)), (0., 1.), (0., 1.)]
    saved = np.array([old['mean_constant'] / scale, old['ar1'],
                      old['omega'] / scale**2, old['alpha'], old['beta']])
    mean_start = model.starting_values()
    default = np.r_[mean_start, model.volatility.starting_values(residuals)]

    def objective_raw(parameters, degrees=nu):
        return float(model._loglikelihood(np.r_[parameters, degrees],
                                         sigma2, backcast, var_bounds))

    previous_llf = -objective_raw(saved, old['nu'])
    if abs(previous_llf - old['loglikelihood']) > 1e-6:
        raise ValueError('Saved-likelihood mismatch: ' + str(old['identifier']))

    def encode(parameters, limit):
        c, rho, omega, a, b = parameters
        persistence = a + b
        share = a / persistence if persistence else .05
        max_a, max_b = volatility_coefficients(share, 1., nu, limit)
        fraction = persistence / (max_a + max_b)
        if fraction > 1:
            fraction = .99
            new_a, new_b = volatility_coefficients(share, fraction, nu, limit)
            omega = float(np.var(residuals)) * (1 - new_a - new_b)
        return np.array([c, np.clip(rho, *bounds[1]),
                         np.log(np.clip(omega, *omega_bounds)),
                         share, np.clip(fraction, 0, 1)])

    def decode(coordinates, limit):
        c, rho, logomega, share, fraction = coordinates
        a, b = volatility_coefficients(share, fraction, nu, limit)
        return np.array([c, rho, np.exp(logomega), a, b])

    attempts = []

    def optimize(starts, limit, label):
        candidates = []
        for n, parameters in enumerate(starts):
            x0 = encode(parameters, limit)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                result = minimize(lambda x: objective_raw(decode(x, limit)), x0,
                                  method='SLSQP', bounds=bounds,
                                  options={'maxiter': 700, 'ftol': 1e-8})
            final = decode(result.x, limit)
            value = objective_raw(final)
            record = dict(model=label, start=n, success=bool(result.success),
                          status=int(result.status), message=str(result.message),
                          iterations=int(result.nit), objective=value,
                          warnings=sorted(set(str(w.message) for w in caught)))
            attempts.append(record)
            if np.isfinite(value) and result.success:
                candidates.append((value, final))
        if not candidates:
            raise RuntimeError('No converged solution: ' + str(old['identifier']) +
                               ' ' + label + ' ' + json.dumps(attempts))
        return min(candidates, key=lambda entry: entry[0])

    baseline_nll, baseline = optimize([saved, default], None, 'fixed_nu')
    if moment_multiplier(*baseline[3:5], nu) <= MOMENT_LIMIT:
        constrained_nll, constrained = baseline_nll, baseline.copy()
        attempts.append(dict(model='finite_moment', reused_feasible_optimum=True))
    else:
        neutral = np.r_[baseline[:2], np.var(residuals) * .05, .05, .90]
        constrained_nll, constrained = optimize(
            [baseline, neutral], MOMENT_LIMIT, 'finite_moment')
    # A larger constrained likelihood exposes a missed unconstrained optimum.
    if constrained_nll < baseline_nll - 1e-6:
        retry_nll, retry = optimize([constrained], None, 'fixed_nu_nested_repair')
        if retry_nll < baseline_nll:
            baseline_nll, baseline = retry_nll, retry
    if constrained_nll < baseline_nll - 1e-5:
        raise RuntimeError('Unresolved nested optimum: ' + str(old['identifier']))

    output = []
    for label, parameters, nll in [('fixed_nu', baseline, baseline_nll),
                                    ('finite_moment', constrained, constrained_nll)]:
        c, rho, omega, a, b = map(float, parameters)
        km = moment_multiplier(a, b, nu)
        if label == 'finite_moment' and not (km < 1 and abs(rho) < 1):
            raise ValueError('Infeasible fitted driver: ' + str(old['identifier']))
        row = {k: old[k] for k in ('series_index', 'kind', 'identifier', 'name',
                                   'L2', 'members', 'controls')}
        row.update(model=label, nu=nu, nobs=len(residuals), scale=scale,
                   ar1=rho, mean_constant=c*scale, omega=omega*scale**2,
                   alpha=a, beta=b, persistence=a+b, moment_4_1=km,
                   moment_boundary=bool(label == 'finite_moment' and
                                        km > MOMENT_LIMIT - 1e-5),
                   loglikelihood=-nll, old_loglikelihood=old['loglikelihood'],
                   loss_from_old=old['loglikelihood']+nll,
                   moment_loss=constrained_nll-baseline_nll,
                   moment_loss_per_obs=(constrained_nll-baseline_nll)/len(residuals),
                   saved_likelihood_error=previous_llf-old['loglikelihood'])
        output.append(row)
    return dict(rows=output, attempts=attempts,
                seconds=time.perf_counter()-started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    old = pd.read_csv(SOURCE / 'estimates.csv', low_memory=False)
    old = old.loc[old.model.eq('garch_t') & old.kind.isin(NU)].copy()
    old = old.sort_values(['kind', 'series_index']).reset_index(drop=True)
    assert len(old) == 3106 and old.series_index.is_unique
    if args.preflight:
        parts = []
        for _, group in old.groupby('kind', sort=True):
            parts.append(group.iloc[np.unique(np.linspace(0, len(group)-1,
                                                         min(3,len(group))).astype(int))])
        tasks = pd.concat(parts).to_dict('records')
    else:
        tasks = old.to_dict('records')
    PRIVATE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / ('preflight.jsonl' if args.preflight else 'estimates.jsonl')
    if path.exists():
        raise FileExistsError(path)
    began = time.perf_counter()
    execution = dict(started_at=now(), status='running', tasks=len(tasks),
                     workers=args.workers, model_observations=1210,
                     fixed_nu=NU, finite_moment_order=4.1,
                     finite_moment_limit=MOMENT_LIMIT, simulations=False,
                     EG_DH_retests=False, completed=0)
    status_path = OUTPUT / ('preflight_execution.json' if args.preflight else
                            'execution.json')
    status_path.write_text(json.dumps(execution, indent=2), encoding='utf-8')
    with path.open('w', encoding='utf-8') as journal:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize) as pool:
            for done, result in enumerate(pool.map(fit_record, tasks), 1):
                journal.write(json.dumps(result, ensure_ascii=False) + '\n')
                journal.flush()
                execution['completed'] = done
                if args.preflight or done % 100 == 0 or done == len(tasks):
                    execution['elapsed_seconds'] = time.perf_counter()-began
                    status_path.write_text(json.dumps(execution, indent=2),
                                           encoding='utf-8')
                    print(f'{done}/{len(tasks)} series; '
                          f'{execution["elapsed_seconds"]:.1f}s', flush=True)
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    failures = [record for record in records if 'error' in record]
    execution.update(status='needs_repair' if failures else 'complete',
                     failed_series=len(failures), completed_at=now(),
                     elapsed_seconds=time.perf_counter()-began)
    status_path.write_text(json.dumps(execution, indent=2), encoding='utf-8')
    rows = [row for record in records for row in record.get('rows', [])]
    pd.DataFrame(rows).to_csv(PRIVATE / ('preflight_estimates.csv' if args.preflight
                                        else 'estimates.csv'), index=False)
    print(json.dumps(execution), flush=True)


def fit_record(old):
    try:
        return fit_series(old)
    except Exception as error:
        return dict(series_index=int(old['series_index']), identifier=old['identifier'],
                    kind=old['kind'], error=f'{type(error).__name__}: {error}')


if __name__ == '__main__':
    main()
