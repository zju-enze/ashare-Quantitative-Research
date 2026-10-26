"""Post-review checks of the typeset artifact, not a rerun of the factor study."""
from pathlib import Path
import json
import re
import pandas as pd
import pdfplumber
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    pdf = ROOT / 'bp_single_factor_report.pdf'
    pages = [re.sub(r'\s+', '', p.extract_text()) for p in PdfReader(pdf).pages]
    assert len(pages) == 16
    assert all(word in pages[0] for word in ['摘要', '关键词', '研究背景与因子简介'])
    all_text = '\n'.join(pages)
    markers = ['图A', '图B'] + [f'图D{i}' for i in range(1,11)] + ['表C1(a)', '表C1(b)', '表C2(a)', '表C2(b)', '表C3', '表C4(a)', '表C4(b)']
    locations = {key: [i+1 for i,p in enumerate(pages) if re.search(re.escape(key)+r'(?!\d)',p)] for key in markers}
    assert all(locations.values())
    sources = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'sections').glob('*.tex'))
    figures = re.findall(r'\{figures/([^}]+)\.pdf\}', sources)
    assert len(figures)==12 and len(set(figures))==12
    assert all((ROOT/'figures'/f'{name}.pdf').exists() for name in figures)
    assert not any(word in sources for word in ['全A', '股票至期', 'TODO', '待填写'])
    assert all(word in all_text for word in ['无风险收益率（RF）','复合年化收益率（CAGR）','普通最小二乘法（OLS）','加权最小二乘回归（WLS）','异方差与自相关稳健（HAC）'])
    d5_page=locations['图D5'][0]
    assert '该阶段没有继续积累优势' in pages[d5_page-1]
    d8_page=locations['图D8'][0]
    assert '超额稳定性并非最佳' in pages[d8_page-1]
    d10_page=locations['图D10'][0]
    assert '12.54' in pages[d10_page-1] and '5.31' in pages[d10_page-1] and '4.44' in pages[d10_page-1]
    # Catch a wrong data snapshot or scaled/cross-pool transcriptions during export.
    origin = ROOT.parent / 'outputs/runs/bp-v05-20261026-main'
    copied=[]
    for path in (ROOT/'source-data').glob('*.csv'):
        pd.testing.assert_frame_equal(pd.read_csv(path), pd.read_csv(origin/path.name))
        copied.append(path.name)
    assert all(value in all_text for value in ['0.0566','162/228','13.00','20.98','19/30','24/30','25/30','161/217','12/54'])
    for name, rows in [('C1',3),('C2',3),('C3',20),('C4',31)]:
        assert len(pd.read_csv(ROOT/'source-data'/f'{name}.csv'))==rows
    log = (ROOT/'build/main.log').read_text(encoding='utf-8',errors='replace')
    failures = re.findall(r'Overfull[^\n]*|Missing character[^\n]*|Float too large[^\n]*|[^\n]*undefined[^\n]*',log)
    assert not failures, failures
    small_text, outside = [], []
    with pdfplumber.open(pdf) as document:
        for i,page in enumerate(document.pages):
            for char in page.chars:
                if char['text'].strip():
                    # For our 90-degree axis labels, pdfminer calls glyph advance "size"; width is the em height.
                    small_text.append(char['size'] if char['upright'] else char['width'])
                    if char['x0'] < -1 or char['x1'] > page.width+1 or char['top'] < -1 or char['bottom'] > page.height+1:
                        outside.append(i+1)
    assert not outside
    assert min(small_text) >= 5
    result = dict(status='passed', pages=len(pages), abstract_pages=[1], figure_count=len(figures),
                  course_item_pages=locations, source_tables_unchanged=len(copied),
                  minimum_rendered_text_pt=round(min(small_text),3), out_of_page_text=outside,
                  compile_log_layout_errors=failures, reviewer_minor_fixes='definitions and D5/D8/D10 placement verified',
                  scope='Typeset transfer, required displays, page layout and fixed reviewer concerns; no raw-data/PIT re-audit')
    (ROOT/'reviews/delivery_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
