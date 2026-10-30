"""Check saved sensitivity holdings/returns and independently refit three real months."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    out, private = ROOT / 'outputs/runs' / args.run_id, ROOT / '.local/runs' / args.run_id
    manifest = json.loads((out / 'run_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'complete'
    responses = pd.read_parquet(private / 'responses.parquet')
    calendar = pd.read_csv(out / 'calendar.csv').set_index('signal_month')
    sampled = ['2007-01', '2020-01', '2025-12']
    baseline = None
    records, changes = [], []

    def close(actual, expected):
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-13)

    for scheme in manifest['schemes']:
        name = scheme['id']
        target = out / name
        formed = pd.read_parquet(private / name / 'formations.parquet')
        holdings = pd.read_parquet(private / name / 'holdings.parquet')
        keys = ['signal_month', 'ts_code']
        inputs = formed[keys + ['pb', 'total_mv', 'circ_mv', 'industry_code']]
        if baseline is None:
            baseline = inputs.copy()
            baseline_holdings = holdings.set_index(keys).layer
        pd.testing.assert_frame_equal(inputs, baseline, check_exact=True)
        pd.testing.assert_frame_equal(holdings[keys], formed[keys], check_exact=True)
        monthly = pd.read_csv(target / 'monthly.csv', index_col=0)
        turnover = pd.read_csv(target / 'turnover.csv', index_col=0)
        gross = pd.read_csv(target / 'layers_gross.csv', index_col=0)
        net = pd.read_csv(target / 'layers_net.csv', index_col=0)
        costs = pd.read_csv(target / 'costs.csv', index_col=0)
        diag = pd.read_csv(target / 'winsor_diagnostics.csv', index_col=0)
        data = formed.merge(holdings, on=keys, validate='one_to_one').merge(responses[keys + ['ret_fwd']], on=keys, validate='one_to_one')
        previous = {q: set() for q in range(1, 6)}
        for month, g in data.groupby('signal_month', sort=True):
            period = calendar.loc[month, 'holding_month']
            raw = 1 / g.pb
            if scheme['method'] == 'quantile_01_99':
                lo, hi = raw.quantile([.01, .99], interpolation='linear')
            else:
                median = raw.median()
                mad = (raw - median).abs().median()
                lo, hi = median - scheme['k'] * mad, median + scheme['k'] * mad
            expected = raw.clip(lo, hi)
            close(g.bp_w, expected)
            close([diag.loc[month, 'lower'], diag.loc[month, 'upper']], [lo, hi])
            assert diag.loc[month, 'n_changed'] == raw.ne(expected).sum()
            close(diag.loc[month, 'changed_fraction'], raw.ne(expected).mean())
            close(g.bp_z, (expected - expected.mean()) / expected.std(ddof=0))
            ranks = rankdata(g.f_neu, method='ordinal')
            np.testing.assert_array_equal(g.residual_rank, ranks)
            layers = np.searchsorted(1 + (len(g) - 1) * np.arange(1, 5) / 5, ranks, side='left') + 1
            np.testing.assert_array_equal(g.layer, layers)
            for q, group in g.groupby('layer'):
                members = set(group.ts_code)
                to = 1 - len(previous[q] & members) / len(members)
                close(turnover.loc[period, str(q)], to)
                close(group.weight, 1 / len(members))
                close(gross.loc[period, str(q)], group.ret_fwd.mean())
                close(costs.loc[period, str(q)], .004 * to)
                close(net.loc[period, str(q)], group.ret_fwd.mean() - .004 * to)
                previous[q] = members
            close(monthly.loc[period, 'benchmark'], g.ret_fwd.mean())
            close(monthly.loc[period, 'ic'], spearmanr(g.f_neu, g.ret_fwd).statistic)
            close(monthly.loc[period, 'long_short'], gross.loc[period, '5'] - gross.loc[period, '1'] - costs.loc[period, ['5', '1']].sum())
            if month in sampled:
                dummies = pd.get_dummies(g.industry_code, drop_first=True).astype(float).to_numpy()
                x = np.column_stack([np.ones(len(g)), np.log(g.total_mv), dummies])
                close(g.f_neu, sm.OLS(expected.to_numpy(), x).fit().resid)
                xw = np.column_stack([np.ones(len(g)), g.bp_z, np.log(g.total_mv), dummies])
                fit = sm.WLS(g.ret_fwd.to_numpy(), xw, weights=np.sqrt(g.circ_mv)).fit()
                close(monthly.loc[period, ['factor_ret', 't']].to_numpy(dtype=float), [fit.params[1], fit.tvalues[1]])
        changed = holdings.set_index(keys).layer.ne(baseline_holdings)
        changes.append(changed.groupby(level=0).agg(['sum', 'mean']).rename(
            columns={'sum': 'changed_layer_count', 'mean': 'changed_layer_fraction'}).assign(scheme=name).reset_index())
        records.append(dict(scheme=name, status='passed', checked_stock_periods=len(data), months=len(calendar),
                            independent_ols_wls_months=sampled, changed_layer_count=int(changed.sum())))
    pd.concat(changes).to_csv(out / 'holding_change_vs_mad5.csv', index=False, encoding='utf-8-sig')
    audit = dict(status='passed', checks=records,
                 scope='All raw inputs, clipping bounds/counts, z-scores, ranks, layers, returns, turnover and costs; OLS/WLS via statsmodels for three predefined months per scheme.')
    (out / 'numerical_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
