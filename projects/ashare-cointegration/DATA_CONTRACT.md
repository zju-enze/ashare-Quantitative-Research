# 第一阶段输入与来源

所有证券行情、供应商响应、缓存及冻结输入保存在受忽略的 .local/ 下。
运行只请求2021-01-01至2025-12-31价格；因子事件允许向上市期回溯以取得期初种子。
当前历史身份/行业资料可以包含较晚的更新记录，统一标为当前历史重建。

## 行业来源的实施适配

用户确认无Tushare凭据并要求优先免费来源。经
[CNEquity源码](https://github.com/rootSunc/CNEquity/blob/e6e59918b8dbd479c04e743927e41554f2a535e8/src/cnequity/adapters/sw/industry_history.py)
及[a-stock-data](https://github.com/simonlin1212/a-stock-data/tree/29b07d2e37005b9fd568bca1262f6e572b5f9407)
定位到申万官网原始文件，实际计算直接读取官网记录，不把GitHub说明当数据验证。

- [行业变迁表](https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls)：股票代码、计入日期、行业代码、更新日期。
- [SW2021官方资料包](https://www.swsresearch.com/swindex/pdf/SwClass2021/SwClass.rar)：SwClassCode_2021.xls完整目录、SwClassStd2021.pdf及当时分类资料。
- 分类标准PDF日期2021-08-20，说明新版2021-07-30推出。目录实读为31个L1、134个L2、346个L3；代码与名称父子关系逐项验证，数量是观测结果，不作为硬编码筛选门槛。
- 使用官方分类代码（如480301），不与行业指数代码（如801xxx.SI）混接。

这是一张生效变更事件表，没有Tushare的is_new/in_date/out_date字段，因此不模拟N/Y分页。
每条计入记录自该时点起生效，直至同一股票的下一次计入；按左闭右开事件区间重建
2025-12-31收市后的归属。同一生效时点的冲突不能被排序覆盖。等价重复合并；
末次有效行业不在SW2021目录时排除。当前文件含早期版本变更，只有最终归属通过目录核验才纳入。
不按2026行业或ST状态回溯筛选。source_updated_at是供应商记录更新时间，不冒充公开发布时间。
没有证据证明这些当前重建记录在2025当时已经以同样内容发布。

## BaoStock

独立环境固定baostock 0.9.4。

| 文件 | 请求与用途 |
|---|---|
| sources/calendar.csv | query_trade_dates，2021—2025，is_trading_day=1 |
| sources/stock_basic.csv | query_stock_basic，保存上市/退市日期及证券类型；不使用当前status筛选2025 |
| sources/stock_asof_20251231.csv | query_all_stock(date=2025-12-31)，核对当时存在与返回名称 |
| market/{code}/raw.csv | adjustflag=3；date,code,close,preclose,volume,tradestatus,isST |
| market/{code}/hfq.csv | adjustflag=1；date,code,close |
| market/{code}/factors.csv | query_adjust_factor，1990-01-01至2025-12-31 |
| market/{code}/status.json | 请求终态、全部已查明排除标签、种子及复权差异 |

普通A股使用证券type=1与沪深普通A股代码范围；B股、指数、基金及存托凭证单列排除。
上海689存托凭证范围不能因type=1而纳入；已据上交所2025年九号公司公告核实实际遇到的689009。
BaoStock未覆盖的北交所不纳入主池，官方行业记录中观测到的北交所代码另列来源覆盖说明，
不把它们称为已验证的北交所完整总体。上游名称仅作标签；2025年底ST资格直接由当日日线isST判断。
连续性同时要求精确相同的1,212日共同日历、正有限价格、tradestatus=1、正成交量。
数据下载失败是未解决任务；有记录的停牌/缺日是不合格数据终态，两者分开。

## C1：不猜测舍入方式的记录值恒等验收

供应商字段的小数位数不足以证明潜在累计因子按半单位四舍五入。本实现不使用这一假设。
原始响应保留字符串，先用Decimal在原生后复权坐标逐行验证：

    Decimal(P_raw) × Decimal(F_returned) == Decimal(Q_API)

这里检验的是已返回数据的精确代数恒等式。比较误差界为0；不是声称潜在真实因子的舍入误差为0。
原始价四位、因子六位与直接报价十位的本轮响应使乘积可精确比较，不由显示位数推出舍入规则。
只接受恒等成立的记录，任何非零差异均记录并排除/调查，不根据统计结果选择容差。
供应商潜在因子的舍入规则仍未知；本检查只能证明所保存记录与直接接口的坐标相容。

累计因子按生效日向过去匹配，事件值直接替换，不重复连乘。首日事件先应用再存档分母；
未来事件不倒填。取得期初累计因子后，研究价格为P_raw×F/F_first。
转float64后的运算误差与前述Decimal恒等检查分开。audit_float_coordinates.py对冻结的3,616,608个数值
使用60位Decimal参考重建，记录实际绝对误差，并在正的正常范围binary64输入下核对
gamma_6=6u/(1-6u)、u=2^-53的转换/运算界；此界不用于放宽供应商记录值恒等条件。
累计因子比值不作为自动经济事件验收门槛，
所以没有把未经证明的半单位区间用于除法。已知公司行动用正式公告作针对性核对。

## 冻结与恢复

在任何ADF之前保存U.parquet、H.parquet、prices.npy、catalogue.parquet、stock_audit.parquet和freeze.json，
同时复制有效协议与生产源码。恢复时直接比较协议/统计内核字节；统计规格或输入纠错须另建run-id并记录纠错。
报告排版和元数据展示可以从冻结结果重新生成，不因此重算未改变的统计。原始来源流转账本保留在
stock_audit.parquet；stock_audit_report.parquet将非普通证券的行业显示为空，由UNKNOWN归集，避免指数与股票共用六位数字导致的无意义行业归类。
原始输入保持不变，当前任务不添加无后续用途的哈希。统计批次按固定H每1000对保存，
意外错误中止完整声明；同run-id恢复复用已完成批次。完整逐股和逐对表留在本地冻结目录。
