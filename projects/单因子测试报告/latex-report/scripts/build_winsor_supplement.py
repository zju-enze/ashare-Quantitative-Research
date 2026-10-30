"""Generate only S1 and the scoped paragraph from the completed sensitivity run."""
from pathlib import Path
import argparse
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    out, latex = ROOT / 'outputs/runs' / args.run_id, ROOT / 'latex-report'
    for name in ['mad5_baseline_check.json', 'numerical_audit.json']:
        assert json.loads((out / name).read_text(encoding='utf-8'))['status'] == 'passed'
    s = pd.read_csv(out / 'summary.csv', float_precision='round_trip').set_index('scheme')
    order = ['mad-k5', 'mad-k3', 'quantile-p01-p99-linear']
    assert s.index.tolist() == order
    assert s.n_months.eq(228).all() and s.rank_ic_mean.gt(0).all() and s.factor_ret_mean.gt(0).all()
    assert s.adjacent_order.eq(4).all()
    numeric = s.select_dtypes(include='number')
    d = numeric.sub(numeric.loc[order[0]])
    assert d.loc['mad-k3', 'ls_gross_arithmetic_ann'] < 0 < d.loc['mad-k3', 'ls_cost_arithmetic_ann']
    assert -d.loc['mad-k3', 'ls_gross_arithmetic_ann'] > d.loc['mad-k3', 'ls_cost_arithmetic_ann']
    signed = lambda value: f'{100 * value:+.2f}'.replace('-', '−')
    p = (
        '本次补充完成前述后续工作中的去极值敏感性分析，比较MAD5、MAD3与1%/99%分位数缩尾；IC衰减与样本外检验仍留待后续。'
        f'表S1中，三种方案的平均回归因子收益均为正（{s.factor_ret_mean.min()*100:.2f}%至{s.factor_ret_mean.max()*100:.2f}%/月），'
        f'平均Rank IC为{s.rank_ic_mean.min():.4f}至{s.rank_ic_mean.max():.4f}，方向一致；ICIR为{s.ic_ir.min():.3f}至{s.ic_ir.max():.3f}。'
        f'相对MAD5，MAD3与分位数方案的多空年化净收益分别变化{signed(d.loc[order[1], "long_short_ann"])}、{signed(d.loc[order[2], "long_short_ann"])}个百分点，'
        f'Q5算术年化超额分别变化{signed(d.loc[order[1], "q5_ann_exc"])}、{signed(d.loc[order[2], "q5_ann_exc"])}个百分点。'
        '三种方案五层年化净收益均随层号递增。'
        f'按可加总的算术年化口径，MAD3毛多空下降{-100*d.loc[order[1], "ls_gross_arithmetic_ann"]:.2f}个百分点，'
        f'双腿成本增加{100*d.loc[order[1], "ls_cost_arithmetic_ann"]:.2f}个百分点，净收益下降主要来自毛收益变化。'
        '由此，原结论的正向关联与分层单调性得到支持，但收益幅度仍依赖去极值选择，不能称为完全稳健。'
        '未进行方案差异的统计检验，也不据表现改选默认MAD5；以上仅适用于本次全部A股样本及这三种方案。'
    )
    assert 300 <= len(p) <= 450, len(p)
    rows = []
    values = []
    for name, row in s.iterrows():
        cells = [row.label, f'{row.rank_ic_mean:.4f}', f'{row.ic_ir:.3f}',
                 f'{100*row.factor_ret_mean:.2f}', f'{100*row.long_short_ann:.2f}', f'{100*row.q5_ann_exc:.2f}']
        values.append(dict(scheme=name, displayed=cells))
        rows.append(' & '.join(x.replace('%', r'\%') for x in cells) + r' \\')
    table = r'''\begingroup\small\setlength{\tabcolsep}{3pt}
\begin{table}[H]\centering
\caption*{\textbf{表S1　去极值方法敏感性}}
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrr@{}}\toprule
去极值方案 & \makecell{Rank IC\\均值} & ICIR & \makecell{回归因子收益\\均值（\%/月）} & \makecell{多空年化\\净收益（\%）} & \makecell{Q5算术年化超额\\（百分点）} \\ \midrule
''' + '\n'.join(rows) + r'''
\bottomrule\end{tabular*}
\par\smallskip\raggedright\footnotesize 全部 A 股，228期；仅改变去极值方法，其余设定及输入S样本不变。ICIR未年化；多空为扣除双腿成本后的CAGR；Q5超额为相对原内部等权毛收益基准的算术年化超额。分位点采用线性插值。差值按未舍入结果计算。
\end{table}
\endgroup
'''
    (latex / 'tables/S1.tex').write_text(table, encoding='utf-8')
    body = '\\Needspace{85mm}\n\\subsection*{去极值方法敏感性}\n\\input{tables/S1}\n'
    body += p.replace('%', r'\%').replace('−', '$-$') + '\n'
    (latex / 'sections/05_winsor_sensitivity.tex').write_text(body, encoding='utf-8')
    shutil.copy2(out / 'summary.csv', latex / 'source-data/winsor_sensitivity_summary.csv')
    (out / 'supplement_paragraph.txt').write_text(p + '\n', encoding='utf-8')
    record = dict(run_id=args.run_id, source='summary.csv', table_rows=values, paragraph_characters=len(p),
                  paragraph=p, positive_direction=True, all_three_layer_orders='Q1<Q2<Q3<Q4<Q5',
                  delta_source='difference_vs_mad5.csv', cost_decomposition='arithmetic annualization, not CAGR subtraction')
    (out / 'report_values.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Generated only S1 and sensitivity paragraph ({len(p)} characters).')


if __name__ == '__main__':
    main()
