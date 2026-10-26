# BP单因子测试报告 LaTeX工程

本目录是独立的可编译工程。最终报告为`bp_single_factor_report.pdf`；主源文件为`main.tex`，正文在`sections/`，表格在`tables/`，矢量图在`figures/`。编译不依赖父目录的原始股票数据。

## 本机编译

Windows已配置MiKTeX/XeLaTeX，中文字体使用ctex的Windows字体集。在PowerShell中进入本目录执行：

```powershell
./build.ps1
```

脚本调用本机`xelatex`两遍，遇到失败立即停止；日志与中间文件在`build/`，成功后复制最终PDF到工程根目录。本轮命令行编译成功。Codex内置编辑器的预览编译曾因MiKTeX注册表访问权限失败，不影响已生成的独立PDF，也没有为此修改系统注册表。

## 内容与证据

- 重新阅读教材书197–200页（PDF211–214页）的单因子报告附录后组织正文。保留中文，使用正式股票池名称，摘要在一页以内。
- 三池C1/C2、年度C3、行业C4、D1–D10、行业中位数与规模相关诊断均纳入正文。宽表按字段拆分，原始数值与评价窗口不变。
- 实证唯一来源为`bp-v05-20261026-main`，方法0.5，原研究源码`38a5369`；`source-data/`只保存汇总CSV与来源说明。证券级数据不在本工程。
- `scripts/build_tables.py`与`scripts/build_figures.py`使用课程Python环境读取本工程汇总。正文可直接编辑，不由这些脚本覆盖；只改文字时无需重建表图或重跑实证。
- `reviews/`保存三份隔离审阅、编辑核对与汇总。原审阅稿针对冻结输入包，修正后仍保留原稿，不回写制造一致意见。

## 使用技能与范围

nature-writing采用manuscript/research/generic，nature-polishing用于中文学术表达和实际LaTeX版面；按照项目要求保留中文，没有套用英文翻译路线或期刊篇幅模板。nature-reviewer按用户本轮指定的三份隔离审阅加汇总执行，区别于此前Markdown交付的单份审阅。

原Markdown报告和正式实证结果继续保留；本次没有改变因子、股票池、窗口、成本、回归或分域规则，没有重跑完整实证。
