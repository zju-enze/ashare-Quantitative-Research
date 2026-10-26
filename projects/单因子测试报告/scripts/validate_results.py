"""Bounded acceptance: raw holdings arithmetic, result identities, deliverable links."""
from pathlib import Path
import argparse
import json
import re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    run, private = ROOT / 'outputs/runs' / args.run_id, ROOT / '.local/runs' / args.run_id
    def read(name, index=None):
        return pd.read_csv(run / (name + '.csv'), index_col=index)
    cal = read('calendar').set_index('signal_month')
    c1, c2 = read('C1').set_index('pool'), read('C2').set_index('pool')
    checks = []
    for pool in ['ALL_A', 'HS300', 'ZZ500']:
        m, net, gross, to = [read(pool+'_'+key, 0) for key in ['monthly', 'layers_net', 'layers_gross', 'turnover']]
        assert len(m) == 228 and m.index.tolist() == cal.holding_month.tolist()
        np.testing.assert_allclose(net, gross - .004*to, atol=1e-13)
        np.testing.assert_allclose(m.long_short, gross['5'] - gross['1'] - .004*(to['5'] + to['1']), atol=1e-13)
        wealth = np.r_[1, np.cumprod(1+m.long_short)]
        expected = [(np.prod(1+net[str(q)]))**(12/228)-1 for q in range(1,6)]
        np.testing.assert_allclose(c2.loc[pool, [f'Q{q}_ann' for q in range(1,6)]].astype(float), expected)
        np.testing.assert_allclose(c2.loc[pool, ['long_short_ann', 'long_short_sharpe', 'long_short_max_dd']].astype(float),
                                   [wealth[-1]**(12/228)-1, np.sqrt(12)*m.long_short.mean()/m.long_short.std(ddof=1), np.min(wealth/np.maximum.accumulate(wealth)-1)])
        np.testing.assert_allclose(c1.loc[pool, ['t_mean','factor_ret_mean','rank_ic_mean','rank_ic_sd','ic_ir']].astype(float),
                                   [m.t.mean(),m.factor_ret.mean(),m.ic.mean(),m.ic.std(ddof=1),m.ic.mean()/m.ic.std(ddof=1)])
        checks.append(dict(check='monthly_to_C1_C2_and_costs', pool=pool, status='passed', n=228))

    panel = pd.read_parquet(ROOT / '.local/preflight_repaired/candidate_panel.parquet')
    holdings = pd.read_parquet(private / 'ALL_A_holdings.parquet')
    gross = read('ALL_A_layers_gross', 0)
    monthly = read('ALL_A_monthly', 0)
    real_rows = []
    for month in ['2007-01', '2020-01', '2025-12']:
        g = panel[panel.S & panel.signal_month.eq(month)].merge(holdings[holdings.signal_month.eq(month)], on=['ts_code','signal_month'], validate='one_to_one')
        g['ret_fwd'] = g.exit_adjusted_value/g.entry_adjusted_value-1
        period = cal.loc[month,'holding_month']
        np.testing.assert_allclose(g.groupby('layer').ret_fwd.mean(), gross.loc[period].to_numpy(), atol=1e-13)
        np.testing.assert_allclose(g.ret_fwd.mean(), monthly.loc[period,'benchmark'], atol=1e-13)
        real_rows.append(g.sort_values('ts_code').head(3)[['ts_code','signal_month','entry_date','exit_date','entry_adjusted_value','exit_adjusted_value','exit_value_kind','layer','ret_fwd']])
        checks.append(dict(check='stock_values_to_frozen_layers', signal_month=month, n=len(g), status='passed'))
    pd.concat(real_rows).to_csv(private / 'acceptance_real_samples.csv', index=False, encoding='utf-8-sig')

    c4 = read('C4')
    assert len(c4) == 31 and c4.status.eq('complete').sum() == 30
    insufficient = c4[c4.status.ne('complete')]
    assert insufficient.n_months.tolist() == [12] and insufficient.ann_exc.isna().all()
    for name in ['D9', 'D10_size1', 'D10_size2', 'D10_size3']:
        counts, known = read(name+'_counts',0), read(name+'_known_weight',0)
        assert counts.shape == (228,10) and counts.min().min() >= 5
        np.testing.assert_allclose(known, 1)
    roll = read('D6_rolling_excess',0)
    assert roll.iloc[:11].isna().all().all() and roll.iloc[11:].notna().all().all()
    net = read('ALL_A_layers_net',0)
    for i in [11, 100, 227]:
        expected = (1+net.iloc[i-11:i+1]).prod() - (1+monthly.benchmark.iloc[i-11:i+1]).prod()
        np.testing.assert_allclose(roll.iloc[i], expected, atol=1e-13)
    checks.append(dict(check='domain_coverage_and_continuous_rolling_arithmetic', status='passed'))

    report_path = ROOT / 'report/bp_single_factor_report.md'
    report = report_path.read_text(encoding='utf-8')
    links = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', report)
    assert len(links) == 12 and all((report_path.parent / link).exists() for link in links)
    claims = pd.read_csv(ROOT / 'report/claim_evidence.csv')
    assert len(claims) == 18 and all(text in report for text in claims.claim_text)
    assert all((run / name).exists() for artifacts in claims.artifact for name in artifacts.split(';'))
    assert not any(x in report for x in ['待填写', 'Evidence needed', 'TODO'])
    checks.append(dict(check='12_figure_links_and_18_claim_sources', status='passed'))
    summary = dict(run_id=args.run_id, status='passed', checks=checks,
                   scope='Targeted result arithmetic and artifact correspondence, not a fresh source/PIT audit',
                   not_performed=['HAC time-series inference','industry multiple-testing correction','live execution simulation'],
                   numerical_tolerance='NumPy allclose default rtol with arithmetic atol=1e-13 where specified')
    (run / 'acceptance_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
