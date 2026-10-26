"""Course figures from locked aggregate results, with PNG/PDF/SVG exports."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#386A9D', '#58A1A6', '#8C8C80', '#C88A3C', '#B84747']


def main():
    run = ROOT / 'source-data'
    out = ROOT / 'figures'
    out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Microsoft YaHei', 'DejaVu Sans'],
                         'font.size': 12, 'axes.unicode_minus': False, 'svg.fonttype': 'none', 'pdf.fonttype': 42,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.linewidth': .7, 'legend.frameon': False, 'figure.facecolor': 'white'})
    def read(name):
        return pd.read_csv(run / (name + '.csv'))
    def times(name):
        frame = read(name).set_index('holding_month')
        frame.index = pd.PeriodIndex(frame.index, freq='M')
        return frame
    def base(title, ylabel, height=4.8):
        fig, ax = plt.subplots(figsize=(9, height))
        fig.subplots_adjust(left=.12, right=.87, bottom=.16, top=.89)
        ax.set_title('')
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', color='#E5E5E5', linewidth=.6)
        ax.set_axisbelow(True)
        return fig, ax
    def date_axis(ax):
        ax.xaxis.set_major_locator(mdates.YearLocator(3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.set_xlabel('持有期退出日期')
    def legend(ax, twin=None, ncol=3):
        handles, labels = ax.get_legend_handles_labels()
        if twin is not None:
            h, l = twin.get_legend_handles_labels()
            handles += h
            labels += l
        ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1.015), ncol=ncol, fontsize=11, borderaxespad=0)
    def save(fig, name, source, note):
        fig.canvas.draw()
        fig.savefig(out / f'{name}.png', dpi=180, bbox_inches='tight')
        fig.savefig(out / f'{name}.pdf', bbox_inches='tight')
        
        # Each figure has one plot area; dual axes are two scales of that same panel.
        (out / f'{name}.alignment.json').write_text(json.dumps({'status': 'NOT APPLICABLE', 'reason': 'Single plot area; no comparable panels'}, indent=2), encoding='utf-8')
        manifest.append(dict(figure=name, source=source, note=note, archetype='quantitative single panel'))
        plt.close(fig)
    def wealth(values):
        result = np.r_[1, np.cumprod(1 + np.asarray(values))]
        assert np.isfinite(result).all() and (result > 0).all()
        return result

    manifest = []
    cal = read('calendar')
    dates = pd.to_datetime(cal.exit_date.astype(str))
    wealth_dates = pd.DatetimeIndex([pd.to_datetime(str(cal.entry_date.iloc[0]))] + dates.tolist())
    monthly = times('ALL_A_monthly')
    net = times('ALL_A_layers_net')
    bnav = wealth(monthly.benchmark)
    note = '全部 A 股；228期；分层扣教材成本，内部等权基准不扣成本。'
    ind = read('industry_median_20260130').sort_values('bp_median')
    fig, ax = base('最新截面：一级行业原始 BP 中位数', '申万一级行业', height=9.5)
    fig.subplots_adjust(left=.2, top=.98, bottom=.08)
    ax.set_title('')
    ax.barh(ind.industry_label, ind.bp_median, color='#386A9D')
    ax.set_xlabel('BP = 1 / PB（倍）')
    save(fig, 'industry_median', 'industry_median_20260130.csv', '2026-01-30；正有限PB的F样本；31个一级行业；不含本期未来收益。')

    size = read('size_correlation')
    fig, ax = base('原始 BP 与对数总市值的截面相关', 'Spearman 相关系数')
    ax.plot(pd.to_datetime(size.signal_month), size.rho, color='#386A9D', linewidth=1.2)
    ax.axhline(0, color='#555555', linewidth=.7)
    date_axis(ax)
    ax.set_xlabel('信号月份')
    save(fig, 'size_correlation', 'size_correlation.csv', '229个完整信号月；原始BP与ln(总市值)；相关系数不是中性化后的结果。')

    flow = read('D1_sample_flow').query('pool == "ALL_A"')
    fig, ax = base('D1  合格样本与 BP 覆盖度', '股票数量')
    fd = pd.to_datetime(flow.signal_month)
    for key, color, style in [('U', '#888888', '-'), ('F', '#386A9D', '--'), ('S', '#58A1A6', ':')]:
        ax.plot(fd, flow[key], label=key+'数量', color=color, linestyle=style)
    twin = ax.twinx()
    twin.plot(fd, flow.bp_coverage_f_over_u, color='#B84747', label='覆盖度 F/U', linewidth=1)
    twin.set_ylim(.90, 1.01)
    twin.set_ylabel('BP 覆盖度（右轴）')
    twin.yaxis.set_major_formatter(PercentFormatter(1))
    date_axis(ax)
    ax.set_xlabel('信号月份')
    legend(ax, twin, ncol=4)
    save(fig, 'D1', 'D1_sample_flow.csv', 'U：历史合格池；F：正有限PB；S：再满足行业/市值控制；229信号月。')

    for key, number, title, ylabel in [('ic', 'D2', 'Rank IC 算术累计', '累计 Rank IC'),
                                       ('factor_ret', 'D3', 'WLS 因子系数算术累计', '累计系数（收益小数）')]:
        fig, ax = base(number+'  '+title, ylabel)
        ax.plot(dates, monthly[key].cumsum(skipna=False), color='#386A9D')
        ax.axhline(0, color='#555555', linewidth=.7)
        date_axis(ax)
        save(fig, number, 'ALL_A_monthly.csv', '全部 A 股；228期；逐期相加，不是投资财富净值。')

    fig, ax = base('D4  五层组合、内部基准与价格指数净值', '期初净值 = 1（对数轴）', height=4.6)
    for q, color in zip(net, COLORS):
        ax.plot(wealth_dates, wealth(net[q]), color=color, label='Q'+q, linewidth=1.2)
    ax.plot(wealth_dates, bnav, color='#222222', linestyle='--', label='内部等权基准')
    ix = read('index_returns')
    for code, label, color in [('000300.SH', '沪深300价格指数', '#82649A'), ('000905.SH', '中证500价格指数', '#9B7553')]:
        ax.plot(wealth_dates, wealth(ix.query('index_code == @code').ret), linestyle=':', color=color, label=label)
    ax.set_yscale('log')
    date_axis(ax)
    legend(ax, ncol=4)
    save(fig, 'D4', 'ALL_A_layers_net.csv;ALL_A_monthly.csv;index_returns.csv', '统一2007-02-01至2026-02-02端点；个股为复权收益，外部指数不含分红。')

    fig, ax = base('D5  五层相对内部基准净值', '层净值 / 内部基准净值')
    for q, color in zip(net, COLORS):
        ax.plot(wealth_dates, wealth(net[q]) / bnav, color=color, label='Q'+q)
    ax.axhline(1, color='#555555', linewidth=.7)
    legend(ax, ncol=5)
    date_axis(ax)
    save(fig, 'D5', 'ALL_A_layers_net.csv;ALL_A_monthly.csv', note)

    rolling = times('D6_rolling_excess')
    fig, ax = base('D6  滚动12个月复利超额收益', '层累计收益 − 基准累计收益')
    for q, color in zip(rolling, COLORS):
        ax.plot(dates, rolling[q], color=color, label='Q'+q, linewidth=1)
    ax.axhline(0, color='#555555', linewidth=.7)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    legend(ax, ncol=5)
    date_axis(ax)
    save(fig, 'D6', 'D6_rolling_excess.csv', '全部 A 股；前11个月为空；217个重叠窗口，不能视为217个独立样本。')

    fig, ax = base('D7  多空月收益与累计净值', '多空月收益（左轴）', height=7.6)
    ax.bar(dates, monthly.long_short, width=21, color='#58A1A6', label='多空净月收益')
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    twin = ax.twinx()
    twin.plot(wealth_dates, wealth(monthly.long_short), color='#B84747', label='多空净值', linewidth=1.5)
    twin.set_ylabel('多空净值（右轴，期初1）')
    legend(ax, twin)
    date_axis(ax)
    save(fig, 'D7', 'ALL_A_monthly.csv', 'Q5毛收益−Q1毛收益−两腿成本；教材复利约定，不代表实盘资本占用。')

    for name, source, title in [('D8', 'ALL_A_layer_stats', '五层收益与风险调整指标'), ('D9', 'D9_layer_stats', '十层收益与风险调整指标')]:
        stats = read(source)
        fig, ax = base(name+'  '+title, '年化净收益（左轴）')
        ax.bar(stats.layer, stats.ann, color='#A7C4D8', label='年化净收益', width=.6)
        ax.set_xticks(stats.layer, ['Q'+str(q) for q in stats.layer])
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        twin = ax.twinx()
        twin.plot(stats.layer, stats.sharpe, color='#386A9D', marker='o', label='夏普比率')
        twin.plot(stats.layer, stats.ir, color='#B84747', marker='s', linestyle='--', label='信息比率')
        twin.set_ylabel('夏普 / 信息比率（右轴）')
        legend(ax, twin)
        save(fig, name, source+'.csv', note+'RF=0；时间序列标准差ddof=1。')

    fig, ax = base('D10  三个市值域内十层年化超额', '相对域内基准的算术年化超额', height=5.6)
    for i, color, label in [(1, '#386A9D', '低流通市值'), (2, '#58A1A6', '中流通市值'), (3, '#C88A3C', '高流通市值')]:
        stats = read(f'D10_size{i}_layer_stats')
        ax.bar(stats.layer + (i - 2) * .25, stats.ann_exc, width=.24, color=color, label=label)
    ax.set_xticks(range(1, 11), ['Q'+str(q) for q in range(1, 11)])
    ax.axhline(0, color='#555555', linewidth=.7)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    legend(ax)
    save(fig, 'D10', 'D10_size1_layer_stats.csv;D10_size2_layer_stats.csv;D10_size3_layer_stats.csv', '每月先按流通市值三等分，再按同一全部 A 股残差十等分；域内等权毛基准。')
    pd.DataFrame(manifest).to_csv(out / 'figure_sources.csv', index=False, encoding='utf-8-sig')
    assert len(manifest) == 12
    print('Exported 12 typeset figures as PDF and PNG.')


if __name__ == '__main__':
    main()
