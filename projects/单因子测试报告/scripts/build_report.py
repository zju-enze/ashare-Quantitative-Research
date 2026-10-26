"""Render the Chinese course report from the locked v0.5 result tables.

Narrative is specific to this study; changing the study requires reviewing it.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
POOL = {'ALL_A': '全部 A 股', 'HS300': '沪深300', 'ZZ500': '中证500'}


def pct(x):
    return '—' if pd.isna(x) else f'{x:.2%}'


def number(x, digits=3):
    return '—' if pd.isna(x) else f'{x:.{digits}f}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    run = ROOT / 'outputs/runs' / args.run_id
    manifest = json.loads((run / 'run_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'complete' and manifest['n_main_months'] == 228
    out = ROOT / 'report'
    out.mkdir(exist_ok=True)
    def read(name, index=None):
        return pd.read_csv(run / (name + '.csv'), index_col=index)
    c1, c2, c3, c4 = [read(n) for n in ['C1', 'C2', 'C3', 'C4']]
    m, net, gross, to, stats = [read('ALL_A_' + n, 0) for n in ['monthly', 'layers_net', 'layers_gross', 'turnover', 'layer_stats']]
    size, industry, flow = [read(n) for n in ['size_correlation', 'industry_median_20260130', 'D1_sample_flow']]
    f = flow[flow.pool.eq('ALL_A')]
    rolling = read('D6_rolling_excess', 0)
    ten = read('D9_layer_stats', 0)
    domains = [read(f'D10_size{i}_layer_stats', 0) for i in [1, 2, 3]]
    claims, chunks = [], []
    def claim(identifier, text, artifact, locator, scope='冻结方法v0.5下的历史描述性结果'):
        claims.append(dict(claim_id=identifier, claim_text=text, evidence_type='本次结果', run_id=args.run_id,
                           method_version='0.5', artifact=artifact, locator=locator, scope=scope,
                           support_status='已支持', action='保留'))
        return text
    def figure(name, caption):
        assert (run / 'figures' / (name + '.png')).exists()
        return f'![{caption}](../outputs/runs/{args.run_id}/figures/{name}.png)\n\n*{caption}。底层数据与矢量图见同一运行目录。*'
    def add(text):
        chunks.append(text.strip())
    a, h, z = [c1[c1.pool.eq(pool)].iloc[0] for pool in ['ALL_A', 'HS300', 'ZZ500']]
    ca = c2[c2.pool.eq('ALL_A')].iloc[0]
    assert ca.adjacent_order == 4 and c2[c2.pool.eq('HS300')].iloc[0].adjacent_order == 3
    assert c3.set_index('year').loc[2025, 'long_excess'] < 0

    add('''## 1. 研究背景与因子定义

单因子测试先回答一个有限问题：同一期股票之间的因子差异，能否对应下一持有期的收益差异。本文按课程附录，以回归、Rank IC和分层三条证据评价BP，并进一步检查不同股票池、年份、行业和市值域。目标是判断BP是否值得进入后续多因子研究，不构造完整交易系统，也不把本次回测解释为可直接执行的投资方案。

账面市值比（Book-to-Price，BP）衡量账面净资产相对市场价格的水平。高BP可能反映较低估值；其后收益较高可能与风险补偿或错误定价有关。但资产减值、盈利能力差异和持续经营风险也可能形成“价值陷阱”。这些是待检验解释，本报告的观察性设计不能区分因果机制。

| 项目 | 本报告定义 |
| --- | --- |
| 经济概念与实际变量 | 经济概念为账面权益/总市值；实际采用供应商历史日度 `pb` 的倒数 |
| 公式与单位 | `BP = 1 / pb`，无量纲比值；只取正且有限的PB |
| 来源与口径边界 | 课程离线Tushare历史估值字段；供应商定义及有限财务样本已核对，未自行重建逐版本财报PIT数据库 |
| 频率与方向 | 交易月末收盘后取值；预先假设高BP对应较高下期收益，Q5始终为高残差层 |
| 无效值 | 缺失、零、负、无穷PB均不填补；这是因子定义域限制，不称为去极值 |
| 规模变量 | 中性化和WLS控制使用总市值；WLS权重、市值三分域使用流通市值；源单位为万元 |

这一口径依赖供应商历史PB的财务定义和修订规则，不能无条件等同于当时投资者可取得的原始披露版本。全文统一使用“全部 A 股”“内部等权基准”“年化净收益”“算术年化超额”和“Rank IC”，避免把不同收益口径混称为alpha。''')

    add('''## 2. 数据范围与形成时点

三池共同信号期为2007-01至2025-12，共228期；实际建仓从2007-02-01收盘开始，最后退出为2026-02-02收盘。持有期归属2007-02至2026-01。另保留2026-01-30这一最新完整信号截面作诊断，其未来退出日超出行情截止，未进入绩效。

全部 A 股沿用课程沪深京人民币权益证券覆盖，含库内境内上市CDR；北交所从2021-11-15开市后纳入。股票池使用历史生命周期、历史指数成员、历史行业和历史ST/PT状态。入场按下一交易日收盘可交易判断，日内临停但收盘恢复者可保留。沪深300和中证500均使用历史真实成员，没有以当前名单或市值排名替代。

样本依次为U（历史合格池）、F（U中正有限PB）、S（F中行业与市值控制变量可用）、Y（S的后续收益可评价）。去极值、中性化和持仓在S上冻结，之后才接入收益。三池分别预处理，未来收益可得性不参与分层。

完整主窗口全A包含686,280个股票—期。原始8,011个退出端点不足中，7,936项按停牌及公司行为估值，58项依据事先公告在最后实际交易日退出并持有零利息现金，17项按合并对价估值；其中两项承接A股尚未上市，按已确认政策延续最后旧股估值对应的换股权利。所有处理保留原样本和计划持有期，剩余未解决端点为0。它们是研究估值近似，不保证真实卖出可成交。

行业历史使用生效事件匹配，保留旧分类，不把现行分类倒填早期。229个诊断月合计87个F股票—期缺行业，依预先声明的控制变量规则从S排除；没有用未来收益筛除。有限流通市值异常已根据公司股本事件修正，但未宣称完成全市场财报、股本或行业版本的严格PIT重建。''')

    add('## 3. 截面诊断\n\n### 3.1 行业分布\n\n'+figure('industry_median', '图A：2026-01-30原始BP行业中位数'))
    top, bottom = industry.iloc[0], industry.iloc[-1]
    add(claim('A', f'最新截面共{int(industry.n.sum())}只F股票、31个一级行业。{top.industry_label}BP中位数为{top.bp_median:.3f}，{bottom.industry_label}为{bottom.bp_median:.3f}，前者约为后者的{top.bp_median/bottom.bp_median:.1f}倍。房地产和煤炭也处于较高区间。这种行业差异支持在比较股票之前控制行业；不能把银行高BP本身解释为银行股票具有更高预测收益。综合行业在本截面仅15只，仍展示中位数，但不据此认定其行业分层可靠。', 'industry_median_20260130.csv', '31行业中位数与n'))
    add('### 3.2 与规模的关系\n\n'+figure('size_correlation', '图B：原始BP与对数总市值逐月Spearman相关'))
    add(claim('B', f'229/229个信号截面均可计算，相关系数均值为{size.rho.mean():.4f}；与均值同为负号的月份为{int(size.rho.lt(0).sum())}/229（{pct(size.rho.lt(0).mean())}），正号为{int(size.rho.gt(0).sum())}/229。均值较小并不表示每月都与规模无关，图中方向曾发生反转。因此保留逐期规模控制，且不把中性化后的低相关倒写为原始BP无规模关联。', 'size_correlation.csv', 'rho均值、正负月份数量'))
    add('### 3.3 覆盖度\n\n'+figure('D1', 'D1：全A合格池、因子样本与覆盖度'))
    last = f.iloc[-1]
    reasons = f[['valuation_row_missing', 'pb_missing', 'pb_nonfinite', 'pb_zero', 'pb_negative']].sum()
    add(claim('D1', f'全A各月F/U介于{pct(f.bp_coverage_f_over_u.min())}与{pct(f.bp_coverage_f_over_u.max())}。最新截面U={int(last.U):,}、F=S={int(last.F):,}，覆盖度为{pct(last.bp_coverage_f_over_u)}。229期累计U与F之差为{int(f.U.sum()-f.F.sum()):,}个股票—期，其中估值整行缺失{int(reasons.valuation_row_missing):,}、PB字段缺失{int(reasons.pb_missing):,}、非有限{int(reasons.pb_nonfinite):,}、零值{int(reasons.pb_zero):,}、负值{int(reasons.pb_negative):,}。缺失不能统一解释为负净资产；ST/PT和入场不合格已在U之前过滤，不进入覆盖率分母。覆盖度较高仅支持数据可用性，不等于预测有效性。', 'D1_sample_flow.csv', 'ALL_A U/F/S及BP缺失分类'))

    add('''## 4. 方法与默认参数

每个交易月末生成信号，下一交易日收盘建仓，持有到下一月末后的首个交易日收盘。个股收益为同一原始代码尺度的“退出复权估值/入场复权估值−1”；端点估值规则见第2节。回归、IC、分层与指数共享日期表。

1. **预处理。** 在各池S中对原始BP作中位数±5×MAD截尾，MAD为绝对离差的中位数。回归暴露再作Z-score（截面标准差ddof=0）。IC与分层使用截尾BP对截距、对数总市值及行业哑变量作OLS后的残差；负残差仍有效。
2. **WLS与IC。** 下期个股收益对标准化BP、对数总市值及行业回归；目标函数权重为流通市值平方根，拟合矩阵相应再乘权重平方根。Rank IC是冻结残差与下期收益的Spearman相关。截面t采用课程常规WLS残差方差，不是稳健标准误；表中t均值不代表因子收益时间序列均值的t检验。
3. **分层与费用。** 按残差从低到高等人数五分层，层内等权；并列时按证券代码稳定排序。教材只数换手为`1−本期与上期持仓交集数/本期只数`，首期为1。各层净收益=毛收益−0.004×换手。多空=Q5毛收益−Q1毛收益−两腿各自成本，不能相减两条净收益。该近似忽略权重漂移、完整再平衡及借券融资，不额外模拟交易撮合。
4. **基准。** 内部基准为当期全部实际分层S的个股等权毛收益，不另扣换手成本；不是五层收益的简单平均。外部沪深300与中证500采用相同端点的价格指数，不含分红。个股复权收益与价格指数并非完全同口径，主要选股比较使用内部基准。
5. **统计。** 连续完整月频净收益的CAGR=`prod(1+r)^(12/n)−1`；夏普=`sqrt(12)×mean(r)/sd(r)`，RF=0；算术年化超额=`12×mean(层净收益−基准毛收益)`；IR将同一月超额均值除以其标准差再乘`sqrt(12)`。时间序列标准差ddof=1，ICIR不年化。最大回撤含期初净值1，以非正数表示；超额回撤用层净值/基准净值计算。
6. **扩展与缺期。** D9在同一全A样本与残差上改十层。C4在行业内五层，D10每月先按流通市值三等分，再在域内按同一全A残差十分层，均不重新中性化。C4每期至少25只，D10每域至少50只，并检查不同因子取值数。无法形成或评价的月份保留为空，不拼接年化、不补零。C4共同窗口在看收益前冻结为2021-07至2025-12信号月；综合行业不足，保留空结果。

主设定在首次绩效计算前已冻结。以下分段解读按持有期归属月使用2007-02—2013-12、2014-01—2020-12、2021-01—2026-01三个连续日历块，目的为描述变化，不构成额外显著性检验或重新择窗。''')

    add('## 5. 三池主结果\n\n### 5.1 C1：回归与Rank IC')
    add(table(['股票池', '绝对t均值', '绝对t>2（月数/228）', '占比', 't均值', '因子收益均值/月'],
              [[POOL[r.pool], number(r.t_abs_mean), f'{r.t_abs_gt2}/228', pct(r.t_abs_gt2_rate), number(r.t_mean), pct(r.factor_ret_mean)] for r in c1.itertuples()]))
    add(claim('C1_reg', f'三池的平均回归系数均为正。全A绝对t均值{a.t_abs_mean:.3f}、绝对t>2共{int(a.t_abs_gt2)}/228期，但t均值仅{a.t_mean:.3f}；沪深300、中证500的t均值分别为{h.t_mean:.3f}和{z.t_mean:.3f}。绝对t反映偏离零的强度，包含负向月份，不能替代正向稳定性。这些是逐截面统计的描述，不能据此宣布时间序列均值通过了稳健显著性检验。', 'C1.csv', '回归字段，三池各228期'))
    add(table(['股票池', 'Rank IC均值', '标准差', 'ICIR（未年化）', 'IC>0（月数/228）', '占比'],
              [[POOL[r.pool], number(r.rank_ic_mean, 4), number(r.rank_ic_sd, 4), number(r.ic_ir), f'{r.ic_positive}/228', pct(r.ic_positive_rate)] for r in c1.itertuples()]))
    add(claim('C1_ic', f'全A平均Rank IC为{a.rank_ic_mean:.4f}，正向月份{int(a.ic_positive)}/228；沪深300与中证500分别为{h.rank_ic_mean:.4f}、{z.rank_ic_mean:.4f}。方向与平均回归系数一致，但指数池的ICIR均低于全A。三池同窗比较排除了时段不同这一解释；成员范围、截面数量与各池独立预处理仍有差异，不能将差距唯一归因于规模。', 'C1.csv', 'Rank IC字段，三池各228期'))
    add('### 5.2 C2：五层与多空绩效')
    add(table(['股票池', 'Q1年化', 'Q2年化', 'Q3年化', 'Q4年化', 'Q5年化', '递增相邻层/4', '层序秩相关'],
              [[POOL[r.pool], *[pct(getattr(r, f'Q{q}_ann')) for q in range(1, 6)], f'{r.adjacent_order}/4', number(r.layer_rank_rho)] for r in c2.itertuples()]))
    add(claim('C2_layers', f'全A五层年化净收益从{pct(ca.Q1_ann)}依次升至{pct(ca.Q5_ann)}，4/4个相邻层递增，层序与年化收益Spearman为1。中证500同样4/4递增；沪深300为3/4，Q3低于Q2。整体排序支持正向BP假说，但“每池严格单调”不成立。', 'C2.csv', 'Q1–Q5年化、相邻层数、秩相关'))
    add(table(['股票池', '多空年化', '多空夏普', '多空最大回撤', '多空月胜率', 'Q5算术年化超额'],
              [[POOL[r.pool], pct(r.long_short_ann), number(r.long_short_sharpe), pct(r.long_short_max_dd), f'{r.long_short_positive}/228 ({pct(r.long_short_win_rate)})', pct(r.q5_ann_exc)] for r in c2.itertuples()]))
    add(claim('C2_ls', f'全A扣双腿成本后的多空年化为{pct(ca.long_short_ann)}、夏普{ca.long_short_sharpe:.3f}、最大回撤{pct(ca.long_short_max_dd)}。两指数池多空年化约5%，且沪深300多空最大回撤接近47.50%，因此全A结果不能直接替代指数池风险判断。全A Q5算术年化超额为{pct(stats.loc[5, "ann_exc"])}，Q1为{pct(stats.loc[1, "ann_exc"])}；多空同时包含高BP端的超额与低BP端的落后，不能全部称为多头选股收益。', 'C2.csv;ALL_A_layer_stats.csv', '多空绩效及Q1/Q5年化超额'))

    add('### 5.3 时间路径：D2与D3\n\n'+figure('D2', 'D2：Rank IC累计和'))
    segments = []
    for start, end in [('2007-02', '2013-12'), ('2014-01', '2020-12'), ('2021-01', '2026-01')]:
        g = m.loc[start:end]
        segments.append(dict(start=start, end=end, n=len(g), mean_ic=g.ic.mean(), sum_coef=g.factor_ret.sum(), **{f'Q{q}_roll_mean': rolling.loc[start:end, str(q)].mean() for q in range(1, 6)}))
    seg = pd.DataFrame(segments)
    seg.to_csv(run / 'interpretation_segments.csv', index=False, encoding='utf-8-sig')
    add(claim('D2', '三个日历块的平均Rank IC分别为'+ '、'.join(f'{r.mean_ic:.4f}（{r.start}至{r.end}，{r.n}期）' for r in seg.itertuples()) + '，均为正；但2010、2013年全年平均IC接近零，累计曲线存在走平阶段。持续累积的是排序相关，不是复利收益。', 'ALL_A_monthly.csv;interpretation_segments.csv;C3.csv', 'ic及分段均值'))
    add(figure('D3', 'D3：标准化BP回归系数累计和'))
    add(claim('D3', f'228期回归系数累计为{m.factor_ret.sum():.4f}；三个日历块分别贡献'+ '、'.join(f'{x:.4f}' for x in seg.sum_coef) +'，正向累计并非只来自一个块。曲线也存在回落，故正均值不能表述为每月稳定获利。系数对应一单位标准化BP暴露且控制行业和规模，其算术累计没有交易组合净值含义。', 'ALL_A_monthly.csv;interpretation_segments.csv', 'factor_ret累计及分段累计'))
    add('### 5.4 绝对、相对与滚动表现：D4–D7\n\n'+figure('D4', 'D4：五层、内部等权基准及两价格指数净值'))
    wealth = (1 + net).prod()
    bwealth = (1 + m.benchmark).prod()
    ix = read('index_returns').groupby('index_code')['ret'].apply(lambda r: (1+r).prod())
    add(claim('D4', f'同样从1开始，期末Q5净值为{wealth["5"]:.3f}，内部基准为{bwealth:.3f}，Q1为{wealth["1"]:.3f}；沪深300和中证500价格指数分别为{ix["000300.SH"]:.3f}与{ix["000905.SH"]:.3f}。长期财富差异明显，但Q5最大回撤仍达{pct(stats.loc[5, "max_dd"])}，高年化不等于低绝对风险。图用对数轴呈现比例变化；外部价格指数缺分红且采用市值加权，与个股等权复权组合的差距不能全归于因子。', 'ALL_A_layers_net.csv;ALL_A_monthly.csv;index_returns.csv;ALL_A_layer_stats.csv', '期末净值及Q5最大回撤'))
    add(figure('D5', 'D5：分层净值除以内部基准净值'))
    relative_19_20 = (1 + net.loc['2019-01':'2020-12', '5']).prod() / (1 + m.loc['2019-01':'2020-12', 'benchmark']).prod() - 1
    add(claim('D5', f'期末Q5/基准为{wealth["5"]/bwealth:.3f}，Q4为{wealth["4"]/bwealth:.3f}，Q3为{wealth["3"]/bwealth:.3f}；超额财富主要集中在高层。但2019-01至2020-12的Q5相对财富变化为{pct(relative_19_20)}，这一段没有继续积累优势。相对净值的斜率不等于算术年化超额，分段结论来自对应收益的乘积比。', 'ALL_A_layers_net.csv;ALL_A_monthly.csv', '期末相对净值及2019–2020分段'))
    add(figure('D6', 'D6：连续12个月的层复利收益减基准复利收益'))
    add(table(['持有期归属区间', '有效滚动点', 'Q1均值', 'Q2均值', 'Q3均值', 'Q4均值', 'Q5均值'],
              [[r.start+'—'+r.end, int(rolling.loc[r.start:r.end, '5'].notna().sum()), *[pct(getattr(r, f'Q{q}_roll_mean')) for q in range(1, 6)]] for r in seg.itertuples()]))
    bad = rolling['5'].dropna().lt(0)
    runs = []
    for _, group in bad.groupby(bad.ne(bad.shift()).cumsum()):
        if group.all(): runs.append((len(group), group.index[0], group.index[-1]))
    longest = max(runs)
    add(claim('D6', f'Q5滚动超额为正的点为{int(rolling["5"].gt(0).sum())}/217，最长连续为负区间为{longest[1]}至{longest[2]}（{longest[0]}个滚动端点，按持有期归属月）。表中Q5三个分段均值为正，不能掩盖这一失效段。前11期为空；每点使用连续12期，且相邻窗口重叠11期，不能按217个独立观测推断显著性。', 'D6_rolling_excess.csv;interpretation_segments.csv', 'Q5符号、最长负区间及各层分段均值'))
    add(figure('D7', 'D7：多空净月收益与同序列复利净值'))
    add(claim('D7', f'多空正收益为{int(m.long_short.gt(0).sum())}/228个月，期末净值{(1+m.long_short).prod():.3f}。最差月为{m.long_short.idxmin()}，收益{pct(m.long_short.min())}；最好月为{m.long_short.idxmax()}，收益{pct(m.long_short.max())}，均按持有期起始月份归属。月度胜率仅约六成，长期复利优势并不意味着多数月份都能显著获利。多空是教材双腿差额复利约定，未模拟借券可得性和资金占用。', 'ALL_A_monthly.csv', 'long_short符号、极值及复利'))

    add('## 6. 分年度与适用域\n\n### 6.1 C3：年度结果')
    add(table(['年份', '月数', '多空收益', '多空月胜率', 'Q5收益', '内部基准', '多头超额', '平均IC'],
              [[str(r.year)+('（部分）' if r.partial_year else ''), r.n_months, pct(r.long_short_return), pct(r.long_short_win_rate), pct(r.q5_return), pct(r.benchmark_return), pct(r.long_excess), number(r.rank_ic_mean, 4)] for r in c3.itertuples()]))
    full = c3[~c3.partial_year]
    badyears = '、'.join(map(str, full[full.long_short_return.lt(0)].year))
    discord = full[full.long_short_return.gt(0) & full.long_excess.lt(0)]
    add(claim('C3', f'2007年仅11期、2026年仅1期，表内均为实际累计而非全年外推。18个完整年度中，多空正收益{int(full.long_short_return.gt(0).sum())}/18年，多头超额为正{int(full.long_excess.gt(0).sum())}/18年；多空不利年份为{badyears}。2019年多空为正但Q5跑输内部基准，说明低BP端落后可在多头选股失效时支撑多空。2025年IC均值仍为0.0495，Q5超额却为−5.39个百分点：排序关联的存在不保证最高层当年跑赢基准。', 'C3.csv', '完整年度符号、2019与2025'))
    add('### 6.2 C4：行业内五层')
    add('共同信号窗2021-07至2025-12，共54期；实际入场2021-08-02，退出2026-02-02。按Q5算术年化超额降序；夏普对应Q5，IR与超额回撤对应行业内部等权基准。收益排序按各层CAGR从高到低列出，ρ为层序与CAGR的Spearman。')
    add(table(['一级行业', '有效期/54', 'Q5年化超额', '夏普', 'IR', '超额回撤', '相对月胜率', '层收益排序', 'ρ'],
              [[r.industry_label, f'{r.n_months}/54', pct(r.ann_exc), number(r.sharpe), number(r.ir), pct(r.excess_max_dd), pct(r.relative_win_rate), r.layer_order if pd.notna(r.layer_order) else '样本不足', number(r.layer_rank_rho)] for r in c4.itertuples()]))
    valid = c4[c4.status.eq('complete')]
    add(claim('C4', f'30个可比行业中，Q5年化超额为正{int(valid.ann_exc.gt(0).sum())}/30，Q5收益排名第一{int(valid.q5_rank.eq(1).sum())}/30、前二{int(valid.q5_rank.le(2).sum())}/30。家用电器Q5年化超额17.93%，房地产−6.39%、钢铁−6.75%，煤炭接近零且为负。这支持较广但非普遍的行业内区分能力；美容护理最低只有27只，极端结果尤其不宜外推。综合行业仅12/54期达25只门槛，保留不足行，不拼接12期年化。行业排名是未作多重检验校正的描述，不能据最高排名宣称最优投资行业。', 'C4.csv;../../preflight_repaired/industry_comparison_coverage.csv', '30可比行业、Q5名次、负超额行业；综合不足'))
    add('### 6.3 D8与D9：分层粒度及风险调整\n\n'+figure('D8', 'D8：五层年化收益、夏普与信息比率'))
    add(claim('D8', f'五层年化收益与夏普均随层序递增，Q5夏普为{stats.loc[5, "sharpe"]:.3f}。信息比率却在Q4达到{stats.loc[4, "ir"]:.3f}，高于Q5的{stats.loc[5, "ir"]:.3f}；Q5相对月胜率{pct(stats.loc[5, "relative_win_rate"])}也低于Q4的{pct(stats.loc[4, "relative_win_rate"])}。高BP端的绝对收益较高，但相对基准超额的稳定性并非最高；这与“因子越高越稳”不同。', 'ALL_A_layer_stats.csv', 'ann、sharpe、ir、relative_win_rate'))
    add(figure('D9', 'D9：同一全A残差的十层绩效'))
    add(claim('D9', f'十层CAGR有{int((np.diff(ten.ann)>0).sum())}/9对相邻层递增，层序秩相关{spearmanr(ten.index, ten.ann).statistic:.3f}；Q9与Q10分别为{pct(ten.loc[9, "ann"])}、{pct(ten.loc[10, "ann"])}，最高尾部增益很小。Q10算术年化超额{pct(ten.loc[10, "ann_exc"])}低于Q9的{pct(ten.loc[9, "ann_exc"])}，IR也从{ten.loc[9, "ir"]:.3f}降至{ten.loc[10, "ir"]:.3f}。更细分层没有逆转整体CAGR排序，却揭示最高尾部的超额波动，不能据五层单调就断言极端BP越大越好。', 'D9_layer_stats.csv', '十层CAGR、相邻层及Q9/Q10超额风险'))
    add('### 6.4 D10：市值三分域\n\n'+figure('D10', 'D10：低、中、高流通市值域内十层年化超额'))
    size_counts = read('D10_size_domains')
    add(table(['流通市值域', '每期只数范围', 'Q1年化超额', 'Q10年化超额', '递增相邻层/9'],
              [[label, f'{int(size_counts[size_counts.size_bucket.eq(i)].n.min())}—{int(size_counts[size_counts.size_bucket.eq(i)].n.max())}', pct(d.loc[1, 'ann_exc']), pct(d.loc[10, 'ann_exc']), f'{int((np.diff(d.ann_exc)>0).sum())}/9'] for i, label, d in zip([1,2,3], ['低','中','高'], domains)]))
    add(claim('D10', f'三域均有228期，Q10算术年化超额分别为'+ '、'.join(pct(d.loc[10, 'ann_exc']) for d in domains) +'；低、中市值域的十层年化超额均9/9递增，高市值域有中低层倒序。BP作用在低市值域更强，但高市值域Q10仍为正，不能称其仅适用于小盘。划域发生在S形成之后，域内BP覆盖均为100%；这不替代U→F的整体覆盖，前置排除已在D1披露。市值分界按每月等人数变化，记录实际边界和层数；本图为依次分组，不是独立双重排序，也不保证每层持仓权重严格行业/规模中性。', 'D10_size_domains.csv;D10_size1_layer_stats.csv;D10_size2_layer_stats.csv;D10_size3_layer_stats.csv', '三域Q1/Q10、层序、样本数'))

    add('''## 7. 综合判断与局限

**结论为“保留BP作为后续多因子研究候选，同时观察时变性和适用域”。** 三池回归系数和平均Rank IC方向一致，成本后分层大体支持正向假说；全A证据强于两个指数池。年度和行业结果说明它具有条件性：2019、2025年的高层超额不支持持续增强，房地产、钢铁等行业的高层也未跑赢各自基准。上述异质性已经进入判断，没有通过换因子、反转方向或调整窗口消除。

三类证据衡量的对象不同。WLS强调加权线性斜率，Rank IC衡量全截面排序，等权高层组合只使用尾部股票并扣费。因此正IC、正回归与某年Q5弱超额可以同时成立；D8、D9的高层IR回落也提示“高期望收益”与“低超额波动”不可混同。方法检查已统一日期、样本、冻结暴露与成本，剩余差异不应仅用故事强行解释为同一种经济机制。

历史PB及行业来自当前可取得的历史版本，无法证明完全无回填或修订；这限制“当时即可复制”的主张。有限股本修正没有扩展为全市场PIT数据库。停牌和合并估值、两项未上市权利延续以及最后交易日退出依赖已声明政策，限制净值的可执行解释。教材只数换手未计入真实冲击、涨跌停成交、融资融券和投资者税负；Q5与未扣费内部基准的成本待遇也不同。外部价格指数仅作背景参照。

本报告没有完成多空均值的HAC显著性检验、行业多重检验校正或样本外策略评估；逐月t和ICIR不能替代这些推断。没有把这些范围外工作包装成已完成的稳健性。若下一步进入多因子合成，首先应检验BP与其他估值/质量因子的相关冗余，并用新的时间窗及可执行成本验证是否保留增量，而不是根据本次最优行业或市值域直接优化交易规则。''')

    add(f'''## 8. 复现与资料

本报告唯一实证运行是`{args.run_id}`，方法版本0.5，研究源码提交`{manifest['source_version']}`。月度结果、C1–C4、D1–D10底层数据和12张PNG/PDF/SVG图均位于`outputs/runs/{args.run_id}/`；逐条主张对应`report/claim_evidence.csv`。证券级暴露、持仓和补充证据保留本地，不随公开仓库提交。

在项目目录，用课程Python环境执行：

```powershell
python -m unittest discover -s tests -p test_bp_core.py -v
python scripts/run_research.py --run-id <新的运行标识> --course-root <课程材料目录>
python scripts/plot_results.py --run-id <同一运行标识>
python scripts/build_report.py --run-id <同一运行标识>
```

`run_research.py`要求P1修复面板及日期表已存在；P1重建入口和资料来源见`outputs/preflight_repaired/preflight_findings.md`及`scripts/preflight_repaired.py`。原始数据仅从课程材料`data/offline`读取。没有找到课程中所称的独立报告生成脚本，故本项目增加了最小报告层，未覆盖课程Notebook或共享qfbook。

方法依据：课程`main_student.pdf`附录书197–200页（PDF211–214页）；交易时点、成本与统计定义参考书177–183页（PDF191–197页）。实现复用`qfbook.factor.single_test`的MAD、标准化、中性化、设计矩阵和双腿扣费；必要行为差异见`outputs/validation/implementation_notes.md`。数据来源核验和官方公告证据见P1预检记录。本文没有引入未经核实的外部论文或文献结论。

本稿由研究代码生成表图，并由AI辅助整理文字与证据对应；不是期刊投稿稿，也未代替作者作课程提交。''')

    abstract = f'''# BP单因子测试报告

方法版本0.5 · 2026-10-26 · 全部 A 股、沪深300与中证500

## 摘要

本文检验正且有限历史PB倒数所构成的BP因子，预期高BP对应较高下期收益。采用月末信号、下一交易日收盘换仓、行业与规模控制、WLS、Rank IC及扣教材成本的等权分层，三池共同评价2007-02至2026-01归属的228个完整持有期。全A平均Rank IC为{a.rank_ic_mean:.4f}，正向月份{int(a.ic_positive)}/228；五层年化净收益由{pct(ca.Q1_ann)}递增至{pct(ca.Q5_ann)}，多空年化{pct(ca.long_short_ann)}，Q5相对内部基准的算术年化超额{pct(ca.q5_ann_exc)}。指数池方向相同而强度较弱。行业共同窗口中Q5在{int(valid.q5_rank.eq(1).sum())}/30个可比行业排名第一；房地产、钢铁等行业为负超额，综合行业样本不足。2025年正IC与负多头超额并存，低市值域的排序关系更强。结论是保留BP作为后续研究候选，观察时变性与行业边界；历史版本修订、估值近似及简化成本使本结果不能直接解释为严格PIT或实盘可实现收益。
'''
    report = abstract.strip() + '\n\n' + '\n\n'.join(chunks) + '\n'
    assert report.count('![') == 12 and len(claims) == 18
    (out / 'bp_single_factor_report.md').write_text(report, encoding='utf-8')
    pd.DataFrame(claims).to_csv(out / 'claim_evidence.csv', index=False, encoding='utf-8-sig')
    print(f'Wrote Chinese report ({len(report)} characters), 12 figures, {len(claims)} evidence records.')


if __name__ == '__main__':
    main()
