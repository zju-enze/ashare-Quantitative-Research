"""Typeset locked aggregate CSVs; no empirical model is rerun here.

Revision 2026-10-28: table notes follow the revised manuscript (including the
author's manual C1a note), negative numbers use a typeset minus sign, counts and
correlations previously hard-coded in notes are computed from the data, C3 gains
the exact long/short decomposition from derived_C3_decomposition.csv (run
scripts/derive_interpretation.py first) and D10 gains the Q10 information ratio.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'source-data'
OUT = ROOT / 'tables'
POOL = {'HS300': '沪深300', 'ZZ500': '中证500', 'ALL_A': '全部 A 股'}


def minus(text):
    return '$-$' + text[1:] if text.startswith('-') else text


def pct(x):
    return '---' if pd.isna(x) else minus(f'{x*100:.2f}')


def num(x, digits=3):
    return '---' if pd.isna(x) else minus(f'{x:.{digits}f}')


def table(name, title, headers, rows, cols, note='', long=False):
    start = (r'\begingroup\small\setlength{\tabcolsep}{4pt}'+'\n')
    head = ' & '.join(headers) + r' \\ \midrule' + '\n'
    body = '\n'.join(' & '.join(map(str, row)) + r' \\' for row in rows)
    if long:
        start += r'\begin{longtable}{'+cols+'}\n'+r'\caption*{\textbf{'+title+r'}}\\'+'\n'+r'\toprule'+'\n'+head
        start += r'\endfirsthead'+'\n'+r'\caption*{'+title+r'（续）}\\\toprule'+'\n'+head+r'\endhead'+'\n'
        start += r'\midrule\multicolumn{'+str(len(headers))+r'}{r}{续下页}\\\endfoot'+'\n'+r'\bottomrule\endlastfoot'+'\n'
        end = '\n'+r'\end{longtable}'
    else:
        start += r'\begin{table}[H]\centering'+'\n'+r'\caption*{\textbf{'+title+'}}\n'
        start += r'\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}'+cols+r'@{}}\toprule'+'\n'+head
        end = '\n'+r'\bottomrule\end{tabular*}'+('\n'+r'\par\smallskip\raggedright\footnotesize '+note if note else '')+r'\end{table}'
        note = ''
    end += '\n'+(r'\noindent\footnotesize '+note+'\par\n' if note else '')+r'\endgroup'+'\n'
    (OUT/(name+'.tex')).write_text(start+body+end,encoding='utf-8')


def main():
    c1,c2,c3,c4 = [pd.read_csv(DATA/(name+'.csv')) for name in ['C1','C2','C3','C4']]
    c1=c1.set_index('pool').loc[list(POOL)].reset_index()
    c2=c2.set_index('pool').loc[list(POOL)].reset_index()
    assert len(c1)==len(c2)==3 and len(c3)==20 and len(c4)==31
    table('C1a','表C1(a)　回归法汇总', ['股票池','因子',r'$|t|$均值',r'$|t|>2$占比',r'$t$均值',r'\makecell{因子收益均值\\（\%/月）}'],
          [[POOL[r.pool],'BP',num(r.t_abs_mean),f'{r.t_abs_gt2}/228 ({pct(r.t_abs_gt2_rate)}\%)',num(r.t_mean),pct(r.factor_ret_mean)] for r in c1.itertuples()], 'llrrrr',
          '各池均有228期。回归系数对应一单位标准化BP暴露；表中是截面$t$统计量。')
    table('C1b','表C1(b)　Rank IC汇总',['股票池','因子','Rank IC均值','Rank IC标准差','ICIR',r'$IC>0$占比'],
          [[POOL[r.pool],'BP',num(r.rank_ic_mean,4),num(r.rank_ic_sd,4),num(r.ic_ir),f'{r.ic_positive}/228 ({pct(r.ic_positive_rate)}\%)'] for r in c1.itertuples()], 'llrrrr',
          '时间序列标准差使用$n-1$分母；ICIR未年化。')
    table('C2a','表C2(a)　五层年化净收益',['股票池','因子','Q1','Q2','Q3','Q4','Q5',r'\makecell{递增相邻\\层数/4}'],
          [[POOL[r.pool],'BP',*[pct(getattr(r,f'Q{q}_ann')) for q in range(1,6)],f'{r.adjacent_order}/4'] for r in c2.itertuples()], 'llrrrrrr',
          '收益单位为\%，为复合年化净收益（CAGR）。三池层序与年化收益的Spearman相关分别为'+'、'.join(num(v) for v in c2.layer_rank_rho)+'。每池228期，所有层均已扣教材成本。')
    table('C2b','表C2(b)　多空绩效与多头超额',['股票池',r'\makecell{多空年化\\（\%）}','夏普',r'\makecell{最大回撤\\（\%）}','多空月胜率',r'\makecell{Q5年化超额\\（百分点）}'],
          [[POOL[r.pool],pct(r.long_short_ann),num(r.long_short_sharpe),pct(r.long_short_max_dd),f'{r.long_short_positive}/228 ({pct(r.long_short_win_rate)}\%)',pct(r.q5_ann_exc)] for r in c2.itertuples()], 'lrrrrr',
          '夏普、回撤和胜率对应多空，回撤按含期初净值1的序列计算；Q5年化超额为相对内部基准（等权毛收益）的算术年化超额，即月超额均值乘以12。')
    dec=pd.read_csv(DATA/'derived_C3_decomposition.csv',encoding='utf-8-sig')
    dec=dec[dec.year.ne('all_annualized')].assign(year=lambda d: d.year.astype(int)).set_index('year')
    table('C3','表C3　全部 A 股分年度表现',['年份','月数',r'\makecell{多空\\收益}',r'\makecell{多空月\\胜率}',r'\makecell{Q5\\收益}',r'\makecell{内部基准\\收益}',r'\makecell{多头超额\\（复利差）}',r'\makecell{多头\\部分}',r'\makecell{空头\\部分}',r'\makecell{平均\\Rank IC}'],
          [[str(r.year)+('*' if r.partial_year else ''),r.n_months,pct(r.long_short_return),pct(r.long_short_win_rate),pct(r.q5_return),pct(r.benchmark_return),pct(r.long_excess),pct(dec.loc[r.year,'long_part']),pct(dec.loc[r.year,'short_part']),num(r.rank_ic_mean,4)] for r in c3.itertuples()], 'lrrrrrrrrr',
          '收益与胜率单位为\%，多头超额与两部分单位为百分点。年度按持有期起始月归属；*为部分年度，报告实际累计收益，不向全年外推。胜率分母为该行月数。多头超额为当年Q5复利收益减内部基准复利收益，不同于正文的算术年化超额。多头部分为当年各月“Q5净收益减内部基准毛收益”之和，空头部分为当年各月“内部基准毛收益减Q1毛收益再减Q1腿成本”之和；两部分相加等于当年各月多空净收益之和。',long=True)
    table('C4a','表C4(a)　行业内五层的Q5绩效',['一级行业','有效期',r'\makecell{年化超额\\（百分点）}','夏普','IR',r'\makecell{超额回撤\\（\%）}',r'\makecell{相对月\\胜率（\%）}'],
          [[r.industry_label,f'{r.n_months}/54',pct(r.ann_exc),num(r.sharpe),num(r.ir),pct(r.excess_max_dd),pct(r.relative_win_rate)] for r in c4.itertuples()], 'lrrrrrr',
          '共同信号窗为2021-07至2025-12（54期，持有期归属2021-08至2026-01），按年化超额降序。年化超额为算术年化超额；夏普对应Q5，IR、超额回撤和胜率相对行业内部基准（等权毛收益）。完整行业胜率分母均为54；综合行业不计算共同窗口绩效。',long=True)
    order=lambda text: '$'+text.replace('Q','Q_')+'$' if pd.notna(text) else '样本不足'
    table('C4b','表C4(b)　行业内收益排序与样本量',['一级行业',r'\makecell{每期最少\\股票数}',r'\makecell{Q5收益\\名次}','层收益排序',r'层序相关$\rho$'],
          [[r.industry_label,r.min_n,int(r.q5_rank) if pd.notna(r.q5_rank) else '---',order(r.layer_order),num(r.layer_rank_rho)] for r in c4.itertuples()], 'lrrlr',
          '收益排序按各层年化净收益从高到低排列；相关系数是层序与年化收益的Spearman相关。共30个完整行业，综合行业保留不足行。',long=True)
    segments=pd.read_csv(DATA/'interpretation_segments.csv')
    rolling=pd.read_csv(DATA/'D6_rolling_excess.csv',encoding='utf-8-sig').set_index('holding_month')
    table('D6','表D6附表　各层滚动12个月超额的分段均值',['持有期归属区间','有效点','Q1','Q2','Q3','Q4','Q5'],
          [[r.start+'至'+r.end,int(rolling.loc[r.start:r.end,'5'].notna().sum()),*[pct(getattr(r,f'Q{q}_roll_mean')) for q in range(1,6)]] for r in segments.itertuples()], 'lrrrrrr',
          '单位为百分点。分段按滚动端点归属，窗口可跨分段边界，相邻窗口重叠11期。')
    counts=pd.read_csv(DATA/'D10_size_domains.csv')
    rows=[]
    for i,label in enumerate(['低','中','高'],1):
        d=pd.read_csv(DATA/f'D10_size{i}_layer_stats.csv').set_index('layer')
        n=counts[counts.size_bucket.eq(i)].n
        rows.append([label,f'{n.min()}--{n.max()}',pct(d.loc[1,'ann_exc']),pct(d.loc[10,'ann_exc']),num(d.loc[10,'ir']),f'{int(d.ann_exc.diff().gt(0).sum())}/9'])
    table('D10','表D10附表　市值域的样本量与两端超额',['流通市值域','每期只数范围','Q1年化超额','Q10年化超额','Q10信息比率','递增相邻层数/9'],rows,'lrrrrr',
          '超额为相对域内基准（等权毛收益）的算术年化超额，单位为百分点；三域均有228期。每月先按流通市值三等分，再在各域内按同一份全部 A 股残差十等分。')
    assert len(list(OUT.glob('C*.tex')))==7
    print('Generated nine source-backed table files.')


if __name__=='__main__':
    main()
