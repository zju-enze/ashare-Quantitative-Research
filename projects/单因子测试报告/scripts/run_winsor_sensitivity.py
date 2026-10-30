"""ALL_A only: reproduce MAD5, then vary winsorization on the same frozen S."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import json
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'bp-v05-20261026-main'
SCHEMES = [
    dict(id='mad-k5', method='mad5', label='MAD5', k=5, scale=1),
    dict(id='mad-k3', method='mad3', label='MAD3', k=3, scale=1),
    dict(id='quantile-p01-p99-linear', method='quantile_01_99',
         label='1%/99%分位数缩尾', lower=.01, upper=.99, interpolation='linear'),
]
FORMATION = ['signal_month', 'ts_code', 'pb', 'total_mv', 'circ_mv', 'industry_code']
MONTHLY = ['factor_ret', 't', 'ic', 'benchmark', 'long_short', 'n_formed', 'n_response']
RTOL, ATOL = 1e-7, 1e-13


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def compare_frames(actual, expected, name, exact=False):
    """Keys/counts are exact; floating results use the existing arithmetic tolerance."""
    actual, expected = actual.reset_index(drop=True), expected.reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False,
                                  check_exact=exact, rtol=RTOL, atol=ATOL)
    numeric = expected.select_dtypes(include=np.number).columns
    delta = (actual[numeric] - expected[numeric]).abs().to_numpy()
    finite = delta[np.isfinite(delta)]
    return dict(check=name, status='passed', rows=len(actual), exact=exact,
                max_abs_difference=float(finite.max()) if finite.size else 0.)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--course-root', type=Path)
    args = parser.parse_args()
    course_root = args.course_root or Path(json.loads(
        (ROOT / '.local/paths.json').read_text(encoding='utf-8-sig'))['course_root'])
    sys.path[:0] = [str(ROOT / 'src'), str(course_root)]
    import bp_core as bp

    out, private = ROOT / 'outputs/runs' / args.run_id, ROOT / '.local/runs' / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    base, base_private = ROOT / 'outputs/runs' / BASELINE, ROOT / '.local/runs' / BASELINE
    panel_path = ROOT / '.local/preflight_repaired/candidate_panel.parquet'
    old_manifest = json.loads((base / 'run_manifest.json').read_text(encoding='utf-8'))
    source_version = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = dict(run_id=args.run_id, baseline_run=BASELINE, method_version='0.5 + winsor sensitivity',
                    started_at=now(), status='running', source_version=source_version,
                    source_changes=['src/bp_core.py', 'scripts/run_winsor_sensitivity.py'],
                    pool='ALL_A', active_change='winsorization only', schemes=SCHEMES,
                    cost_rt=.004, main_layers=5, min_stocks=50, min_distinct_bp=20,
                    zscore_ddof=0, wls_objective_weight='sqrt(circ_mv)', rf=0, time_std_ddof=1,
                    ic_ir_annualized=False, numerical_tolerance=dict(rtol=RTOL, atol=ATOL),
                    inputs=[dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size,
                                 mtime_ns=p.stat().st_mtime_ns)
                            for p in [panel_path, base / 'calendar.csv',
                                      base_private / 'ALL_A_formations.parquet',
                                      base_private / 'ALL_A_holdings.parquet']],
                    qfbook_source=str(bp.course.__file__), python=sys.executable)

    def write_json(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def csv(frame, path, index=False):
        frame.to_csv(path, index=index, encoding='utf-8-sig')

    def read_csv(path):
        return pd.read_csv(path, float_precision='round_trip')

    write_json(out / 'run_manifest.json', manifest)
    try:
        prior_panel = next(x for x in old_manifest['inputs'] if x['name'] == 'accepted_panel')
        assert (panel_path.stat().st_size, panel_path.stat().st_mtime_ns) == (
            prior_panel['bytes'], prior_panel['mtime_ns']), 'Accepted panel version differs from baseline'
        panel = pd.read_parquet(panel_path)
        cal = pd.read_csv(base / 'calendar.csv', dtype={'signal_date': str, 'entry_date': str, 'exit_date': str})
        assert len(cal) == 228 and cal.signal_month.tolist() == pd.period_range('2007-01', '2025-12', freq='M').astype(str).tolist()
        assert cal.holding_month.tolist() == pd.period_range('2007-02', '2026-01', freq='M').astype(str).tolist()
        csv(cal, out / 'calendar.csv')
        s = panel.loc[panel.S & panel.holding_complete].copy()
        inputs = s[FORMATION].copy()
        assert not inputs.duplicated(['signal_month', 'ts_code']).any()
        assert inputs.pb.gt(0).all() and np.isfinite(inputs[['pb', 'total_mv', 'circ_mv']]).all().all()
        assert inputs.total_mv.gt(0).all() and inputs.circ_mv.gt(0).all() and inputs.industry_code.notna().all()
        old_formed = pd.read_parquet(base_private / 'ALL_A_formations.parquet')
        keys = ['signal_month', 'ts_code']
        baseline_checks = [compare_frames(inputs.sort_values(keys), old_formed[FORMATION].sort_values(keys),
                                           'pre_winsor_stock_periods_and_controls', exact=True)]
        date_columns = ['signal_date', 'entry_date', 'exit_date', 'holding_month']
        dates = s[['signal_month'] + date_columns].drop_duplicates().sort_values('signal_month')
        baseline_checks.append(compare_frames(dates, cal[['signal_month'] + date_columns], 'original_dates', exact=True))
        summaries, accepted = [], []
        baseline_monthly = baseline_diagnostics = None
        for scheme in SCHEMES:
            scheme_id = scheme['id']
            print(f"Forming {scheme_id}: {len(inputs):,} stock-periods", flush=True)
            target, detail = out / scheme_id, private / scheme_id
            target.mkdir()
            detail.mkdir()
            write_json(target / 'config.json', dict(**scheme, run_id=args.run_id, pool='ALL_A'))
            formed, status = bp.form_pool(inputs, cal, winsor=scheme['method'])
            failures = [dict(signal_month=m, scheme=scheme_id, reason=v) for m, v in status.items() if v != 'ok']
            csv(pd.DataFrame(failures, columns=['signal_month', 'scheme', 'reason']), target / 'formation_issues.csv')
            assert not failures, failures
            formations = pd.concat([g.assign(signal_month=m) for m, g in formed.items()], ignore_index=True)
            compare_frames(formations[FORMATION].sort_values(keys), inputs.sort_values(keys), 'same_S', exact=True)
            if scheme['method'] == 'mad5':
                baseline_checks.append(compare_frames(formations[old_formed.columns], old_formed, 'all_formation_values'))
            formations['residual_rank'] = formations.groupby('signal_month').f_neu.rank(method='first')
            formations.to_parquet(detail / 'formations.parquet', index=False)
            diagnostics = []
            for month, g in formed.items():
                med = g.bp.median()
                mad = (g.bp - med).abs().median()
                lower, upper = (g.bp.quantile([.01, .99], interpolation='linear') if scheme['method'] == 'quantile_01_99'
                                else (med - scheme['k'] * mad, med + scheme['k'] * mad))
                changed = g.bp_w.ne(g.bp)
                diagnostics.append(dict(signal_month=month, n=len(g), median=med, mad=mad, lower=lower, upper=upper,
                                        n_below=int(g.bp.lt(lower).sum()), n_above=int(g.bp.gt(upper).sum()),
                                        n_changed=int(changed.sum()), changed_fraction=changed.mean(),
                                        winsor_distinct=g.bp_w.nunique(), residual_distinct=g.f_neu.nunique(),
                                        negative_residuals=int(g.f_neu.lt(0).sum())))
            diagnostics = pd.DataFrame(diagnostics)
            csv(diagnostics, target / 'winsor_diagnostics.csv')

            # evaluate_layers freezes each month's ranks/holdings before joining these responses.
            responses = s[['signal_month', 'ts_code']].assign(
                ret_fwd=s.exit_adjusted_value / s.entry_adjusted_value - 1)
            assert np.isfinite(responses.ret_fwd).all()
            if scheme['method'] == 'mad5':
                response_detail = s[keys + date_columns + ['entry_adjusted_value', 'exit_adjusted_value', 'exit_value_kind']].copy()
                response_detail['ret_fwd'] = responses.ret_fwd
                response_detail.to_parquet(private / 'responses.parquet', index=False)
            res = bp.evaluate_layers(formed, status, responses, cal)
            csv(res['reasons'], target / 'issues.csv')
            assert res['reasons'].empty, res['reasons'].to_dict('records')
            assert res['n_formed'].equals(res['n_response']) and np.isfinite(res['layers_net']).all().all()
            assert res['ic'].notna().sum() == res['factor_ret'].notna().sum() == len(cal)
            monthly = pd.DataFrame({k: res[k] for k in MONTHLY})
            cost = .004 * res['turnover']
            monthly['long_short_gross'] = res['layers_gross'][5] - res['layers_gross'][1]
            monthly['long_short_cost'] = cost[5] + cost[1]
            monthly['q5_excess'] = res['layers_net'][5] - res['benchmark']
            np.testing.assert_allclose(res['long_short'], monthly.long_short_gross - monthly.long_short_cost, rtol=RTOL, atol=ATOL)
            csv(monthly, target / 'monthly.csv', True)
            for key in ['layers_gross', 'layers_net', 'turnover', 'counts', 'known_weight']:
                csv(res[key], target / (key + '.csv'), True)
            csv(cost, target / 'costs.csv', True)
            holdings = res['holdings'].copy()
            holdings['weight'] = 1 / holdings.groupby(['signal_month', 'layer']).ts_code.transform('size')
            holdings.to_parquet(detail / 'holdings.parquet', index=False)
            c1, layer, ls = bp.c1_row(res), bp.layer_statistics(res), bp.performance(res['long_short'])
            csv(layer, target / 'layer_stats.csv', True)
            c2 = dict(**{f'Q{q}_ann': layer.loc[q, 'ann'] for q in layer.index}, long_short_ann=ls['ann'],
                      long_short_sharpe=ls['sharpe'], long_short_max_dd=ls['max_dd'],
                      long_short_win_rate=ls['win_rate'], long_short_positive=int(res['long_short'].gt(0).sum()),
                      n_months=len(cal), q5_ann_exc=layer.loc[5, 'ann_exc'],
                      adjacent_order=int((np.diff(layer.ann) > 0).sum()), layer_rank_rho=spearmanr(layer.index, layer.ann).statistic)
            summary = dict(scheme=scheme_id, label=scheme['label'], **c1, **c2,
                           n_stock_periods=len(inputs), mean_modified_fraction=diagnostics.changed_fraction.mean(),
                           n_modified=int(diagnostics.n_changed.sum()),
                           q1_mean_turnover=res['turnover'][1].mean(), q5_mean_turnover=res['turnover'][5].mean(),
                           ls_gross_arithmetic_ann=12 * monthly.long_short_gross.mean(),
                           ls_cost_arithmetic_ann=12 * monthly.long_short_cost.mean(),
                           ls_net_arithmetic_ann=12 * res['long_short'].mean())
            csv(pd.DataFrame([summary]), target / 'summary.csv')
            if scheme['method'] == 'mad5':
                baseline_checks.append(compare_frames(res['holdings'], pd.read_parquet(base_private / 'ALL_A_holdings.parquet'), 'all_holdings', exact=True))
                for key in ['monthly', 'layers_gross', 'layers_net', 'turnover', 'counts', 'known_weight', 'layer_stats', 'issues']:
                    expected = read_csv(base / ('ALL_A_' + key + '.csv'))
                    actual = read_csv(target / (key + '.csv'))[expected.columns]
                    baseline_checks.append(compare_frames(actual, expected, key, exact=key in ['counts', 'known_weight', 'issues']))
                for name, row in [('C1', c1), ('C2', c2)]:
                    expected = read_csv(base / (name + '.csv')).query("pool == 'ALL_A'").drop(columns='pool')
                    baseline_checks.append(compare_frames(pd.DataFrame([row])[expected.columns], expected, name))
                write_json(out / 'mad5_baseline_check.json', dict(status='passed', baseline_run=BASELINE,
                           tolerance=dict(rtol=RTOL, atol=ATOL), checks=baseline_checks))
                print('MAD5 baseline passed: original dates, inputs, all holdings, monthly series and summaries.', flush=True)
                baseline_monthly, baseline_diagnostics = monthly.copy(), diagnostics.copy()
            else:
                np.testing.assert_array_equal(monthly.index, baseline_monthly.index)
                np.testing.assert_array_equal(monthly.n_formed, baseline_monthly.n_formed)
                np.testing.assert_array_equal(monthly.benchmark, baseline_monthly.benchmark)
            csv(monthly - baseline_monthly, target / 'monthly_difference_vs_mad5.csv', True)
            csv(diagnostics.select_dtypes(include=np.number).sub(baseline_diagnostics.select_dtypes(include=np.number)).assign(
                signal_month=diagnostics.signal_month), target / 'winsor_difference_vs_mad5.csv')
            summaries.append(summary)
            accepted.append(dict(scheme=scheme_id, status='passed', months=len(cal), stock_periods=len(inputs),
                                 formation_issues=0, evaluation_issues=0, same_S=True, same_benchmark=True,
                                 formation_and_holdings_recomputed=True, double_leg_cost_identity=True))
            print(f"Completed {scheme_id}", flush=True)
        summary = pd.DataFrame(summaries)
        csv(summary, out / 'summary.csv')
        numeric = summary.select_dtypes(include=np.number).columns
        csv(summary[numeric].sub(summary.loc[0, numeric], axis='columns').assign(scheme=summary.scheme), out / 'difference_vs_mad5.csv')
        write_json(out / 'acceptance_results.json', dict(status='passed', checks=accepted,
                   scope='Same frozen ALL_A inputs, 228 months, separate preprocessing and holdings; no new inference.'))
        manifest.update(status='complete', finished_at=now(), n_months=len(cal), n_stock_periods=len(inputs),
                        first_signal=cal.signal_date.iloc[0], last_signal=cal.signal_date.iloc[-1],
                        first_entry=cal.entry_date.iloc[0], last_exit=cal.exit_date.iloc[-1])
    except Exception as exc:
        manifest.update(status='failed', finished_at=now(), failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write_json(out / 'run_manifest.json', manifest)


if __name__ == '__main__':
    main()
