"""Course figures from locked aggregate results, with PNG/PDF exports.

Revision 2026-10-28 (after review): figures are drawn at the final printed
width (6.3 in, within the 166 mm text block) and placed at natural size, so the
in-figure type is about 8.5 pt everywhere. Time axes use the holding month
(month of entry), matching tables and prose. D5/D6 shade the failure periods
listed in derived_periods.csv (run scripts/derive_interpretation.py first).
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator, PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#386A9D', '#58A1A6', '#8C8C80', '#C88A3C', '#B84747']
WIDTH = 6.3
SHADE = '#B84747'


def main():
    run = ROOT / 'source-data'
    out = ROOT / 'figures'
    out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Microsoft YaHei', 'DejaVu Sans'],
                         'font.size': 8.5, 'axes.labelsize': 8.5, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
                         'legend.fontsize': 8, 'axes.unicode_minus': False, 'svg.fonttype': 'none', 'pdf.fonttype': 42,
                         'axes.spines.top': False, 'axes.spines.right': False, 'lines.linewidth': 1.0,
                         'axes.linewidth': .6, 'legend.frameon': False, 'figure.facecolor': 'white'})

    def read(name):
        return pd.read_csv(run / (name + '.csv'), encoding='utf-8-sig')

    def times(name):
        frame = read(name).set_index('holding_month')
        frame.index = pd.PeriodIndex(frame.index, freq='M')
        return frame

    def base(ylabel, height):
        fig, ax = plt.subplots(figsize=(WIDTH, height), layout='constrained')
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', color='#E5E5E5', linewidth=.5)
        ax.set_axisbelow(True)
        return fig, ax

    def date_axis(ax, label='持有期归属月份（按建仓月）', span=None):
        if span is not None:
            ax.set_xlim(*span)
        ax.xaxis.set_major_locator(mdates.YearLocator(3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.set_xlabel(label)

    def legend(ax, twin=None, ncol=3, extra=None):
        handles, labels = ax.get_legend_handles_labels()
        if twin is not None:
            h, l = twin.get_legend_handles_labels()
            handles += h
            labels += l
        for handle in extra or []:
            handles.append(handle)
            labels.append(handle.get_label())
        ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=ncol, borderaxespad=0,
                  handlelength=1.8, columnspacing=1.2)

    def save(fig, name, source, note):
        fig.savefig(out / f'{name}.png', dpi=300)
        fig.savefig(out / f'{name}.pdf')
        fig.savefig(out / f'{name}.svg')
        # Each figure has one plot area; dual axes are two scales of that same panel.
        (out / f'{name}.alignment.json').write_text(json.dumps({'status': 'NOT APPLICABLE', 'reason': 'Single plot area; no comparable panels'}, indent=2), encoding='utf-8')
        manifest.append(dict(figure=name, source=source, note=note, archetype='quantitative single panel'))
        plt.close(fig)

    def wealth(values):
        result = np.r_[1, np.cumprod(1 + np.asarray(values))]
        assert np.isfinite(result).all() and (result > 0).all()
        return result

    def shade(ax, rows, label):
        for r in rows.itertuples():
            ax.axvspan(pd.Period(r.start, 'M').start_time, pd.Period(r.end, 'M').end_time,
                       color=SHADE, alpha=.10, linewidth=0, zorder=0)
        return Patch(facecolor=SHADE, alpha=.10, label=label)

    manifest = []
    monthly = times('ALL_A_monthly')
    hm = monthly.index
    month_end = hm.to_timestamp(how='end')
    wealth_dates = pd.DatetimeIndex([hm[0].start_time] + list(month_end))
    bar_dates = hm.to_timestamp(how='start') + pd.Timedelta(days=14)
    net = times('ALL_A_layers_net')
    SPAN = (wealth_dates[0] - pd.Timedelta(days=150), month_end[-1] + pd.Timedelta(days=150))
    bnav = wealth(monthly.benchmark)
    periods = read('derived_periods')
    note = '全部 A 股；228期；分层扣教材成本，内部等权基准不扣成本。'

    ind = read('industry_median_20260130').sort_values('bp_median')
    fig, ax = base('申万一级行业', height=5.2)
    ax.grid(axis='y', visible=False)
    ax.grid(axis='x', color='#E5E5E5', linewidth=.5)
    ax.barh(ind.industry_label, ind.bp_median, color='#386A9D', height=.7)
    ax.set_ylim(-.6, len(ind) - .4)
    ax.set_xlabel('原始 BP 截面中位数（BP = 1/PB，无量纲）')
    save(fig, 'industry_median', 'industry_median_20260130.csv', '2026-01-30；正有限PB的F样本；31个一级行业；不含本期未来收益。')

    size = read('size_correlation')
    fig, ax = base('Spearman 相关系数', height=2.5)
    ax.plot(pd.to_datetime(size.signal_month), size.rho, color='#386A9D')
    ax.axhline(0, color='#555555', linewidth=.6)
    date_axis(ax, '信号月份')
    save(fig, 'size_correlation', 'size_correlation.csv', '229个完整信号月；原始BP与ln(总市值)；相关系数不是中性化后的结果。')

    flow = read('D1_sample_flow').query('pool == "ALL_A"')
    fig, ax = base('合格池 U 股票数（左轴）', height=2.7)
    fd = pd.to_datetime(flow.signal_month)
    ax.plot(fd, flow.U, color='#888888', label='合格池 U 股票数')
    twin = ax.twinx()
    twin.spines['right'].set_visible(True)
    twin.plot(fd, flow.bp_coverage_f_over_u, color='#B84747', label='覆盖度 F/U（右轴）')
    twin.set_ylim(.90, 1.005)
    twin.set_ylabel('BP 覆盖度 F/U（右轴）')
    twin.yaxis.set_major_formatter(PercentFormatter(1))
    date_axis(ax, '信号月份')
    legend(ax, twin, ncol=2)
    save(fig, 'D1', 'D1_sample_flow.csv', 'U：历史合格池；F：正有限PB；S：再满足行业/市值控制（F与S全期相差87个股票期，未单独作线）；229信号月。')

    for key, number, ylabel in [('ic', 'D2', '累计 Rank IC'), ('factor_ret', 'D3', '累计系数（月度系数之和）')]:
        fig, ax = base(ylabel, height=2.5)
        ax.plot(month_end, monthly[key].cumsum(skipna=False), color='#386A9D')
        ax.axhline(0, color='#555555', linewidth=.6)
        date_axis(ax, span=SPAN)
        save(fig, number, 'ALL_A_monthly.csv', '全部 A 股；228期；逐期相加，不是投资财富净值。')

    fig, ax = base('净值（期初 = 1，对数轴）', height=3.4)
    for q, color in zip(net, COLORS):
        ax.plot(wealth_dates, wealth(net[q]), color=color, label='Q'+q)
    ax.plot(wealth_dates, bnav, color='#111111', linestyle=(0, (4, 2)), linewidth=1.5, label='内部等权基准', zorder=6)
    ix = read('index_returns')
    for code, label, color in [('000300.SH', '沪深300价格指数', '#82649A'), ('000905.SH', '中证500价格指数', '#9B7553')]:
        ax.plot(wealth_dates, wealth(ix.query('index_code == @code').ret), linestyle=':', linewidth=1.3, color=color, label=label)
    ax.set_yscale('log')
    ax.yaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10, 20, 40]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_ylim(.4, 50)
    date_axis(ax)
    legend(ax, ncol=4)
    save(fig, 'D4', 'ALL_A_layers_net.csv;ALL_A_monthly.csv;index_returns.csv', '统一2007-02-01至2026-02-02端点；个股为复权收益，外部指数不含分红。')

    fig, ax = base('层净值 / 内部基准净值', height=3.0)
    patch = shade(ax, periods.query('series == "D5_Q5_relative_wealth"'), 'Q5 低于前高≥12个月')
    for q, color in zip(net, COLORS):
        ax.plot(wealth_dates, wealth(net[q]) / bnav, color=color, label='Q'+q, linewidth=1.5 if q == '5' else 1.0)
    ax.axhline(1, color='#555555', linewidth=.6)
    legend(ax, ncol=6, extra=[patch])
    date_axis(ax)
    save(fig, 'D5', 'ALL_A_layers_net.csv;ALL_A_monthly.csv;derived_periods.csv', note)

    rolling = times('D6_rolling_excess')
    fig, ax = base('层滚动12个月复利收益 − 基准', height=3.1)
    patch = shade(ax, periods.query('series == "D6_Q5_rolling_excess"'), 'Q5 连续为负≥6个端点')
    for q, color in zip(rolling, COLORS):
        ax.plot(month_end, rolling[q], color=color, label='Q'+q, linewidth=1.5 if q == '5' else .9)
    ax.axhline(0, color='#555555', linewidth=.6)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    legend(ax, ncol=6, extra=[patch])
    date_axis(ax, span=SPAN)
    save(fig, 'D6', 'D6_rolling_excess.csv;derived_periods.csv', '全部 A 股；前11个月为空；217个重叠窗口，不能视为217个独立样本。')

    fig, ax = base('多空净月收益（左轴）', height=3.1)
    ax.bar(bar_dates, monthly.long_short, width=22, color='#58A1A6', label='多空净月收益（柱，左轴）')
    ax.axhline(0, color='#555555', linewidth=.6)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    twin = ax.twinx()
    twin.spines['right'].set_visible(True)
    twin.plot(wealth_dates, wealth(monthly.long_short), color='#B84747', label='多空净值（线，右轴）', linewidth=1.3)
    twin.set_ylabel('多空净值（右轴，期初 = 1）')
    legend(ax, twin, ncol=2)
    date_axis(ax, span=SPAN)
    save(fig, 'D7', 'ALL_A_monthly.csv', 'Q5毛收益−Q1毛收益−两腿成本；教材复利约定，不代表实盘资本占用；两轴刻度相互独立。')

    for name, source in [('D8', 'ALL_A_layer_stats'), ('D9', 'D9_layer_stats')]:
        stats = read(source)
        fig, ax = base('年化净收益（柱，左轴）', height=2.8)
        ax.bar(stats.layer, stats.ann, color='#A7C4D8', label='年化净收益（左轴）', width=.6)
        ax.set_xticks(stats.layer, ['Q'+str(q) for q in stats.layer])
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        twin = ax.twinx()
        twin.spines['right'].set_visible(True)
        twin.plot(stats.layer, stats.sharpe, color='#386A9D', marker='o', markersize=3.5, label='夏普比率（右轴）')
        twin.plot(stats.layer, stats.ir, color='#B84747', marker='s', markersize=3.5, linestyle='--', label='信息比率（右轴）')
        twin.axhline(0, color='#999999', linewidth=.5)
        twin.set_ylabel('夏普 / 信息比率（右轴）')
        legend(ax, twin)
        save(fig, name, source+'.csv', note+'RF=0；时间序列标准差分母为n−1。')

    fig, ax = base('相对域内基准的算术年化超额', height=3.0)
    for i, color, label in [(1, '#386A9D', '低流通市值'), (2, '#58A1A6', '中流通市值'), (3, '#C88A3C', '高流通市值')]:
        stats = read(f'D10_size{i}_layer_stats')
        ax.bar(stats.layer + (i - 2) * .25, stats.ann_exc, width=.24, color=color, label=label)
    ax.set_xticks(range(1, 11), ['Q'+str(q) for q in range(1, 11)])
    ax.axhline(0, color='#555555', linewidth=.6)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    legend(ax)
    save(fig, 'D10', 'D10_size1_layer_stats.csv;D10_size2_layer_stats.csv;D10_size3_layer_stats.csv', '每月先按流通市值三等分，再按同一全部 A 股残差十等分；域内等权毛基准。')
    pd.DataFrame(manifest).to_csv(out / 'figure_sources.csv', index=False, encoding='utf-8-sig')
    assert len(manifest) == 12
    print('Exported 12 typeset figures as PDF and PNG.')


if __name__ == '__main__':
    main()
