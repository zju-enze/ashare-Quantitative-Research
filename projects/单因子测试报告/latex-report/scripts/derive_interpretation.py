"""Derive interpretation numbers cited in the prose from locked aggregate CSVs.

No empirical model is rerun. Inputs are source-data/ files copied from run
bp-v05-20261026-main; outputs are three derived CSVs in source-data/.
Periods are labelled by holding month (the month in which the position is
entered), matching the tables and prose.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'source-data'
COST = 0.004


def read(name, **kw):
    return pd.read_csv(DATA / (name + '.csv'), encoding='utf-8-sig', **kw)


def layers(name):
    frame = read(name, index_col=0)
    frame.columns = [int(c) for c in frame.columns]
    return frame


def wealth(r):
    return pd.Series(np.cumprod(1 + r.to_numpy()), index=r.index)


def underwater(level, min_len, series, kind):
    """Runs below the running peak of a level series (wealth ratio or cumulative sum).

    The starting level (1 for wealth, 0 for sums) counts as the first peak.
    """
    start_level = 1.0 if kind == 'ratio' else 0.0
    values = np.r_[start_level, level.to_numpy()]
    labels = ['start'] + list(level.index)
    out, peak_i, run_start = [], 0, None
    for i in range(1, len(values) + 1):
        new_peak = i < len(values) and values[i] >= values[peak_i]
        if i < len(values) and not new_peak:
            run_start = i if run_start is None else run_start
            continue
        if run_start is not None:
            seg = values[run_start:i]
            if len(seg) >= min_len:
                trough = run_start + int(np.argmin(seg))
                depth = values[trough] / values[peak_i] - 1 if kind == 'ratio' else values[trough] - values[peak_i]
                out.append(dict(series=series, kind='below_prior_peak', peak_month=labels[peak_i],
                                start=labels[run_start], end=labels[i - 1], length=len(seg), extreme=depth,
                                extreme_month=labels[trough],
                                recovered_month=labels[i] if i < len(values) else 'not_recovered'))
            run_start = None
        if i < len(values):
            peak_i = i
    return out


def sign_runs(values, sign, min_len, series):
    out, start = [], None
    items = list(values.items())
    for i, (month, v) in enumerate(items + [(None, np.nan)]):
        hit = month is not None and np.sign(v) == sign
        if hit and start is None:
            start = i
        if not hit and start is not None:
            seg = values.iloc[start:i]
            if len(seg) >= min_len:
                out.append(dict(series=series, kind='negative_run' if sign < 0 else 'positive_run',
                                peak_month='', start=seg.index[0], end=seg.index[-1], length=len(seg),
                                extreme=seg.min() if sign < 0 else seg.max(),
                                extreme_month=seg.idxmin() if sign < 0 else seg.idxmax(),
                                recovered_month='to_end' if i == len(items) else ''))
            start = None
    return out


def main():
    m = read('ALL_A_monthly', index_col=0)
    net, gross, to = layers('ALL_A_layers_net'), layers('ALL_A_layers_gross'), layers('ALL_A_turnover')
    b, ls = m.benchmark, m.long_short
    assert np.allclose(ls, gross[5] - gross[1] - COST * (to[5] + to[1]), atol=1e-12)

    # Exact two-sided decomposition: LS_net = (Q5_net - B) + (B - Q1_gross - c*TO1).
    long_part = net[5] - b
    short_part = b - gross[1] - COST * to[1]
    assert np.allclose(long_part + short_part, ls, atol=1e-12)
    year = pd.PeriodIndex(m.index, freq='M').year
    rows = []
    for y in sorted(set(year)):
        k = year == y
        rows.append(dict(year=y, n_months=int(k.sum()), long_part=long_part[k].sum(), short_part=short_part[k].sum()))
    rows.append(dict(year='all_annualized', n_months=len(m), long_part=12 * long_part.mean(), short_part=12 * short_part.mean()))
    decomposition = pd.DataFrame(rows)
    decomposition['short_share'] = decomposition.short_part / (decomposition.long_part + decomposition.short_part)
    decomposition.to_csv(DATA / 'derived_C3_decomposition.csv', index=False, encoding='utf-8-sig')

    periods = []
    rel = wealth(net[5]) / wealth(b)
    periods += underwater(rel, 12, 'D5_Q5_relative_wealth', 'ratio')
    d6 = read('D6_rolling_excess', index_col=0)['5'].dropna()
    periods += sign_runs(d6, -1, 6, 'D6_Q5_rolling_excess')
    periods += underwater(m.factor_ret.cumsum(), 12, 'D3_cumulative_coefficient', 'diff')
    periods += underwater(m.ic.cumsum(), 6, 'D2_cumulative_rank_ic', 'diff')
    size = read('size_correlation', index_col=0).rho
    for sgn in (-1, 1):
        periods += sign_runs(size, sgn, 12, 'size_correlation_sign')
    for pool in ['HS300', 'ZZ500']:
        w = wealth(read(f'{pool}_monthly', index_col=0).long_short)
        full = pd.concat([pd.Series([1.0], index=['start']), w])
        dd = full / full.cummax() - 1
        trough = dd.idxmin()
        periods.append(dict(series=f'{pool}_long_short_max_drawdown', kind='peak_to_trough',
                            peak_month=full[:trough].idxmax(), start='', end=trough, length='',
                            extreme=dd.min(), extreme_month=trough, recovered_month=''))
    pd.DataFrame(periods).to_csv(DATA / 'derived_periods.csv', index=False, encoding='utf-8-sig')

    stats = read('ALL_A_layer_stats', index_col=0)
    flow = read('D1_sample_flow')
    summary = [('rel_wealth_2019_01_to_2020_12', rel['2020-12'] / rel['2018-12'] - 1),
               ('rel_wealth_end', rel.iloc[-1]),
               ('q5_excess_max_dd', stats.loc[5, 'excess_max_dd']),
               ('d6_last_endpoint_q5', d6.iloc[-1]),
               ('t_gt2', int((m.t > 2).sum())), ('t_lt_minus2', int((m.t < -2).sum())), ('t_gt0', int((m.t > 0).sum())),
               ('short_part_ann', 12 * short_part.mean()), ('long_part_ann', 12 * long_part.mean()),
               ('corr_ls_long_excess_complete_years',
                read('C3').query('~partial_year')[['long_short_return', 'long_excess']].corr().iloc[0, 1])]
    for q in range(1, 6):
        summary.append((f'turnover_after_first_Q{q}', to[q].iloc[1:].mean()))
    d10 = read('D10_size1_turnover', index_col=0)
    summary.append(('turnover_after_first_D10_low_Q10', d10['10'].iloc[1:].mean()))
    for pool, g in flow.groupby('pool'):
        cov = g.set_index('signal_month').bp_coverage_f_over_u
        summary += [(f'coverage_min_{pool}', cov.min()), (f'coverage_min_month_{pool}', cov.idxmin())]
        if pool == 'ALL_A':
            early = cov[cov.index <= '2012-12']
            late = cov[cov.index >= '2013-01']
            summary += [('coverage_ALL_A_2007_2012_mean', early.mean()), ('coverage_ALL_A_2007_2012_min', early.min()),
                        ('coverage_ALL_A_2013_on_mean', late.mean()), ('coverage_ALL_A_2013_on_min', late.min()),
                        ('valuation_row_missing_2007_2012', int(g[g.signal_month <= '2012-12'].valuation_row_missing.sum())),
                        ('valuation_row_missing_total', int(g.valuation_row_missing.sum()))]
    summary.append(('size_corr_abs_gt_0_1', int((size.abs() > 0.1).sum())))
    pd.DataFrame(summary, columns=['key', 'value']).to_csv(DATA / 'derived_summary.csv', index=False, encoding='utf-8-sig')
    print('Wrote derived_C3_decomposition.csv, derived_periods.csv, derived_summary.csv')


if __name__ == '__main__':
    main()
