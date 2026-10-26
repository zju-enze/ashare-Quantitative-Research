"""Download selected issuer notices for terminal valuation review."""

import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import pandas as pd
import requests


def main():
    root = Path(__file__).resolve().parents[1]
    private = root / ".local/data_repairs"
    folder = private / "terminal_sources/documents"
    folder.mkdir(exist_ok=True)
    selected = pd.read_csv(private / "terminal_first_candidates.csv", dtype=str)
    assert selected.pdf.notna().all()
    session = requests.Session()
    records = []
    for number, row in enumerate(selected.itertuples(index=False), 1):
        name = Path(urlsplit(row.pdf).path).stem
        pdf, txt = folder / (name + ".pdf"), folder / (name + ".txt")
        if not pdf.exists():
            response = session.get(row.pdf, timeout=30)
            response.raise_for_status()
            assert response.content.startswith(b"%PDF"), f"Not a PDF: {row.pdf}"
            temporary = pdf.with_suffix(".pdf.part")
            temporary.write_bytes(response.content)
            temporary.replace(pdf)
        if not txt.exists():
            extraction = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=True, capture_output=True)
            if extraction.stderr:
                txt.with_suffix(".warnings.txt").write_bytes(extraction.stderr)
        text = txt.read_text(encoding="utf-8")
        records.append(dict(ts_code=row.ts_code, signal_names=row.signal_names, title=row.title,
                            publication_date=row.date, url=row.pdf, text_characters=len(text),
                            document_file=str(pdf.relative_to(private)), text_file=str(txt.relative_to(private))))
        pd.DataFrame(records).to_csv(private / "terminal_documents.csv", index=False, encoding="utf-8-sig")
        if number == 1 or number % 10 == 0 or number == len(selected):
            print(f"Terminal documents {number}/{len(selected)}: {row.ts_code}, {len(text)} text characters", flush=True)
    summary = dict(completed=True, documents=len(records), empty_text_documents=sum(r["text_characters"] == 0 for r in records),
                   scope="Regular-exit notices precede final trade; merger notices are bounded by planned valuation date. Acquisition is not valuation approval")
    (root / "outputs/repairs/terminal_document_acquisition.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
