# BP单因子测试报告 LaTeX工程

本目录是独立的可编译工程。2026-10-30结项版为[main.pdf](main.pdf)，共17页；主源文件为`main.tex`，正文在`sections/`，表格在`tables/`，矢量图在`figures/`。编译不依赖父目录的原始股票数据。

最新版包含第5.1节分年度表现、第5.2节去极值方法敏感性及表S1的未舍入差值说明。[独立审阅汇总](reviews/codex-20261030/synthesis.md)与三份个人报告均已冻结。下方2026-10-28、2026-10-29条目为历史交付记录，其中旧PDF和本地备份路径不作为当前入口。

## 本机编译

Windows已配置MiKTeX/XeLaTeX，中文字体使用ctex的Windows字体集。在PowerShell中进入本目录执行：

```powershell
./build.ps1
```

脚本调用本机`xelatex`两遍，遇到失败立即停止；日志与中间文件在`build/`，成功后更新工程根目录的`main.pdf`。最终稿应直接编译现有TeX。`build_winsor_supplement.py`用于重新生成实验补充草稿，会覆盖作者对第5.2节的手工修订，结项稿不要重跑该生成器。Codex内置编辑器的预览编译曾因MiKTeX注册表访问权限失败，不影响命令行编译，也没有为此修改系统注册表。

## 内容与证据

- 重新阅读教材书197–200页（PDF211–214页）的单因子报告附录后组织正文。保留中文，使用正式股票池名称，摘要在一页以内。
- 三池C1/C2、年度C3、行业C4、D1–D10、行业中位数与规模相关诊断均纳入正文。宽表按字段拆分，原始数值与评价窗口不变。
- 主结果来源为`bp-v05-20261026-main`，方法0.5，原研究源码`38a5369`；去极值补充来源为`bp-v05-20261029-winsor-sensitivity`。`source-data/`只保存汇总CSV与来源说明。证券级数据不在本工程。
- `scripts/build_tables.py`与`scripts/build_figures.py`使用课程Python环境读取本工程汇总。正文可直接编辑，不由这些脚本覆盖；只改文字时无需重建表图或重跑实证。
- `reviews/`保存三份隔离审阅、编辑核对与汇总。原审阅稿针对冻结输入包，修正后仍保留原稿，不回写制造一致意见。

公开仓库保留报告、源文件、汇总结果及审阅文字。审阅用的教材摘录、重复输入包和页面截图，以及`backup/`、`build/`仅保留本地。审阅原文中的`packet/`位置是本地冻结包指针；当前公开证据对应本工程的同名源目录和项目的正式运行目录。

## 使用技能与范围

nature-writing采用manuscript/research/generic，nature-polishing用于中文学术表达和实际LaTeX版面；按照项目要求保留中文，没有套用英文翻译路线或期刊篇幅模板。nature-reviewer按用户本轮指定的三份隔离审阅加汇总执行，区别于此前Markdown交付的单份审阅。

原Markdown报告和正式实证结果继续保留；本次没有改变因子、股票池、窗口、成本、回归或分域规则，没有重跑完整实证。

## 2026-10-28 审阅后修订

- 依据`reviews/claude-20261027/`的三份独立审阅与审计修订正文、表与图；逐条对应见`reviews/claude-20261027/revision_log.md`。修订前的源文件、表、图、汇总数据、脚本与`main.pdf`完整备份在`backup/original-20261028/`，哈希清单为`backup/original-20261028.SHA256.txt`。
- 当前最新PDF为`main.pdf`（由`build/main.pdf`复制）。`bp_single_factor_report.pdf`仍是2026-10-26的旧导出，未覆盖；如需更新，运行`build.ps1`。
- 修订后的生成顺序为：`scripts/derive_interpretation.py`（从`source-data/`计算失效区间、多空两端分解等解读数字，输出`source-data/derived_*.csv`）、`scripts/build_tables.py`、`scripts/build_figures.py`，均在课程Python环境中运行，只读取本工程汇总。为此从正式运行复制了`ALL_A_layers_gross.csv`、`ALL_A_turnover.csv`、`HS300_monthly.csv`、`ZZ500_monthly.csv`、`D10_size1_turnover.csv`五个汇总文件到`source-data/`。
- 表格现在完全由`build_tables.py`生成，作者对C1a表注的手工修改已写回脚本；手工改动表格后须同步脚本，否则重跑会覆盖。图按印刷宽度绘制并以原尺寸插入，图内字号约8.5pt。


## 2026-10-29 去极值敏感性定向补充

新版为[去极值敏感性补充PDF](bp_single_factor_report_winsor_sensitivity_20261029.pdf)，共17页。第16页、第6节之前新增表S1及390字解读；原正文、原表图及摘要/结论不变。`main.pdf`和`bp_single_factor_report.pdf`均保留原文件。

新增块来自`../outputs/runs/bp-v05-20261029-winsor-sensitivity/`；逐月结果、MAD5复现及验收入口见该目录README。`source-data/winsor_sensitivity_summary.csv`为本次汇总副本，独立LaTeX编译仍不需要原始数据。

```powershell
# 在项目根目录、既有课程Python环境中生成新增块
python latex-report/scripts/build_winsor_supplement.py --run-id bp-v05-20261029-winsor-sensitivity
# 只输出带独立名称的新PDF，保留两份原PDF
./latex-report/build-winsor-sensitivity.ps1
```

本轮前完整报告快照在`backup/pre-winsor-20261029/`。仅`sections/05_annual.tex`增加标记包围的一处input引用；移除该新增引用块，原文件逐字节恢复。新表独立编号S1，不影响原表号。未重跑原表图生成器。
