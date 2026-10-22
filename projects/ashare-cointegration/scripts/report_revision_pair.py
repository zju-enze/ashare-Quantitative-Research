"""Report saved supplementary results; never generate paths or rerun tests."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results_revision/pair_comparison'
METHODS=['EG-fixed-1','DH-fixed-1','EG-AIC','DH-fixed-7']
SCENARIOS=['PAIR_NULL','PAIR_COINT','HEAVY_NULL','HEAVY_COINT']
LABELS={'PAIR_NULL':'主规格：无协整','PAIR_COINT':'主规格：协整',
        'HEAVY_NULL':'ν=3.5：无协整','HEAVY_COINT':'ν=3.5：协整'}


def main():
    validation=json.loads((OUT/'formal_validation.json').read_text())
    status=json.loads((OUT/'formal_status.json').read_text())
    assert validation['status']=='passed' and status['completed_paths']==20000
    summary=pd.read_csv(OUT/'formal_summary.csv')
    paired=pd.read_csv(OUT/'formal_paired.csv')
    main_results=summary.loc[np.isclose(summary.alpha,.05)].set_index(['scenario','method'])
    main_pairs=paired.loc[np.isclose(paired.alpha,.05)].set_index(['scenario','comparison'])
    engineering=json.loads((OUT/'engineering_status.json').read_text())
    calls=[item for item in status['invocations'] if not item['summarize_only']]
    elapsed=sum(item['elapsed_seconds'] for item in calls if 'elapsed_seconds' in item)
    missing_times=sum('elapsed_seconds' not in item for item in calls)
    timing_note=(f'另有{missing_times}次中断调用缺少完整计时，未计入上述耗时。'
                 if missing_times else '')
    resource=json.loads((OUT/'resource_sample.json').read_text(encoding='utf-8-sig')) if (OUT/'resource_sample.json').exists() else None
    tables={}
    for comparison,first,second in [('primary','EG-fixed-1','DH-fixed-1'),
                                    ('working_specs','EG-AIC','DH-fixed-7')]:
        rows=[]
        for scenario in SCENARIOS:
            a,b=main_results.loc[(scenario,first)],main_results.loc[(scenario,second)]
            difference=main_pairs.loc[(scenario,comparison)]
            rows.append(f"|{LABELS[scenario]}|{100*a.rate:.2f}% [{100*a.lower_95:.2f}, {100*a.upper_95:.2f}]|"
                f"{100*b.rate:.2f}% [{100*b.lower_95:.2f}, {100*b.upper_95:.2f}]|"
                f"{100*difference.difference_EG_minus_DH:+.2f}|{100*difference.paired_mcse:.3f}|")
        tables[comparison]='\n'.join(rows)

    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    plot_order=['PAIR_NULL','HEAVY_NULL','PAIR_COINT','HEAVY_COINT']
    titles=['Main: no cointegration','Heavy tail: no cointegration',
            'Main: cointegrated','Heavy tail: cointegrated']
    colors=['#2369a0','#c45b22','#62a5c7','#e6a05c']
    maxima={kind:max(.1 if kind=='NULL' else .3,
        1.12*summary.loc[np.isclose(summary.alpha,.05)&summary.scenario.str.endswith(kind),'upper_95'].max())
        for kind in ('NULL','COINT')}
    for ax,scenario,title in zip(axes.flat,plot_order,titles):
        for y,(method,color) in enumerate(zip(METHODS,colors)):
            row=main_results.loc[(scenario,method)]
            ax.errorbar(row.rate,y,xerr=[[row.rate-row.lower_95],[row.upper_95-row.rate]],
                        fmt='o',color=color,capsize=3,ms=6)
            ax.annotate(f'{100*row.rate:.2f}%',(row.rate,y),xytext=(0,9),
                        textcoords='offset points',ha='center',fontsize=8)
        ax.set_yticks(range(4),METHODS)
        ax.set_ylim(3.7,-.7)
        ax.set_xlim(0,min(1,maxima['NULL' if scenario.endswith('NULL') else 'COINT']))
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(axis='x',alpha=.2)
        ax.set_title(title,loc='left',fontsize=12)
        ax.set_xlabel('Type I rejection rate' if scenario.endswith('NULL') else 'Power at nominal 5%')
        if scenario.endswith('NULL'):
            ax.axvline(.05,color='#555555',ls='--',lw=1)
    fig.suptitle('EG and DH on identical calibrated log-price paths',x=.02,ha='left',fontsize=16)
    fig.supxlabel('5,000 independent repetitions per scenario; pointwise 95% exact binomial intervals.\n'
                  'Single-pair results, not market-family FWER. Heavy-tail cases fall outside the DH moment assumption.',fontsize=9)
    fig.savefig(OUT/'supplementary_rejection_rates.png',dpi=180)
    plt.close(fig)

    interpretation=[]
    for method in METHODS:
        row=main_results.loc[('PAIR_NULL',method)]
        relation=('整个区间高于5%' if row.lower_95>.05 else
                  '整个区间低于5%' if row.upper_95<.05 else '区间包含5%')
        interpretation.append(f'- {method}：主零假设拒绝率{100*row.rate:.2f}%，95%区间'
                              f'[{100*row.lower_95:.2f}%, {100*row.upper_95:.2f}%]，{relation}。')
    eg_power=main_results.loc[('PAIR_COINT','EG-fixed-1')]
    dh_power=main_results.loc[('PAIR_COINT','DH-fixed-1')]
    dh_working=main_results.loc[('PAIR_COINT','DH-fixed-7')]
    power_difference=main_pairs.loc[('PAIR_COINT','primary')]
    heavy_eg=main_results.loc[('HEAVY_NULL','EG-fixed-1')]
    heavy_dh=main_results.loc[('HEAVY_NULL','DH-fixed-1')]
    resource_text=(f"运行中一次进程树采样的工作集合计{resource['working_set_mib']:.2f} MiB、"
                   f"可用内存{resource['free_memory_mib']:.2f} MiB；该值不是峰值。") if resource else '未取得有效运行中内存采样。'
    report=f'''# V1-R / V2-R补充实验报告

完成时间：{status['completed_at']}。按[联合修订计划](../../EXPERIMENT_REVISION_PLAN_V1_V2.md)及ENG-020执行，已完成20,000条正式路径、80,000次检验。工程阶段另有20条/80次检验，未进入正式统计；独立核对的少量重复另计。

**主规格下，两种一阶检验的误拒率区间均覆盖5%；在预定慢回复备择下，EG一阶功效为{100*eg_power.rate:.2f}%，DH一阶为{100*dh_power.rate:.2f}%。厚尾对照中，EG一阶误拒率为{100*heavy_eg.rate:.2f}%，DH一阶为{100*heavy_dh.rate:.2f}%。这些结论限于本DGP的单对比较。**

## 1. 复用与本轮新增范围

直接复用原V1/V2市场清单、已完成校准汇总与其限制结论，以及已估计的empirical-pair-dgp-1参数。EG-AIC调用原V1内核；DH调用已修复实际使用递归前缀的内核，分别设置1阶和7阶。新增固定1阶EG适配、共同路径运行入口、检查点及汇总。

原V1的110对名义发现、原V2的0对名义发现保留；本轮没有读取新市场价格、重估DGP或重算67,678个市场候选。旧模拟的DGP、输入、预检或选阶与本轮不同，因此旧重复不能混入新情景分母。9份关键历史证据/参数文件与运行前保存内容直接比较一致，详见[复用清单](reuse_inventory.json)。

这是一组新的条件性方法比较。不能把旧大面板FWER与本次单对误拒率直接相减，或将旧市场发现追认为已验证协整。

## 2. 固定设计

- 四情景：PAIR_NULL、PAIR_COINT、HEAVY_NULL、HEAVY_COINT，各5,000条独立两股票路径。
- 同一路径同时用于EG-fixed-1、DH-fixed-1、EG-AIC、DH-fixed-7；前两者为主比较，后两者为原工作规格对照。四情景使用独立随机流。
- T=1,212、预热2,000；固定方向A对B、直接使用生成器给出的对数价格，不再次取log、不做逐股ADF门槛。EG残差ADF保留，使用协整分布的p值。
- 主DGPν=(6,7,4.5)、ρ=0.030371485237；无协整φ=1，协整φ=0.992917086360。厚尾对照只将个股ν改为3.5并维持单位方差，其余不变。
- 主水平5%，辅助水平1%；精确参数、种子和运行环境见[机器协议](experiment_protocol.json)、[环境记录](environment.json)和已保存的源文件快照。
- 各条路径的p值、统计量、实际阶数、有效观测数、数值状态、耗时与种子组件按批保存，可续跑缺失批次。主拒绝率分母包含全部5,000条路径；数值不可用记为未拒绝并单列。

## 3. 主比较：相同1阶

括号中为逐格95%双侧Clopper–Pearson区间；差值为EG减DH，单位为百分点。配对MCSE按同一路径拒绝指示之差计算。

|情景|EG-fixed-1：拒绝率 [95%区间]|DH-fixed-1：拒绝率 [95%区间]|差值：百分点|配对MCSE：百分点|
|---|---:|---:|---:|---:|
{tables['primary']}

## 4. 原工作规格对照

|情景|EG-AIC：拒绝率 [95%区间]|DH-fixed-7：拒绝率 [95%区间]|差值：百分点|配对MCSE：百分点|
|---|---:|---:|---:|---:|
{tables['working_specs']}

![新增补充实验结果](supplementary_rejection_rates.png)

## 5. 结果解释与范围

{chr(10).join(interpretation)}

主备择下，同路径EG一阶减DH一阶的功效差为{100*power_difference.difference_EG_minus_DH:.2f}个百分点，配对Monte Carlo标准误为{100*power_difference.paired_mcse:.3f}个百分点。DH从7阶改为1阶后，本批功效由{100*dh_working.rate:.2f}%变为{100*dh_power.rate:.2f}%，与同阶EG的差距仍然存在；不能把观察到的低功效仅归于使用了7阶。

厚尾零假设下，EG一阶误拒率的95%区间为[{100*heavy_eg.lower_95:.2f}%, {100*heavy_eg.upper_95:.2f}%]，DH一阶为[{100*heavy_dh.lower_95:.2f}%, {100*heavy_dh.upper_95:.2f}%]。前者高于5%的偏离应保留为厚尾风险证据；后者在这一情景中的表现不能证明DH对所有无四阶矩过程都有效。

这些是逐规格区间的直接描述，不是同时覆盖或预先定义的硬验收分档。功效应结合相应零假设尺寸解释；尺寸偏高时，较高备择拒绝率不能单独解释为更好的方法。未根据结果更换DGP参数、选阶、重复数或临界值。

本次功效只覆盖φ≈0.9929、主导半衰期约97.5日这一慢回复备择，不是一条完整功效曲线。备择φ来自市场价差的描述性持久性参考，模拟真值由DGP矩阵秩决定，不意味着真实股票对已被认定协整。

ν=3.5情景仍有有限方差，但不满足DH超过四阶矩的假设；它作为实际厚尾风险的对照完整报告，不能替代主规格理论范围内的比较。主规格虽然满足矩条件，个股参数贴近矩边界，有限样本表现以本次结果为准。

本两股票DGP未复现完整共享股票候选图，因此本报告不提供全市场FWER、FDR或多重校正后的功效保证。V1/V2旧发现数也不因本报告而改变；V3、市场重评及2026年样本外/交易阶段没有启动。

## 6. 执行与验证

已记录的正式调用墙钟合计{elapsed:.3f}秒，4进程、BLAS单线程；工程阶段记录调用合计{sum(x.get('elapsed_seconds',0) for x in engineering['invocations']):.3f}秒。{timing_note}{resource_text}

- 5项新增测试通过：固定EG的独立残差回归、DH完整IV矩阵、原对数输入及EG-AIC复用、配对统计汇总、检查点不重算。
- 全部80,000行通过情景/重复/规格覆盖、种子、阶数、有效样本数、p值映射和汇总核对；32行汇总及16行配对比较分别复算，精确区间与独立binomtest接口一致。
- 正式结果数值不可用{validation['numerical_unavailable']}行，p=0有{validation['zero_p_rows']}行。若为0，只说明本批没有观察到，不是一般不存在这些情况的证明。
- 正式每个情景另取第4,999号路径重建，共4条、16次统计量核对；EG对照锁定coint接口，DH对照完整IV矩阵。它们与已保存结果相符，但没有重新计算全部正式路径。
- 关键历史证据和DGP参数内容保持一致；原市场和校准结果没有重算或覆盖。

文件：

- [正式汇总](formal_summary.csv)：包含5%主水平及1%辅助水平。
- [同路径配对比较](formal_paired.csv)、[正式执行状态](formal_status.json)、[正式核对记录](formal_validation.json)。
- [工程执行状态](engineering_status.json)、[工程核对](engineering_validation.json)、[复用清单](reuse_inventory.json)。
- [补充入口](../../run_pair_comparison.py)、[方法适配](../../src/revision_pair.py)、[核对脚本](../../scripts/validate_revision_pair.py)。
- 完整逐重复结果留在.local/revision_pair/formal/batches；运行源码和DGP快照在.local/revision_pair/source。

只需重新生成本报告时运行scripts/report_revision_pair.py；只需重新汇总时运行run_pair_comparison.py --phase formal --summarize-only。普通续跑入口也会验证并复用已完成批次，不重新生成它们。
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    print(main_results[['rate','lower_95','upper_95']].to_string())
    print('Report and plot saved. No test or path was rerun.')


if __name__=='__main__':
    main()
