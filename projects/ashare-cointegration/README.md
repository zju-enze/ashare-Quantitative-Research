# A 股同业协整研究

**主研究问题：在预先限定的A股同业股票对中，哪些配对具有协整证据？这些证据来自什么检验、经过什么多重校正，适用范围和限制是什么？**

**2026-10-23已完成修订设计的全市场检验与独立核对：67,678个候选、四规格合计270,712次检验。** V1/EG固定1阶得到行业内Holm284对、全局Holm21对名义发现；V2/DH固定1阶分别11对和0对。两种口径事前并列固定，整体错误控制校准仍未完成。V3继续暂停。

[本次市场汇总与全部清单](results_revision/market_20261023/REPORT.md) · [EG行业内284对](results_revision/market_20261023/EG-fixed-1_L2_Holm.csv) · [EG全局21对](results_revision/market_20261023/EG-fixed-1_GLOBAL_Holm.csv) · [DH行业内11对](results_revision/market_20261023/DH-fixed-1_L2_Holm.csv)。

## 正式交付

|入口|内容|
|---|---|
|[研究总报告](results_final/README.md)|股票对识别主问题、完整流程、当前证据与尚未回答的问题|
|[V1 / EG 正式报告](results_final/V1_FINAL_REPORT.md)|EG如何寻找协整证据，误报与漏检怎样影响名单|
|[V2 / DH 正式报告](results_final/V2_FINAL_REPORT.md)|DH为何用于识别，如何解释较少的检出|
|[术语与方法附录](results_final/METHODS_AND_GLOSSARY.md)|术语解释、复现公式、参数与完整选阶对照|
|[机器可读正式结果](results_final/FINAL_RESULTS.json)|本设计的模拟与市场统计、名义发现及未完成的全图校准标记|
|[共同设计与执行记录](EXPERIMENT_REVISION_PLAN_V1_V2.md)|已经执行的方案、参数、随机设计、指标与运行范围|
|[工程安排](ENGINEERING_CHANGES.md)|ENG-024全市场运行、结果和研究范围|
|[研究状态](RESEARCH_STATUS.json)|当前正式报告状态和独立保留的历史执行记录|

## 当前方法验证与识别任务的关系

共同 DGP 为 empirical-pair-dgp-1：市场/行业/个股自由度 6/7/4.5，ρ≈0.03037，协整备择 φ≈0.99292。每条路径 1,212 个对数价格观测，预热 2,000 期。四情景分别为主 DGP 无协整/慢回复协整，以及只把个股 ν 改为 3.5 的两种厚尾对照。

每情景 5,000 条独立路径，四情景共 20,000 条；每条路径同时用于 EG-1、DH-1、EG-AIC、DH-7，共 80,000 次检验。工程样本不进入正式统计。

|5% 名义水平|V1 / EG 固定 1 阶|V2 / DH 固定 1 阶|
|---|---:|---:|
|主 DGP 误报率|5.54%|5.06%|
|主 DGP 慢回复检出率|16.28%|8.56%|
|个股 ν=3.5 误报率|6.78%|4.62%|
|个股 ν=3.5 慢回复检出率|16.48%|8.12%|

误报率指没有协整却被判为有证据的比例；检出率（功效）指确有协整时被找出的比例。区间和同路径差异见正式报告。低误报与低检出可以并存，因此后续发现少不能直接解释为市场没有协整关系。

真实候选已完成名义检验与清单交付。行业内主清单中EG有148对、DH有4对存在至少一股I(1)诊断警示；DH一阶另有43个数值占位，均保留完整家族。全图错误控制校准仍未完成，2026评价和交易验证未开展。

## 参数、运行与来源

- [自由度诊断](results_review/student_t_2021_2025/REPORT.md)：形成期数据上的参数依据。
- [固定自由度、有限 4.1 阶矩 DGP](results_review/dgp_fixed_nu_2021_2025/REPORT.md)与[完整精度规格](results_review/dgp_fixed_nu_2021_2025/dgp_spec.json)。
- [冻结运行协议](results_revision/pair_comparison/experiment_protocol.json)、[正式汇总](results_revision/pair_comparison/formal_summary.csv)、[同路径比较](results_revision/pair_comparison/formal_paired.csv)。
- [运行入口](run_pair_comparison.py)、[完成记录](results_revision/pair_comparison/COMPLETION.json)及[独立核对](results_revision/pair_comparison/formal_validation.json)。

本次新增市场计算，直接复用此前模拟与DGP参数；全部四规格共同调用约4分49秒，未重估参数或重跑模拟。原始数据及逐次检查点保持在受忽略的本地目录中。

## 历史实验归档

原设计的计划、市场实验、校准结果与报告，以及已被替代的综合报告，统一从[历史归档索引](archive/README.md)访问，不纳入当前正式报告。旧结果的原路径作为复现工作副本保留，独立日期归档保存原文。

本轮沿用只同步 GitHub 的交付范围；计算服务器不受影响。V3 仍需用户明确要求恢复。
