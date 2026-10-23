"""Validate saved fits and report the calibrated pair DGP; no refits or draws."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import calibrate_dgp as fit
import json
import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.dgp_calibration import moment_multiplier, pair_matrices


def independent_likelihood(row, series):
    y=np.asarray(series[:,int(row.series_index)])/row.scale
    design=np.column_stack((np.ones(len(y)-1),y[:-1]))
    initial=y[1:]-design@np.linalg.lstsq(design,y[1:],rcond=None)[0]
    weights=.94**np.arange(min(75,len(initial)))
    backcast=float(np.sum(initial[:len(weights)]**2*weights)/weights.sum())
    residual=y[1:]-row.mean_constant/row.scale-row.ar1*y[:-1]
    omega=row.omega/row.scale**2
    variance=np.empty(len(residual))
    previous_variance=backcast
    previous_squared=backcast
    for i,value in enumerate(residual):
        variance[i]=omega+row.alpha*previous_squared+row.beta*previous_variance
        previous_variance=variance[i]
        previous_squared=value*value
    return float(t.logpdf(residual,df=row.nu,
                         scale=np.sqrt(variance*(row.nu-2)/row.nu)).sum())


def main():
    current=pd.read_csv(fit.PRIVATE/'estimates.csv')
    reference=pd.read_csv(fit.PRIVATE/'free_nu_reference.csv')
    spec=json.loads((fit.OUTPUT/'dgp_spec.json').read_text(encoding='utf-8'))
    structure=json.loads((fit.OUTPUT/'price_structure.json').read_text())
    execution=json.loads((fit.OUTPUT/'execution.json').read_text())
    records=[json.loads(line) for line in (fit.PRIVATE/'estimates.jsonl').read_text(
        encoding='utf-8').splitlines()]
    assert execution['status']=='complete' and len(current)==6212
    assert current[['series_index','model']].duplicated().sum()==0
    assert set(current.model)=={'fixed_nu','finite_moment'}
    assert current.groupby('series_index').size().eq(2).all()
    assert current.nobs.eq(1210).all() and len(reference)==3106
    fixed=current.loc[current.model.eq('fixed_nu')].set_index('series_index')
    finite=current.loc[current.model.eq('finite_moment')].set_index('series_index')
    assert (fixed.loglikelihood>=finite.loglikelihood-1e-5).all()
    assert current.loss_from_free_reference.min()>=-1e-5
    assert finite.ar1.abs().lt(1).all()
    assert finite[['alpha','beta']].ge(0).all().all()
    assert (finite.alpha+finite.beta).lt(1).all()
    assert finite.moment_4_1.lt(1).all()
    assert finite.groupby('kind').nu.first().to_dict()==fit.NU
    np.testing.assert_allclose(finite.moment_loss,
                               fixed.loglikelihood-finite.loglikelihood,
                               rtol=0,atol=1e-7)

    source=fit.ROOT/'.local/production/formation-2021-2025-v2'
    series=np.load(fit.SOURCE/'series.npy',mmap_mode='r')
    prices=np.load(source/'prices.npy',mmap_mode='r')
    np.testing.assert_allclose(series[:,:2984],100*np.diff(np.log(prices),axis=0),
                               rtol=0,atol=1e-12)
    positions=[]
    for _,group in finite.reset_index().groupby('kind'):
        positions.extend(group.iloc[np.unique(np.linspace(0,len(group)-1,
                                     min(3,len(group))).astype(int))].series_index)
    repairs=json.loads((fit.PRIVATE/'reference_repairs.json').read_text())
    positions.extend(record['series_index'] for record in repairs)
    positions.append(int(finite.moment_loss.idxmax()))
    sample=current.loc[current.series_index.isin(set(positions))]
    ll_errors=[]
    moment_errors=[]
    for row in sample.itertuples():
        ll_errors.append(abs(independent_likelihood(row,series)-row.loglikelihood))
        integrated=quad(lambda z:2*(row.alpha*z*z+row.beta)**2.05*
                        t.pdf(z,row.nu,scale=np.sqrt((row.nu-2)/row.nu)),
                        0,np.inf,epsabs=1e-9,epsrel=1e-9,limit=200)[0]
        moment_errors.append(abs(integrated-row.moment_4_1))
    assert max(ll_errors)<1e-6 and max(moment_errors)<1e-7

    matrices={}
    for name,phi in [('null',1.),('alternative',spec['phi_alternative'])]:
        adjustment,short_run=pair_matrices(spec['rho'],phi)
        companion=np.block([[np.eye(2)+adjustment+short_run,-short_run],
                            [np.eye(2),np.zeros((2,2))]])
        roots=np.sort(np.linalg.eigvals(companion).real)
        np.testing.assert_allclose(roots,np.sort([1.,phi,spec['rho'],spec['rho']]),
                                   rtol=0,atol=1e-9)
        assert np.linalg.matrix_rank(adjustment)==int(name=='alternative')
        matrices[name]=dict(adjustment=adjustment.tolist(),short_run=short_run.tolist(),
                            companion_roots=roots.tolist())
    variance_shares=spec['innovation_variance_shares']
    common=variance_shares['market']+variance_shares['industry']
    covariance=(1-spec['rho']**2)*np.array([[1.,common],[common,1.]])
    assert np.linalg.eigvalsh(covariance).min()>0
    for driver in spec['drivers'].values():
        assert driver['omega']>0 and driver['alpha']+driver['beta']<1
        assert moment_multiplier(driver['alpha'],driver['beta'],driver['nu'])<1
        np.testing.assert_allclose(driver['omega'],1-driver['alpha']-driver['beta'],
                                   rtol=0,atol=1e-12)
    attempts=[attempt for record in records for attempt in record['attempts']
              if 'success' in attempt]
    validation=dict(completed_at=fit.now(),status='passed_parameter_and_structure_checks',
        logical_models=6212,proxy_series=3106,independent_likelihood_cases=len(sample),
        independent_likelihood_max_abs_error=max(ll_errors),
        independent_fractional_moment_cases=len(sample),
        independent_fractional_moment_max_abs_error=max(moment_errors),
        fixed_nu_optimizer_attempts=len(attempts),
        unsuccessful_start_attempts=sum(not a['success'] for a in attempts),
        free_nu_reference_repairs=len(repairs),
        finite_moment_max=float(finite.moment_4_1.max()),
        price_and_saved_return_inputs_match=True,
        matrices=matrices,innovation_covariance=covariance.tolist(),
        deterministic_recursion_test='two-period fixed-shock fixture; no random draw',
        random_simulations=False,EG_DH_retests=False,
        finite_sample_error_control='not_evaluated',out_of_sample_fit='not_evaluated')
    (fit.OUTPUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')

    allframes=[reference.assign(model='free_nu_reference'),current]
    allrows=pd.concat(allframes,ignore_index=True)
    summaries=[]
    for (kind,model),group in allrows.groupby(['kind','model'],sort=True):
        item=dict(kind=kind,model=model,series=len(group),
                  ar1_median=float(group.ar1.median()),
                  alpha_median=float(group.alpha.median()),
                  beta_median=float(group.beta.median()),
                  persistence_median=float((group.alpha+group.beta).median()))
        if model!='free_nu_reference':
            item.update(moment_boundary=int(group.moment_boundary.sum()),
                        free_reference_loss_median=float(group.loss_from_free_reference.median()))
            for q in (.1,.5,.9,.95,1.):
                item[f'moment_loss_q{int(100*q)}']=float(group.moment_loss.quantile(q))
            item['moment_loss_per_obs_median']=float(group.moment_loss_per_obs.median())
        summaries.append(item)
    summary=pd.DataFrame(summaries)
    summary.to_csv(fit.OUTPUT/'parameter_comparison.csv',index=False)
    losses=finite.reset_index()[['series_index','kind','identifier','moment_loss',
                                  'moment_loss_per_obs','loss_from_free_reference']]
    losses.to_csv(fit.PRIVATE/'per_series_fit_loss.csv',index=False)

    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(15,4.7),layout='constrained')
    style=[('free_nu_reference','Free nu reference','#8a8a8a'),
           ('fixed_nu','Fixed nu = 4.5','#c87b28'),
           ('finite_moment','Fixed nu + finite 4.1 moment','#2369a0')]
    for model,label,color in style:
        group=allrows.loc[allrows.kind.eq('specific_proxy') & allrows.model.eq(model)]
        for ax,column,title in zip(axes[:2],['alpha','beta'],
                                   ['Volatility response alpha','Lagged variance beta']):
            values=np.sort(group[column].to_numpy())
            ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',
                    color=color,label=label,lw=1.6)
            ax.set_xlabel(title)
            ax.set_ylabel('Fraction of 2,984 specific proxies')
            ax.grid(axis='y',alpha=.2)
    loss=finite.loc[finite.kind.eq('specific_proxy'),'moment_loss_per_obs']
    values=np.sort(loss.to_numpy())
    axes[2].step(values,np.arange(1,len(values)+1)/len(values),where='post',color='#2369a0')
    axes[2].axvline(np.median(values),color='#444444',ls='--',lw=1)
    axes[2].set_xlabel('Extra constraint loss (nats / observation)')
    axes[2].set_ylabel('Fraction of 2,984 specific proxies')
    axes[2].grid(axis='y',alpha=.2)
    axes[0].legend(frameon=False,loc='lower right',fontsize=8)
    fig.suptitle('Fixed-nu, finite-moment calibration | A-shares, 2021-2025',x=.02,ha='left',fontsize=15)
    fig.supxlabel('In-sample empirical distributions. No Monte Carlo experiment or EG/DH market retest.',fontsize=9)
    fig.savefig(fit.OUTPUT/'specific_parameter_and_fit_loss.png',dpi=180)
    plt.close(fig)

    individual=allrows.loc[allrows.kind.eq('specific_proxy')]
    table=[]
    for model,label,_ in style:
        group=individual[individual.model.eq(model)]
        table.append(f"|{label}|{group.ar1.median():.5f}|{group.alpha.median():.5f}|"
                     f"{group.beta.median():.5f}|{(group.alpha+group.beta).median():.5f}|")
    driver_table=[]
    for key,label in [('market','市场'),('industry','行业'),('specific','个股')]:
        p=spec['drivers'][key]
        driver_table.append(f"|{label}|{p['nu']:.1f}|{p['alpha']:.9f}|{p['beta']:.9f}|"
                            f"{p['omega']:.9f}|{p['moment_4_1']:.9f}|")
    half_life=float(np.log(.5)/np.log(spec['phi_alternative']))
    counts=finite.groupby('kind').moment_boundary.sum().to_dict()
    constrained_specific=finite.loc[finite.kind.eq('specific_proxy')]
    report=f'''# 固定自由度、有限4.1阶矩的DGP估计

完成时间：{fit.now()}。用户授权固定市场ν=6、行业ν=7、个股ν=4.5，使用已有2021—2025年数据重新估计AR/GARCH并形成可执行DGP；个股ν=3.5保留为厚尾对照。

**已完成3,106条代理序列的两种规格，共6,212个模型记录，并形成一个参数已估计、协整真值明确的两股票对数价格DGP。没有运行Monte Carlo、EG/DH市场重算、2026年样本外检验或恢复V3。**

## 1. 数据与识别范围

- 复用冻结formation-2021-2025-v2中的2,984只股票、1,212个价格观测，以及既有代理序列；1,211个日对数收益，AR模型有效观测1,210。
- 重新估计市场代理1条、行业剩余代理121条、个股剩余代理2,984条。原始收益未截尾、未缩尾；没有逐股ADF门槛。
- 代理是描述性分解，不是唯一识别出的结构冲击。原股票池要求持续覆盖与存续，不代表全部曾上市A股。
- 股份名称、原始价格、收益与逐序列参数留在.local目录。此目录中的汇总和DGP系数可独立审阅。

## 2. 固定ν与矩约束的估计

逐序列拟合r_t=c+ρr_(t−1)+ε_t，ε_t=√h_t z_t，h_t=ω+αε_(t−1)²+βh_(t−1)，z_t为单位方差Student-t。现有自由ν拟合作参考；新规格依次是：

1. 固定ν，保留普通GARCH的α+β≤1边界，用于隔离固定自由度造成的损失；该参考规格不被直接用作DGP。
2. 同样固定ν，要求|ρ|<1及K4.1=E[(αz²+β)^2.05]≤0.999999，得到严格有限4.1阶矩。1e−6只是严格不等式的数值间隔，不表示远离边界。

矩函数用Beta积分的超几何函数表达式计算；优化坐标按α/(α+β)及可行持续性比例构造，所以全过程满足约束。使用arch 8.0.0的方差递推与Student-t似然、SciPy SLSQP和预定的两个起点。取较优收敛解，不宣称全局最优保证。部分已可行的固定ν最优解直接复用。

主估计本机4进程、BLAS=1，{execution['elapsed_seconds']:.2f}秒完成全部3,106条序列。另有7条真实序列的预运行。为保证嵌套似然比较公平，新的固定ν拟合暴露出的3个旧自由ν局部最优已在本轮另存重估参考；旧自由度诊断文件没有覆盖。

## 3. 个股参数变化与拟合损失

|规格|ρ中位数|α中位数|β中位数|α+β中位数|
|---|---:|---:|---:|---:|
{chr(10).join(table)}

每列独立取中位数，不能把中位α与中位β相加当成持续性中位数。新增矩约束改变了即时冲击反应与持续性，两者都必须报告。

在固定ν=4.5已经重新优化之后，加入矩约束的个股额外对数似然损失Δℓ=ℓ_fixed−ℓ_constrained：

- 中位数{constrained_specific.moment_loss.median():.6f}，90%分位{constrained_specific.moment_loss.quantile(.9):.6f}，95%分位{constrained_specific.moment_loss.quantile(.95):.6f}，最大{constrained_specific.moment_loss.max():.6f}。
- 每个观测的中位损失{constrained_specific.moment_loss_per_obs.median():.8f} nats；比较使用完全相同的数据、尺度和似然初始化。
- 相比自由ν参考，总损失的中位数为{constrained_specific.loss_from_free_reference.median():.6f}。不同损失的中位数不能直接相加。
- 个股有{int(counts['specific_proxy'])}/2984组贴近矩约束边界；行业为{int(counts['industry_proxy'])}/121，市场为0/1。

这只是训练内拟合代价，不是预测准确率或收益损失，也没有用普通卡方分布作边界约束似然比检验。约95%的个股触及边界，说明约束确实限制了数据偏好的尾部与波动组合；数学上存在矩不等于有限样本表现已得到验证。

![个股参数与拟合损失](specific_parameter_and_fit_loss.png)

## 4. 最终两股票DGP

### 4.1 为什么采用共同短期AR

直接叠加具有不同AR滤波的潜在市场、行业和个股趋势，不自动证明被检验的两个股票价格构成DH要求的闭合线性动态系统。本参考DGP因此将短期动态直接写在两股票VECM中，并用全体股票标准化收益的合并回归估计一条共同ρ。逐代理的自由ρ估计仍完整保留在第3节和本地参数表。

估计ρ={spec['rho']:.12f}。固定该ρ后，对已有代理去模型均值、应用共同AR滤波并按各自创新样本标准差标准化；在有限矩约束下重新估计三个组的共同GARCH形状。它是等序列权重的复合似然参考，不把相关股票当独立样本进行区间推断。

每个底层冲击ε_k,t=√h_k,t z_k,t，h_k,t=ω_k+α_k ε_k,t−1²+β_k h_k,t−1；底层z在时间和成分间独立，具有相应单位方差t分布。下表使用ω=1−α−β，使各底层ε的无条件方差为1：

|成分|ν|α|β|ω|K4.1|
|---|---:|---:|---:|---:|---:|
{chr(10).join(driver_table)}

**实际生成必须读取dgp_spec.json中的完整精度；不得把表格圆整值复制为最终机器参数。个股聚合解也贴近矩边界。**

### 4.2 创新相关结构与尺度

在去共同AR后的标准化股票收益上，用4,382,958个跨行业配对和67,678个同业配对的平均协方差估计三个方差份额。未构造庞大的协方差矩阵，采用行业和全市场求和恒等式；三个估计份额均为正，没有事后裁剪。

- 市场v_M={variance_shares['market']:.9f}，行业v_G={variance_shares['industry']:.9f}，个股v_I={variance_shares['specific']:.9f}，合计1。
- 同业创新相关系数参考为v_M+v_G={common:.9f}；跨行业平均协方差仅用于分解市场份额，不声称单对生成器已复现跨配对依赖网络。
- 两股各有独立个股冲击，共享市场和行业冲击。η_i,t=√(1−ρ²)(√v_M ε_M,t+√v_G ε_G,t+√v_I ε_i,t)。个股份额严格为正，因此两方程创新协方差非退化。
- 最后乘股票日对数收益标准差的样本中位数s={spec['return_scale']:.12f}，对应约{100*spec['return_scale']:.3f}%日波动；再加log(100)作为价格水平常数。零假设下该归一化使日增量的无条件标准差为s。

### 4.3 已知真值的零假设与备择

定义P_s=0.5×[[1,−1],[−1,1]]，P_c=I−P_s。两股票标准化对数价格x满足：

    Δx_t = Π x_(t−1) + Γ Δx_(t−1) + η_t
    Π = −(1−φ)(1−ρ) P_s
    Γ = ρ P_c + φρ P_s

- 零假设：φ=1，Π=0；两条独立永久方向都存在，两股均为I(1)，没有协整。
- 备择：φ={spec['phi_alternative']:.12f}；Π秩为1，x_1−x_2平稳。伴随矩阵根为1、φ、ρ、ρ，只有一个单位根。平稳价差有两个稳定根φ与ρ，约{half_life:.2f}个交易日是主导根对应的回复半衰期。
- φ来自全部67,678对经固定波动尺度标准化的对数价差：对s_t−ρs_(t−1)拟合含常数AR(1)，取未筛选估计的中位数。其10%/90%分位为{structure['phi_quantiles']['0.1']:.6f}/{structure['phi_quantiles']['0.9']:.6f}；{structure['phi_outside_stationary_interval']}对点估计不在(−1,1)内，仍保留在统计中。
- 这一步给备择回复速度提供描述性市场量级；有限样本价差回归可能呈现伪回复，**φ小于1不能据此认定真实股票对协整**。模拟真值由Π的结构设置，而不是由市场检验结果贴标签。
- 个股ν=3.5厚尾对照只替换两条个股底层z的自由度，仍作单位方差标准化；ρ、φ、GARCH系数、权重与尺度都保持不变。该对照没有有限四阶矩，不属于DH的既定矩假设范围。

### 4.4 适用条件与尚未检验的内容

主DGP是明确的有限阶两方程系统，无确定性漂移；短期根稳定、创新具有非退化常数无条件协方差，GARCH冲击是鞅差。正ω与Student-t密度给出有界条件密度，K4.1<1给出统一有限4.1阶矩；备择的协整秩及无I(2)结构由矩阵根直接核对。上述结构与EG的稳定短记忆/函数极限定理设定以及DH的相关动态和矩条件相容。平稳条件异方差不等于原N5—N7的非平稳方差断点。

实际EG/DH选阶、有限样本p值和错误率、功效及多重校正仍需后续模拟验证。本DGP用于两股票检验比较，不复现2,984股、67,678条共享股票边的完整家族图。扩展到该图不能默认继承本两方程结构保证。

## 5. 核对与复现

- 四项新测试通过：分数阶矩与独立积分、四阶解析式及可行参数化、已知协整秩与根、两期固定冲击递推。后者不调用随机数生成。
- 全部6,212模型的任务覆盖、相同观测数、逐对嵌套似然关系和所有约束核对通过；参考中3个旧局部最优单独修复并留痕。
- {len(sample)}个实际拟合结果采用独立OLS初始化、手写方差递推和SciPy Student-t密度核对，最大对数似然差{max(ll_errors):.3g}；同样{len(sample)}个矩函数与独立积分最大差{max(moment_errors):.3g}。抽样核对不等于独立重优化全部模型。
- 参数CSV与dgp_spec.json已保存；生成器已实现，但未调用它生成随机面板或运行检验。工程测试只使用两个时点的固定冲击。

文件：

- [机器DGP规格](dgp_spec.json)、[三类驱动参数](dgp_driver_parameters.csv)、[参数比较](parameter_comparison.csv)、[价格结构估计](price_structure.json)。
- [完整核对](validation.json)、[全量拟合执行记录](execution.json)、[结构估计执行记录](construction_execution.json)。
- [固定ν估计脚本](../../scripts/calibrate_dgp.py)、[参考修复和DGP构造](../../scripts/complete_dgp_calibration.py)、[本报告与核对脚本](../../scripts/report_dgp_calibration.py)、[矩函数和生成器](../../src/dgp_calibration.py)。
- 本地完整参数：[两种固定ν拟合](../../.local/review/dgp_fixed_nu_2021_2025/estimates.csv)、[自由ν参考](../../.local/review/dgp_fixed_nu_2021_2025/free_nu_reference.csv)、[参考修复记录](../../.local/review/dgp_fixed_nu_2021_2025/reference_repairs.json)、[逐序列损失](../../.local/review/dgp_fixed_nu_2021_2025/per_series_fit_loss.csv)、[全部价差持久性](../../.local/review/dgp_fixed_nu_2021_2025/pair_persistence.csv)。

复现顺序为calibrate_dgp.py、complete_dgp_calibration.py、report_dgp_calibration.py。拟合入口拒绝覆盖既有journal；重做时使用单独输出目录或副本。仅重新汇总可运行report_dgp_calibration.py，不会拟合或模拟。既有arch运行时位于.local/diagnostics_runtime/arch-8.0.0，未改动原虚拟环境依赖。

以后得到模拟授权后，生成器可读取完整JSON调用：

```python
import json
from pathlib import Path
from src.dgp_calibration import generate_pair
spec = json.loads(Path('results_review/dgp_fixed_nu_2021_2025/dgp_spec.json').read_text())
# Following example is documented only; it was not executed in this estimation run.
log_prices = generate_pair(spec, n_obs=1212, seed=20261021, cointegrated=False)
```

方法依据：[DH 2018](https://onlinelibrary.wiley.com/doi/abs/10.1111/obes.12214)、[Phillips–Ouliaris残差ADF理论](https://cowles.yale.edu/sites/default/files/2022-08/d0847-r.pdf)、[GARCH矩条件示例](https://mpra.ub.uni-muenchen.de/27685/1/MPRA_paper_27685.pdf)。
'''
    (fit.OUTPUT/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps(validation,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
