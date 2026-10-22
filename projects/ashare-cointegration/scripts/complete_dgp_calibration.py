"""Build a fitted, known-rank two-stock DGP without drawing simulated data."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_dgp as fit
import json
import time
import warnings
import numpy as np
import pandas as pd
from arch import arch_model
from arch.univariate import GARCH, StudentsT
from scipy.optimize import minimize
from src.dgp_calibration import moment_multiplier, volatility_coefficients


def free_nu_reference(current):
    old = pd.read_csv(fit.SOURCE / 'estimates.csv', low_memory=False)
    reference = old.loc[old.model.eq('garch_t') & old.kind.isin(fit.NU)].copy()
    bad = current.loc[current.loss_from_old.lt(-1e-5), 'series_index'].unique()
    repairs = []
    series = np.load(fit.SOURCE / 'series.npy', mmap_mode='r')
    for index in bad:
        position = reference.index[reference.series_index.eq(index)][0]
        row = reference.loc[position]
        base = current.loc[current.series_index.eq(index) &
                           current.model.eq('fixed_nu')].iloc[0]
        scale = row.scale
        start = np.array([base.mean_constant/scale, base.ar1, base.omega/scale**2,
                          base.alpha, base.beta, base.nu])
        with warnings.catch_warnings(record=True):
            result = arch_model(series[:, int(index)]/scale, mean='AR', lags=1,
                                vol='GARCH', p=1, q=1, dist='StudentsT',
                                rescale=False).fit(
                starting_values=start, disp='off', update_freq=0,
                show_warning=False, options={'maxiter':2000, 'ftol':1e-9})
        assert result.convergence_flag == 0
        assert result.loglikelihood >= base.loglikelihood - 1e-5
        p = result.params
        updates = dict(nu=float(p['nu']), ar1=float(p['y[1]']),
                       mean_constant=float(p['Const'])*scale,
                       omega=float(p['omega'])*scale**2,
                       alpha=float(p['alpha[1]']), beta=float(p['beta[1]']),
                       loglikelihood=float(result.loglikelihood))
        repairs.append(dict(series_index=int(index), identifier=row.identifier,
                            old_loglikelihood=float(row.loglikelihood),
                            new_loglikelihood=updates['loglikelihood'],
                            reason='fixed_nu_fit_exposed_saved_local_optimum'))
        for key, value in updates.items():
            reference.loc[position, key] = value
    columns = ['series_index','kind','identifier','name','L2','members','controls',
               'nobs','scale','nu','ar1','mean_constant','omega','alpha','beta',
               'loglikelihood']
    reference = reference[columns]
    reference.to_csv(fit.PRIVATE / 'free_nu_reference.csv', index=False)
    (fit.PRIVATE / 'reference_repairs.json').write_text(
        json.dumps(repairs, ensure_ascii=False, indent=2), encoding='utf-8')
    reference_llf = reference.set_index('series_index').loglikelihood
    current['reference_loglikelihood'] = current.series_index.map(reference_llf)
    current['loss_from_free_reference'] = (current.reference_loglikelihood -
                                           current.loglikelihood)
    current.to_csv(fit.PRIVATE / 'estimates.csv', index=False)
    return reference, repairs


def price_structure():
    source = fit.ROOT / '.local/production/formation-2021-2025-v2'
    universe = pd.read_parquet(source/'U.parquet').reset_index(drop=True)
    pairs = pd.read_parquet(source/'H.parquet')
    logprice = np.log(np.load(source/'prices.npy'))
    returns = np.diff(logprice, axis=0)
    stock_sd = returns.std(axis=0, ddof=1)
    standardized = returns / stock_sd
    centered = standardized - standardized.mean(axis=0)
    rho = float(np.sum(centered[1:]*centered[:-1]) /
                np.sum(centered[:-1]**2))
    assert abs(rho) < 1
    residual = centered[1:] - rho*centered[:-1]
    residual -= residual.mean(axis=0)
    nobs, nstocks = residual.shape
    variances = np.sum(residual**2, axis=0)/(nobs-1)
    total_covsum = (np.sum(residual.sum(axis=1)**2)/(nobs-1) -
                    variances.sum())/2
    within_covsum, within_count = 0., 0
    for indices in universe.groupby('L2', sort=True).indices.values():
        within_count += len(indices)*(len(indices)-1)//2
        within_covsum += (np.sum(residual[:,indices].sum(axis=1)**2)/(nobs-1)
                         -variances[indices].sum())/2
    assert within_count == len(pairs) == 67678
    total_count = nstocks*(nstocks-1)//2
    within = within_covsum/within_count
    between = (total_covsum-within_covsum)/(total_count-within_count)
    shares = np.array([between, within-between, variances.mean()-within])
    assert np.all(shares > 0)
    shares /= shares.sum()

    position = {code:i for i,code in enumerate(universe.ts_code)}
    a = pairs.A.map(position).to_numpy()
    b = pairs.B.map(position).to_numpy()
    standardized_levels = logprice / stock_sd
    rows = []
    for start in range(0,len(pairs),256):
        stop = min(start+256,len(pairs))
        spread = standardized_levels[:,a[start:stop]] - standardized_levels[:,b[start:stop]]
        spread -= spread.mean(axis=0)
        filtered = spread[1:] - rho*spread[:-1]
        lag, future = filtered[:-1], filtered[1:]
        lag = lag-lag.mean(axis=0)
        future = future-future.mean(axis=0)
        phi = np.sum(lag*future,axis=0)/np.sum(lag**2,axis=0)
        for j,value in enumerate(phi):
            rows.append(dict(candidate_id=pairs.iloc[start+j].candidate_id,
                             phi=float(value), spread_sd=float(spread[:,j].std(ddof=1))))
    summary = pd.DataFrame(rows)
    summary.to_csv(fit.PRIVATE/'pair_persistence.csv',index=False)
    phi = float(summary.phi.median())
    assert 0 < phi < 1
    result = dict(rho=rho, phi_alternative=phi,
                  stock_return_sd_median=float(np.median(stock_sd)),
                  innovation_variance_shares=dict(zip(('market','industry','specific'),
                                                       map(float,shares))),
                  within_pairs=within_count, cross_industry_pairs=total_count-within_count,
                  within_residual_correlation=float(within/variances.mean()),
                  cross_industry_residual_correlation=float(between/variances.mean()),
                  correlation_definition='Average covariance divided by mean residual variance; a homogeneous pair correlation target, not the mean pairwise Pearson correlation.',
                  phi_quantiles={str(q):float(summary.phi.quantile(q))
                                 for q in (.1,.25,.5,.75,.9)},
                  phi_outside_stationary_interval=int((summary.phi.abs()>=1).sum()),
                  price_error_note='All predefined pairs; no EG/DH screen. Median persistence is a descriptive calibration target, not evidence that the real pairs cointegrate.',
                  pair_normalization='Each log price divided by its own sample log-return standard deviation; fixed hedge vector (1,-1) in these coordinates.')
    (fit.OUTPUT/'price_structure.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def pooled_garch_shapes(current, structure):
    series = np.load(fit.SOURCE/'series.npy', mmap_mode='r')
    volatility, distribution = GARCH(1,0,1), StudentsT()
    rows = []
    for kind, nu in fit.NU.items():
        subset = current.loc[current.kind.eq(kind) & current.model.eq('finite_moment')]
        inputs = []
        for row in subset.itertuples():
            y = np.array(series[:,int(row.series_index)])
            y -= row.mean_constant/(1-row.ar1)
            residual = y[1:] - structure['rho']*y[:-1]
            residual /= residual.std(ddof=1)
            inputs.append((residual,volatility.backcast(residual),
                           volatility.variance_bounds(residual),np.empty(len(residual))))

        def parameters(x):
            a,b=volatility_coefficients(x[0],x[1],nu,fit.MOMENT_LIMIT)
            return np.array([1-a-b,a,b])

        def objective(x):
            parameters_here = parameters(x)
            loglikelihood = 0.
            for residual, backcast, var_bounds, variance in inputs:
                volatility.compute_variance(parameters_here,residual,variance,
                                             backcast,var_bounds)
                loglikelihood += distribution.loglikelihood([nu],residual,variance)
            return -float(loglikelihood)/(len(inputs)*1210)

        a,b=subset[['alpha','beta']].mean().to_numpy()
        share=a/(a+b)
        max_a,max_b=volatility_coefficients(share,1.,nu,fit.MOMENT_LIMIT)
        starts=[np.array([share,min((a+b)/(max_a+max_b),1.)]),np.array([.05,.95])]
        solutions=[]
        for start in starts:
            solution=minimize(objective,start,method='SLSQP',bounds=[(0,1),(0,1)],
                              options={'ftol':1e-11,'maxiter':500})
            if solution.success:
                solutions.append(solution)
        assert solutions, kind
        best=min(solutions,key=lambda solution:solution.fun)
        omega,a,b=map(float,parameters(best.x))
        rows.append(dict(kind=kind,nu=nu,alpha=a,beta=b,omega=omega,
                         moment_4_1=moment_multiplier(a,b,nu),series=len(inputs),
                         average_negative_loglikelihood=float(best.fun),
                         iterations=int(best.nit)))
        print('Pooled shape',json.dumps(rows[-1]),flush=True)
    frame=pd.DataFrame(rows)
    frame.to_csv(fit.OUTPUT/'dgp_driver_parameters.csv',index=False)
    return rows


def main():
    started=time.perf_counter()
    current=pd.read_csv(fit.PRIVATE/'estimates.csv')
    assert len(current)==6212 and current.series_index.nunique()==3106
    reference,repairs=free_nu_reference(current)
    print('Free-nu reference repairs',len(repairs),flush=True)
    structure=price_structure()
    print('Price structure',json.dumps(structure),flush=True)
    shapes=pooled_garch_shapes(current,structure)
    spec=dict(version='empirical-pair-dgp-1',calibrated_at=fit.now(),
              data_period='2021-2025',estimation_observations=1210,
              price_observations=1212,scope='known-rank two-stock system',
              price_input='log_adjusted_price',deterministic_drift=0.,
              rho=structure['rho'],phi_alternative=structure['phi_alternative'],
              return_scale=structure['stock_return_sd_median'],
              innovation_variance_shares=structure['innovation_variance_shares'],
              drivers={row['kind'].replace('_proxy',''):row for row in shapes},
              heavy_tail_specific_nu=3.5,initialization_burn_in=2000,
              finite_moment_order=4.1,finite_moment_limit=fit.MOMENT_LIMIT,
              simulations_run=False,
              assumptions=['Common short-run AR coefficient estimated from standardized stock returns gives a closed two-equation system.',
                           'Variance components match average within- and cross-industry innovation covariances; homogeneous loadings are a modeling restriction.',
                           'Alternative phi is the unfiltered median persistence of standardized within-industry log-price spreads; it does not identify real cointegration.',
                           'Pooled volatility shape is a composite-likelihood reference, not a claim of independent cross-sectional observations.',
                           'Zero drift and the known cointegration rank are imposed research-design restrictions.',
                           'The heavy-tail comparison keeps all parameters except specific nu unchanged and does not satisfy the DH moment assumption.',
                           'This pair DGP does not replicate the full overlapping-stock candidate graph.'])
    (fit.OUTPUT/'dgp_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(completed_at=fit.now(),seconds=time.perf_counter()-started,
                 reference_refits=len(repairs),pair_persistence_fits=67678,
                 pooled_component_fits=3,simulations=False,EG_DH_retests=False)
    (fit.OUTPUT/'construction_execution.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main()
