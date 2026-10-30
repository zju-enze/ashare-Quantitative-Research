# 独立编辑一致性核对

2026-10-30。三份个人报告全部完成并冻结后，由主执行者单独核对。未把发现回传给评阅者，未改写个人报告。本记录不是第四份审阅，不能据此制造审阅共识。

对象为 `packet/main.pdf` 的17页冻结稿。以下文件指针以 `packet/` 为起点，数值记录在本目录 [audit_numbers.json](audit_numbers.json)。只读取现有CSV和代码，不重新运行证券级实证。数值比较采用相对容差 `1e-10`、绝对容差 `1e-12`。

## AUD-01 主要统计量及范围

- **Status** `passed`
- **Location / claim pointer** 摘要、第4.1和4.2节、C1与C2中的三池回归、IC和多空绩效。
- **Evidence pointer** `source-data/C1.csv`、`C2.csv`、三个股票池的 `*_monthly.csv`。
- **Check** 从月度序列重算C1全部指标及C2多空CAGR、夏普、最大回撤与胜率。若不一致，应追查统计定义或改正报告数字。另核对月份唯一且连续、IC界限及形成数与响应数。
- **Result** 三池各228期、2007-02至2026-01连续，形成数与响应数逐期相等；无整行重复月度结果，IC均在合法范围。重算值与机器汇总一致。全部A股平均IC为0.0565835041，正IC为162/228，ICIR为0.5502655180，多空CAGR为12.99991139%、夏普为1.1495538694、最大回撤为−15.66084872%。
- **Impact / resolution test** 未发现需要修正的主结果。维持稿件规定的未年化ICIR和样本标准差定义即可。
- **Reviewer overlap** 三份个人报告均核对并支持主要数量，此处是独立编辑确认，不构成新的问题共识。

## AUD-02 成本、分解与年度口径

- **Status** `passed`
- **Location / claim pointer** 第3.2节双腿成本与两端分解、第4.2节约59%的空头贡献、第5.1节C3年度解读。
- **Evidence pointer** `source-data/ALL_A_layers_gross.csv`、`ALL_A_layers_net.csv`、`ALL_A_turnover.csv`、`ALL_A_monthly.csv`、`C3.csv`、`derived_C3_decomposition.csv`。
- **Check** 核对层净收益等于毛收益减各层费用，多空等于毛收益差再扣双腿费用，两部分之和等于月度多空净收益。按年度重算复利收益、胜率、平均IC及两端算术贡献。若不成立，正文归因和年度解释需改正。
- **Result** 恒等式最大绝对差为 `2.78e-17`。多头与空头部分算术年化分别为5.3081577745和7.5860434212个百分点，合计12.8942011957个百分点，空头占58.83298474%。18个完整年度中多空正收益14年、复利多头超额为正13年，两者相关系数0.9394137009。年度表和派生分解均一致。
- **Impact / resolution test** 算术分解与CAGR的差异不是错误。现稿已区分其口径，不需改数或重跑。
- **Reviewer overlap** R1、R2均明确支持该分解；R3认可收益概念的区分。无相关未解决问题。

## AUD-03 行业、市值域和层序

- **Status** `passed`
- **Location / claim pointer** 摘要、第4.5至4.7节的行业计数与分层排序。
- **Evidence pointer** `source-data/C4.csv`、`ALL_A_layer_stats.csv`、`D9_layer_stats.csv`、`D10_size1_layer_stats.csv`至`D10_size3_layer_stats.csv`。
- **Check** 用实际列值核对Q5行业名次和完整行业分母，再核对最高IR、最浅相对回撤及相邻层递增数。若与正文最高级或计数不符，应改局部表述。
- **Result** 30个完整行业各54期，Q5超额为正25个，排名第一19个、前二24个。Q4的IR确为最高，相对净值最大回撤确为最浅。D9有9/9相邻层递增，D10低、中、高市值域分别为9/9、9/9和7/9。行业排名、相关系数与胜率范围未见异常。
- **Impact / resolution test** 正文这些排序和数量正确。不能据描述性计数另行声称经过行业多重检验，现稿已保留该推断边界。
- **Reviewer overlap** 三份报告均支持主要行业计数；无需要修正的对应问题。

## AUD-04 去极值比较及精度

- **Status** `passed`
- **Location / claim pointer** 第5.2节表S1及解释段落。
- **Evidence pointer** `sensitivity/summary.csv`、三方案目录中的 `monthly.csv`、`layers_gross.csv`、`layers_net.csv`和`turnover.csv`，以及 `source-data/ALL_A_monthly.csv`。
- **Check** 从三方案逐月结果重算IC均值、ICIR、平均回归系数、多空CAGR、Q5算术年化超额及算术毛收益和成本。核对共享月份、形成数及基准，避免把样本或基准变化误当去极值效应；比较MAD5与主结果共有月度列。若不一致，应先追查比较口径。
- **Result** 三方案均为228期和686,280个股票期，逐月形成数与基准相同，MAD5共有月度列与主结果一致。重算值符合表S1来源，三方案五层CAGR均递增。分位数Q5超额为5.5537786807个百分点，MAD5为5.3081577745个百分点，未舍入之差为0.2456209062个百分点，保留两位小数正确得到0.25。表注已经明确差值按未舍入结果计算。两种MAD回归均值同显0.40%也只是显示精度，并非底层结果重复。
- **Impact / resolution test** 没有算术错误或显示矛盾，不再要求修改0.25。比较限于所列三种方案，不能据此推出所有预处理或样本外均稳健。
- **Reviewer overlap** 三份报告均认可敏感性数值与结论边界，没有把0.25列为问题。

## AUD-05 形成顺序及残差定义

- **Status** `passed`
- **Location / claim pointer** 第1节表1、第3.1和3.2节的形成顺序、残差和分层定义。
- **Evidence pointer** `code/bp_core.py` 的 `form_cross_section`、`assign_layers`、`evaluate_layers`，以及 `RESEARCH_SPEC.md` 第3节。
- **Check** 查看形成函数是否混入未来收益、分层是否在连接响应之前完成、替代去极值是否又被固定MAD5覆盖。若存在这类顺序问题，会影响比较的解释。另针对R3-m1核对残差的正式定义。
- **Result** 形成函数只选择信号字段，去极值后的BP减OLS拟合值形成 `f_neu`，分层先于 `ret_fwd` 连接；各方案使用各自缩尾结果估计残差。现稿表1已明确Q5为高残差层，第3.2节定义了残差并说明负残差有效。定义与代码一致。
- **Impact / resolution test** 未发现形成顺序或信号定义错误。R3-m1建议增加经济含义解释有助于非专业读者，但属于可选澄清，不宜升级为技术缺陷或定稿阻断项。
- **Reviewer overlap** 只有R3-m1提出易读性建议。R1、R2未将现有定义列为问题，不构成共识修改。

## AUD-06 原始数据与外推边界

- **Status** `not_assessable`
- **Location / claim pointer** 第3.1节的历史样本和端点政策，第6节及附录A的数据、成本和推断限制。
- **Evidence pointer** 冻结包 `READ_ME_FIRST.md` 的材料范围，正文相关段落，`sensitivity/run_manifest.json` 的输入登记。
- **Check** 判断所提供资料能否独立核验原始证券级点时性、端点公告与实盘成交。若证据缺失，只保留明确的评价边界，不把缺失本身认定为错误。
- **Result** 本包没有这些原始材料，不能作相应认证。逐月汇总和静态代码检查不替代证券级重建。现稿已披露历史版本、简化成本、HAC及样本外等限制。
- **Impact / resolution test** 无需为课程候选结论扩大研究范围。R3-m2指出第6节“可获得”容易被理解为未来可得收益，建议改成“本历史样本中的算术年化超额”。5.31这一数值本身正确。此项为局部措辞建议，不是发现了预测保证或实证失效。
- **Reviewer overlap** 三位均保留外推限制，只有R3-m2把该句单独列为Minor；不称为三方问题共识。

## 核对结论

没有新增确认的算术错误、聚合口径错误、疑似重复结果或需重跑的技术问题。两条文字建议均来自Reviewer 3，其中残差解释为可选澄清，历史收益措辞建议优先收窄。个人报告保持冻结。此结论只适用于所给稿件、汇总结果和可见代码，不代表原始数据认证。
