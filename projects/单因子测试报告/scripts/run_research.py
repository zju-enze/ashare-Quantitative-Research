"""Run frozen BP study from the accepted P1 panel; raw course inputs are read-only."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
from datetime import datetime
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--course-root', type=Path)
    args = parser.parse_args()
    course_root = args.course_root or Path(json.loads((ROOT / '.local/paths.json').read_text(encoding='utf-8-sig'))['course_root'])
    sys.path.insert(0, str(course_root))
    sys.path.insert(0, str(ROOT / 'src'))
    import bp_core as bp

    out, private = ROOT / 'outputs/runs' / args.run_id, ROOT / '.local/runs' / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    panel_path = ROOT / '.local/preflight_repaired/candidate_panel.parquet'
    calendar_path = ROOT / 'outputs/preflight_repaired/calendar_audit.csv'
    index_path = course_root / 'data/offline/index_daily.parquet'
    source_version = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    config = dict(run_id=args.run_id, method_version='0.5', source_version=source_version,
                  started_at=datetime.now().isoformat(), status='running', cost_rt=.004,
                  main_layers=5, min_stocks=50, min_distinct_bp=20, mad_k=5, zscore_ddof=0,
                  wls_objective_weight='sqrt(circ_mv)', rf=0, time_std_ddof=1, ic_ir_annualized=False,
                  c4_signal_window=['2021-07', '2025-12'], c4_min_stocks=25,
                  d10_size_field='circ_mv', d10_bins=3, d10_layers=10,
                  inputs=[dict(name=name, bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns)
                          for name, p in [('accepted_panel', panel_path), ('calendar', calendar_path), ('index_daily', index_path)]])
    def write_config():
        (out / 'run_manifest.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    write_config()
    def csv(frame, name, index=False):
        frame.to_csv(out / (name + '.csv'), index=index, encoding='utf-8-sig')
    def save_result(res, name):
        monthly = pd.DataFrame({k: res[k] for k in ['factor_ret', 't', 'ic', 'benchmark', 'long_short', 'n_formed', 'n_response']})
        csv(monthly, name + '_monthly', True)
        for key in ['layers_gross', 'layers_net', 'turnover', 'counts', 'known_weight']:
            csv(res[key], name + '_' + key, True)
        csv(res['reasons'], name + '_issues')
        csv(bp.layer_statistics(res), name + '_layer_stats', True)
        res['holdings'].to_parquet(private / (name + '_holdings.parquet'), index=False)

    panel = pd.read_parquet(panel_path)
    cal_all = pd.read_csv(calendar_path, dtype={'signal_date': str, 'entry_date': str, 'exit_date': str})
    cal = cal_all[cal_all.holding_complete].reset_index(drop=True)
    assert len(cal) == 228 and cal.signal_month.iloc[0] == '2007-01' and cal.signal_month.iloc[-1] == '2025-12'
    assert pd.PeriodIndex(cal.holding_month, freq='M').equals(pd.period_range('2007-02', '2026-01', freq='M'))
    csv(cal, 'calendar')
    flow = pd.read_csv(ROOT / 'outputs/preflight_repaired/sample_flow.csv')
    csv(flow, 'D1_sample_flow')

    # Diagnostic U/F is independent of future response availability and regression S.
    f = panel[panel.F].copy()
    f['bp'] = 1 / f.pb
    diag = []
    for month, g in f.groupby('signal_month'):
        valid = g[np.isfinite(g.total_mv) & g.total_mv.gt(0)]
        rho = spearmanr(valid.bp, np.log(valid.total_mv)).statistic if len(valid) >= 50 and valid.bp.nunique() >= 20 else np.nan
        diag.append(dict(signal_month=month, n_F=len(g), n_size=len(valid), rho=rho,
                         reason='ok' if np.isfinite(rho) else 'insufficient_or_degenerate'))
    csv(pd.DataFrame(diag), 'size_correlation')
    latest = f[f.signal_month.eq('2026-01')]
    industry = latest.groupby(['industry_code', 'industry_label'], dropna=False).agg(bp_median=('bp', 'median'), n=('bp', 'size')).reset_index()
    assert len(industry) == 31
    csv(industry.sort_values('bp_median', ascending=False), 'industry_median_20260130')

    # Construct response table only after keeping formation data separate.
    s = panel[panel.S & panel.holding_complete].copy()
    responses = s[['signal_month', 'ts_code']].assign(ret_fwd=s.exit_adjusted_value / s.entry_adjusted_value - 1)
    assert np.isfinite(responses.ret_fwd).all()
    assert not responses.duplicated(['signal_month', 'ts_code']).any()
    results, c1, c2 = {}, [], []
    all_formed = all_status = None
    for pool, mask in [('ALL_A', pd.Series(True, index=s.index)), ('HS300', s.in_000300), ('ZZ500', s.in_000905)]:
        print('Forming and evaluating', pool, flush=True)
        formed, status = bp.form_pool(s[mask], cal)
        formations = pd.concat([g.assign(signal_month=m) for m, g in formed.items()], ignore_index=True)
        formations.to_parquet(private / (pool + '_formations.parquet'), index=False)
        res = bp.evaluate_layers(formed, status, responses, cal)
        assert all(v == 'ok' for v in status.values()), status
        assert res['reasons'].empty, res['reasons'].to_dict('records')
        assert np.isfinite(res['layers_net']).all().all()
        assert res['n_formed'].equals(res['n_response'])
        save_result(res, pool)
        results[pool] = res
        c1.append(dict(pool=pool, **bp.c1_row(res)))
        layer = bp.layer_statistics(res)
        ls = bp.performance(res['long_short'])
        c2.append(dict(pool=pool, **{f'Q{q}_ann': layer.loc[q, 'ann'] for q in layer.index},
                       long_short_ann=ls['ann'], long_short_sharpe=ls['sharpe'], long_short_max_dd=ls['max_dd'],
                       long_short_win_rate=ls['win_rate'], long_short_positive=int(res['long_short'].gt(0).sum()),
                       n_months=len(cal), q5_ann_exc=layer.loc[5, 'ann_exc'],
                       adjacent_order=int((np.diff(layer.ann) > 0).sum()),
                       layer_rank_rho=spearmanr(layer.index, layer.ann).statistic))
        if pool == 'ALL_A':
            all_formed, all_status = formed, status
    csv(pd.DataFrame(c1), 'C1')
    csv(pd.DataFrame(c2), 'C2')
    csv(bp.annual_table(results['ALL_A']), 'C3')
    csv(bp.rolling_excess(results['ALL_A']), 'D6_rolling_excess', True)

    indices = pd.read_parquet(index_path)
    indices['trade_date'] = indices.trade_date.astype(str)
    index_rows = []
    for code in ['000300.SH', '000905.SH']:
        prices = indices[indices.ts_code.eq(code)].set_index('trade_date').close
        for row in cal.itertuples():
            entry, exit_value = prices.loc[row.entry_date], prices.loc[row.exit_date]
            assert np.isfinite(entry) and np.isfinite(exit_value) and entry > 0 and exit_value > 0
            index_rows.append(dict(index_code=code, holding_month=row.holding_month,
                                   entry_date=row.entry_date, exit_date=row.exit_date,
                                   entry_close=entry, exit_close=exit_value, ret=exit_value / entry - 1))
    csv(pd.DataFrame(index_rows), 'index_returns')

    print('Evaluating ten layers and size domains', flush=True)
    ten = bp.evaluate_layers(all_formed, all_status, responses, cal, n_layer=10, min_unique=10, regress=False)
    assert ten['reasons'].empty
    save_result(ten, 'D9')
    size_groups, size_counts = {i: {} for i in [1, 2, 3]}, []
    for m, g in all_formed.items():
        ordered = g.sort_values('ts_code')
        bucket = pd.qcut(ordered.circ_mv.rank(method='first'), 3, labels=False) + 1
        for i in size_groups:
            domain = ordered[bucket.eq(i)]
            size_groups[i][m] = domain
            size_counts.append(dict(signal_month=m, size_bucket=i, n=len(domain), bp_valid=len(domain),
                                    bp_coverage_within_frozen_S=1.0, formation_S=len(g),
                                    circ_mv_min=domain.circ_mv.min(), circ_mv_max=domain.circ_mv.max()))
    csv(pd.DataFrame(size_counts), 'D10_size_domains')
    for i, formed in size_groups.items():
        res = bp.evaluate_layers(formed, all_status, responses, cal, n_layer=10, min_unique=10, regress=False)
        assert res['reasons'].empty
        save_result(res, f'D10_size{i}')

    print('Evaluating industry five-layer comparisons', flush=True)
    c4_cal = cal[cal.signal_month.ge('2021-07')].reset_index(drop=True)
    coverage = pd.read_csv(ROOT / 'outputs/preflight_repaired/industry_comparison_coverage.csv', dtype={'industry_code': str})
    c4 = []
    for industry in coverage.itertuples():
        formed = {m: g[g.industry_code.eq(industry.industry_code)] for m, g in all_formed.items() if m in set(c4_cal.signal_month)}
        res = bp.evaluate_layers(formed, all_status, responses, c4_cal, min_stocks=25, min_unique=5, regress=False)
        save_result(res, 'C4_' + industry.industry_code)
        eligible = bool(industry.common_window_eligible)
        if eligible:
            assert res['reasons'].empty
        layer = bp.layer_statistics(res)
        q5 = layer.loc[5]
        c4.append(dict(industry_code=industry.industry_code, industry_label=industry.industry_label,
                       status='complete' if eligible else 'insufficient_common_window',
                       n_months=int(res['benchmark'].notna().sum()), expected_months=54,
                       min_n=industry.min_S, ann_exc=q5.ann_exc, sharpe=q5.sharpe, ir=q5.ir,
                       excess_max_dd=q5.excess_max_dd, relative_win_rate=q5.relative_win_rate,
                       q5_rank=int(layer.ann.rank(ascending=False).loc[5]) if eligible else np.nan,
                       layer_order='>'.join('Q'+str(q) for q in layer.ann.sort_values(ascending=False).index) if eligible else '',
                       layer_rank_rho=spearmanr(layer.index, layer.ann).statistic if eligible else np.nan,
                       **{f'Q{q}_ann': layer.loc[q, 'ann'] for q in layer.index}))
    csv(pd.DataFrame(c4).sort_values('ann_exc', ascending=False, na_position='last'), 'C4')
    config.update(status='complete', finished_at=datetime.now().isoformat(), n_main_months=len(cal),
                  n_signal_diagnostic_months=len(cal_all), n_main_stock_periods=len(s),
                  first_entry=cal.entry_date.iloc[0], last_exit=cal.exit_date.iloc[-1],
                  main_pool_valid_months={p: int(r['long_short'].notna().sum()) for p, r in results.items()},
                  c4_complete_industries=sum(x['status'] == 'complete' for x in c4),
                  issues=['C4 industry 510000 insufficient in common window; no ranked performance'],
                  output_files=sorted(p.name for p in out.glob('*.csv')))
    write_config()
    print(json.dumps({k: config[k] for k in ['run_id', 'status', 'main_pool_valid_months', 'c4_complete_industries']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
