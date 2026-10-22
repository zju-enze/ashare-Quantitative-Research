# A 股同业协整研究

**最终交付（2026-10-22，ENG-021）：V1/EG、V2/DH 综合最终报告已结合补充实验完成，旧公开结果与报告已按日期归档。V1 保留 110 对名义发现及历史校准失准，V2 保留 0 对名义发现及整体 inconclusive；补充实验完成 20,000 条路径/80,000 次检验。V3 继续暂停。**

从[最终结果总览](results_final/README.md)、[V1 最终报告](results_final/V1_FINAL_REPORT.md)、[V2 最终报告](results_final/V2_FINAL_REPORT.md)开始阅读；[机器结果](results_final/FINAL_RESULTS.json)和[159 文件历史归档](archive/v1_v2_before_final_20261022/README.md)提供逐项来源。旧统计输出保留原路径供复现，原报告已标注历史版本。本次只同步 GitHub，不同步计算服务器。

[V1-R / V2-R联合修订计划](EXPERIMENT_REVISION_PLAN_V1_V2.md)现已采用该DGP作为共同模拟对照：统一对数价格、取消逐股ADF门槛；主比较EG/DH固定1阶，另列EG-AIC与DH-7。四情景每情景5000次已完成并核对，历史结果及DGP估计复用。见[补充实验报告](results_revision/pair_comparison/REPORT.md)：主规格一阶EG/DH误拒率5.54%/5.06%，功效16.28%/8.56%；厚尾对照EG误拒率升至6.78%。这些是单对结果，尚未验证完整家族控制。

[固定自由度DGP校准](results_review/dgp_fixed_nu_2021_2025/REPORT.md)：3106条代理、6212规格完成；[机器规格](results_review/dgp_fixed_nu_2021_2025/dgp_spec.json)和生成器已保存。ρ约0.03037、备择φ约0.99292；主DGP通过稳定性、矩与秩的结构核对。个股约95%逐序列解贴近矩边界；单对有限样本误拒率与功效已由ENG-020补充验证，完整候选图及家族控制仍未验证。

[t自由度诊断报告](results_review/student_t_2021_2025/REPORT.md)：个股AR(1)-GARCH-t的ν中位数4.271，GJR敏感性规格4.279；市场、行业剩余、个股剩余代理分别约6.003、6.918、3.512。统一ν=5未得到普遍验证；代理识别和边界估计限制见报告，不自动将这些数值冻结为新DGP参数。

- 已采用empirical-pair-dgp-1作为共同模拟对照，先比较单对检验尺寸与功效；完整共享股票图和多重校正的校准另行设计。
- 两条修订路线统一采用对数复权价格，主比较取消逐股ADF预检门槛；EG方法内部的残差ADF仍保留。
- 重新评估DH的检出能力及经济含义清楚的较小校正域；具体家族、错误控制目标、功效要求、重复数与预算待讨论，不默认沿用GLOBAL或V3参数。
- 不再安排行业标签置换，也不将其作为发布配对清单的前提。新方案删除N1、N5、N6、N7，不将它们保留为必跑压力项；旧失准记录继续保留。M1含有同类N5波动断点，新方案不直接沿用其原断点设定。
- 原V1/V2结果、源码、协议和检查点保留。有证据的计算或解释错误据实修订并留痕；改变输入、DGP或方法形成的重评结果另行标识，不覆盖历史结果。

[当前安排与恢复条件](ENGINEERING_CHANGES.md) · [机器可读研究状态](RESEARCH_STATUS.json) · [已暂停的V3草案](EXPERIMENT_PLAN_V3.md)。V3须等用户明确要求恢复；下方旧入口仅服务历史复现，不构成当前运行指令。

**V2全量计算与核对已完成：67678个候选位置，GLOBAL-Holm名义发现0对。** 有效DH为42121对，预检占位25557对，最终数值占位0。正式校准18000面板、40889000次DH已完成，但C3-N0上界11.50%超过10%容忍上限，整体仍为证据不足；0发现不证明不存在协整。

V1、D1及全部正式校准结果保留。当前市场结果采用明确标记的名义口径，并修正了23对未使用递归前缀的提前拒绝；7阶、输入、校准样本和结论不变，首次市场结果单独保留。远端及研究第二、第三阶段未启动。

## 当前阅读顺序

|文档|用途|
|---|---|
|[最终结果总览](results_final/README.md)|本轮综合结论、原市场与补充实验的范围区别|
|[V1 最终报告](results_final/V1_FINAL_REPORT.md)|EG 原结果、历史失准、补充尺寸/功效与最终解释|
|[V2 最终报告](results_final/V2_FINAL_REPORT.md)|DH 原结果、校准不足、同阶比较与最终解释|
|[最终机器结果](results_final/FINAL_RESULTS.json)|来源可追溯的完成记录、逐格统计及配对差异|
|[旧结果和报告归档](archive/v1_v2_before_final_20261022/README.md)|159文件日期快照；原统计路径保留|
|[V1-R / V2-R补充报告](results_revision/pair_comparison/REPORT.md)|新增20,000条路径的尺寸、功效、同路径差异及复用/核对记录|
|[V1-R / V2-R联合修订计划](EXPERIMENT_REVISION_PLAN_V1_V2.md)|现行共同DGP、四情景、方法/选阶对照、指标、拟议规模和执行边界|
|[固定ν、有限矩DGP校准](results_review/dgp_fixed_nu_2021_2025/REPORT.md)|重新估计、个股参数与损失比较、已知真值的两股票DGP及结构核对|
|[t自由度诊断](results_review/student_t_2021_2025/REPORT.md)|使用冻结形成期数据的估计方法、结果、不确定性与DGP解释边界；非模拟实验|
|[原V2市场报告（历史）](results_v2/STAGE1_REPORT_V2.md)|完整计算、0名义发现、校准不足、工程修复与范围限制|
|[V2完成记录](results_v2/STAGE1_COMPLETION_V2.json)|机器可读执行及交付状态|
|[正式校准总报告](results_v2/CALIBRATION_REPORT_V2.md)|全部19项验收、跨规模功效及工程核对|
|[EXPERIMENT_PLAN_V2.md](EXPERIMENT_PLAN_V2.md)|已完成V2.1-DH版本的设计与执行记录；不等于当前复盘方案|
|[D1 开发试验报告](results_v2/simulation/D1_REPORT.md)|1500 面板完整结果、置信限、功效、实际资源与限制|
|[F0冻结记录](results_v2/F0_FREEZE.md)|实际冻结时间、用户接受的功效边界、固定规格及输入核对|
|[C1正式校准报告](results_v2/simulation/C1_REPORT.md)|15000面板完整结果、7项严格/2项容忍、功效及适用边界|
|[C1运行状态](results_v2/simulation/C1_status.json)|完整调用记录和阶段判定|
|[C2规模校准报告](results_v2/simulation/C2_REPORT.md)|2500面板、4项严格/1项容忍、M1功效5.60%|
|[C3实际几何报告](results_v2/simulation/C3_REPORT.md)|500面板完成，N0证据不足，M1功效0.597%|
|[DH_DEVELOPMENT.md](DH_DEVELOPMENT.md)|已有实现口径、工程验证及计时记录|
|[DH 开发报告与预算](results_dh_dev/20261019T200814/DH_DEVELOPMENT_REPORT.md)|实际结果；不代表通过统计校准|
|[RESEARCH_STATUS.json](RESEARCH_STATUS.json)|V1 历史状态及独立的 v2 状态块|
|[ENGINEERING_CHANGES.md](ENGINEERING_CHANGES.md)|工程安排、历史暂停/恢复与文档维护记录|
|[archive/README.md](archive/README.md)|被替代的设计、审稿和已完成的执行交接|

当前 V2 文件替代旧 defactor / bootstrap / Romano–Wolf 草案。历史提示词不构成当前执行命令。

## V2已完成版本的冻结规格（历史复现）

- 复用冻结输入 formation-2021-2025-v2：2021–2025、1212 日、2984 股、67678 对。
- 研究价格水平协整，不剥离公共因子；主模型接受无额外确定性漂移的限制。
- F0固定7个滞后差分向量；使用两方程相关性修正后的联合Q。
- 主校正 alpha=0.05；10% 仅为校准最大 FWER 容忍上限，严格通过、容忍通过、失败、证据不足分别报告。
- N1 不进入 V2 新主验收，其 V1 失准和覆盖局限继续披露。
- 候选家族在预检前冻结；预检/数值不可用保留 p=1 占位。
- 零发现合法，不按 beta、半衰期、未来表现或交易条件修改统计主清单。

已有 16 项 V1 测试及 7 项 DH 测试通过。主工程批次 84 个面板、7200 次检验，加 6 次计时求值，共 8280 次开发面板系统检验。N7 的 5 个冒烟面板中有 1 个出现假发现；样本太少，不认证 5% 或 10%。

D1及其 [开发协议](experiment_protocol_v2.json)保持原样，不进入正式验收。[正式冻结协议](experiment_protocol_v2_frozen.json)和C1原入口保留；7阶及慢回复功效边界已固定。C2/C3入口已新增，前续44项测试与新增5项市场专项测试通过；当前显式名义市场分支已执行并核对；整体校准仍为证据不足。

## V2历史正式入口（非当前运行安排）

F0及C1已完成。以下入口复用完整检查点，只补未完成任务；仅重建汇总可附加 --summarize-only：

~~~powershell
.\.venv\Scripts\python.exe -B -u run_calibration_v2.py --stage C1 --workers 8
~~~

该入口仅执行C1。汇总重建可附加 --summarize-only；工程首批的 --max-new 参数只限制单次新任务数，不改变15000面板总分母。

C2/C3使用独立的后续规模入口，前序必须完成并通过独立核对与统计门槛。当前C2固定2500面板，C3固定500面板；首批也计入总量，恢复时复用检查点：

~~~powershell
.\.venv\Scripts\python.exe -B -u run_scale_calibration_v2.py --stage C2 --workers 8
~~~

C3已按该顺序完成。各阶段不自动串联，F0/C1冻结文件保持原样；具体记录见ENG-013至ENG-015。

## 可复现的现有开发入口

D1固定为1500个面板；下列入口自动复用完整检查点，不自动接续其他阶段：

~~~powershell
.\.venv\Scripts\python.exe -B -u run_simulation_v2.py --stage D1 --workers 4
~~~

首批计时用同一命令附加 --max-new 15，随后去掉该参数恢复；仅重建汇总用 --summarize-only。源码、协议或环境不一致时拒绝混用已完成结果。高频状态与汇总见 [D1状态](results_v2/simulation/D1_status.json) 和 [D1汇总](results_v2/simulation/D1_summary.csv)。

在本项目目录使用已锁定的 Python 3.11 环境：

~~~powershell
.\.venv\Scripts\python.exe -B -u scripts\validate_dh_development.py
~~~

该命令执行有限工程面板并创建独立 results_dh_dev/ 时间戳目录，不运行正式校准、真实市场或远端。旧 V1 复现命令保存在 [V1 入口快照](archive/v1_handoffs_20261019/README_STAGE1_V1.md)。

## V1 结论与复现依据保留

V1 主结果是各 L2 分别按名义 5% Holm 校正后的 110 对发现，不能声称全市场真实 FWER 为 5%。S1 的 N1/N5/N6/N7，以及 S2 的 N1/N5/N6，均暴露明显失准；S2 固定 L2 的 FWER 分别约 52.0%–57.0%、16.6%–22.0%、53.2%–57.6%。这些模拟错误率不是市场 110 对中的错误比例。

|依据|位置|
|---|---|
|原计划与实施澄清|[EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md)、[REVIEW_AND_IMPLEMENTATION.md](REVIEW_AND_IMPLEMENTATION.md)|
|数据、复权和行业边界|[DATA_CONTRACT.md](DATA_CONTRACT.md)|
|原市场统计与主清单（历史）|[STAGE1_REPORT.md](results/STAGE1_REPORT.md)、[main_evidence.csv](results/main_evidence.csv)|
|全部校准与局限|[CALIBRATION_REPORT.md](results/CALIBRATION_REPORT.md)|
|完成记录|[STAGE1_COMPLETION.json](results/STAGE1_COMPLETION.json)|
|有效机器协议|[experiment_protocol.json](experiment_protocol.json)，V1 专用|
|早期实施/纠错与交接|[归档索引](archive/README.md)|

V1 的 source-covered 沪深存续连续交易样本、北交所未覆盖、行业历史重建、同源复权审计及非交易结论等限制继续有效。V2 不回填、删除或改写 V1 发现和校准失败。

## 输出隔离

V1的results/、.local/production/和.local/simulation/原位保留。D0输出在results_dh_dev/；D1与C1在results_v2/simulation/以各自前缀保存汇总，在.local/dh_v2/simulation/D1/和C1/分别保存完整配对与恢复检查点。C1/C2/C3均有完整结果，当前市场标签为formation-2021-2025-v2__dh-v2.1__used-prefix；首次市场运行原位保留。

原始授权数据和大规模中间结果继续本地保存。没有读取真实 2026 表现、运行交易回测或自动进入后续阶段。

[返回仓库总览](../../README.md) · [价值信号研究](../../VALUE_SIGNAL_RESEARCH.md)

## V2历史名义市场入口（非当前运行安排）

默认入口仍要求校准通过。本次已依据持续目标及ENG-014/015，显式保留C3证据不足并输出全量名义清单；不能将输出解释为校准通过或交易保证：

~~~powershell
.\.venv\Scripts\python.exe -B -u run_market_v2.py --workers 8 --nominal-if-inconclusive
~~~
