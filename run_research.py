"""Execute and save the integrated A-share research notebook top-to-bottom."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import nbformat
from nbclient import NotebookClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Directory containing the documented Tushare-format Parquet files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    os.environ["ASHARE_DATA_DIR"] = str(args.data_dir.resolve())
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    started = time.perf_counter()
    record_path = root/"results"/"execution.json"
    record_path.write_text(json.dumps({"status": "running"})+"\n", encoding="utf-8")
    path = root/"notebooks"/"ashare_value_signal_robustness.ipynb"
    print(f"START {path.name}", flush=True)
    try:
        notebook = nbformat.read(path, as_version=4)
        client = NotebookClient(notebook, timeout=3600, kernel_name="python3",
                                resources={"metadata": {"path": str(root)}})
        try:
            client.execute()
        finally:
            nbformat.write(notebook, path)
    except Exception:
        record_path.write_text(json.dumps({"status": "failed", "notebook": path.name})+"\n", encoding="utf-8")
        raise
    print(f"PASS {path.name} ({time.perf_counter()-started:.1f}s elapsed)", flush=True)
    record = {"status": "passed", "notebooks": 1, "notebook": path.name,
              "elapsed_seconds": round(time.perf_counter()-started, 1),
              "completed_utc": pd_utc_now()}
    record_path.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


def pd_utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
