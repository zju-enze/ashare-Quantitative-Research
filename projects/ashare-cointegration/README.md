# A 股同业协整研究

**当前正式实验：在共同、由形成期数据估计的两股票对数价格 DGP 中比较 V1/EG 与 V2/DH。** 两条路线主规格均固定 1 阶，不设置逐股 ADF 入场门槛；EG 保留残差 ADF。正式报告只采用这一已讨论并完成的实验设计。V3 继续暂停。

## 正式交付

|入口|内容|
|---|---|
|[正式结果总览](results_final/README.md)|共同设计、主要结果与比较范围|
|[V1 / EG 正式报告](results_final/V1_FINAL_REPORT.md)|EG 固定 1 阶、AIC 敏感性、四情景尺寸与功效|
|[V2 / DH 正式报告](results_final/V2_FINAL_REPORT.md)|DH 固定 1 阶、7 阶敏感性、四情景尺寸与功效|
|[机器可读正式结果](results_final/FINAL_RESULTS.json)|本设计的全部统计与配对差异|
|[共同设计与执行记录](EXPERIMENT_REVISION_PLAN_V1_V2.md)|已经执行的方案、参数、随机设计、指标与运行范围|
|[工程安排](ENGINEERING_CHANGES.md)|ENG-022 的报告范围调整及执行历史|
|[研究状态](RESEARCH_STATUS.json)|当前正式报告状态和独立保留的历史执行记录|

## 已执行设计与主要结果

共同 DGP 为 empirical-pair-dgp-1：市场/行业/个股自由度 6/7/4.5，ρ≈0.03037，协整备择 φ≈0.99292。每条路径 1,212 个对数价格观测，预热 2,000 期。四情景分别为主 DGP 无协整/慢回复协整，以及只把个股 ν 改为 3.5 的两种厚尾对照。

每情景 5,000 条独立路径，四情景共 20,000 条；每条路径同时用于 EG-1、DH-1、EG-AIC、DH-7，共 80,000 次检验。工程样本不进入正式统计。

|5% 名义水平|V1 / EG 固定 1 阶|V2 / DH 固定 1 阶|
|---|---:|---:|
|主 DGP 误拒率|5.54%|5.06%|
|主 DGP 慢回复功效|16.28%|8.56%|
|个股 ν=3.5 误拒率|6.78%|4.62%|
|个股 ν=3.5 慢回复功效|16.48%|8.12%|

区间、拒绝计数及配对 MCSE 均在正式报告中列明。单对模拟不能证明完整共享股票图的家族错误控制；厚尾对照超出 DH 的矩假设范围。该设计下尚未执行真实市场检验、2026 评价或交易验证。

## 参数、运行与来源

- [自由度诊断](results_review/student_t_2021_2025/REPORT.md)：形成期数据上的参数依据。
- [固定自由度、有限 4.1 阶矩 DGP](results_review/dgp_fixed_nu_2021_2025/REPORT.md)与[完整精度规格](results_review/dgp_fixed_nu_2021_2025/dgp_spec.json)。
- [冻结运行协议](results_revision/pair_comparison/experiment_protocol.json)、[正式汇总](results_revision/pair_comparison/formal_summary.csv)、[同路径比较](results_revision/pair_comparison/formal_paired.csv)。
- [运行入口](run_pair_comparison.py)、[完成记录](results_revision/pair_comparison/COMPLETION.json)及[独立核对](results_revision/pair_comparison/formal_validation.json)。

本次只调整正式报告与材料组织，使用已经完成的结果，没有新模拟或参数重估。原始数据及逐次检查点保持在受忽略的本地目录中。

## 历史实验归档

原设计的计划、市场实验、校准结果与报告，以及已被替代的综合报告，统一从[历史归档索引](archive/README.md)访问，不纳入当前正式报告。旧结果的原路径作为复现工作副本保留，独立日期归档保存原文。

本轮沿用只同步 GitHub 的交付范围；计算服务器不受影响。V3 仍需用户明确要求恢复。
