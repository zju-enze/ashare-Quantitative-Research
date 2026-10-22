"""Standalone research figures from independently reconciled C1/C2/C3 summaries."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"C1": "#244A73", "C2": "#BA7A2A", "C3": "#6E715A"}


def main():
    folder = ROOT/"results_v2/simulation"
    protocol = json.loads((ROOT/"experiment_protocol_v2_frozen.json").read_text(encoding="utf-8"))
    rows, power = [], []
    for stage, repeats, pairs in (("C1", 1000, 180), ("C2", 500, 1740), ("C3", 100, 67678)):
        check = json.loads((folder/f"{stage}_validation.json").read_text(encoding="utf-8"))
        assert check["status"] == "passed_engineering_and_summary_reconciliation"
        summary = pd.read_csv(folder/f"{stage}_summary.csv").set_index("scenario")
        required = protocol["acceptance"]["required_C1_scenarios" if stage == "C1" else "required_C2_C3_scenarios"]
        selected = summary.loc[required]
        assert selected.complete.all() and selected.B.eq(repeats).all()
        assert np.isfinite(selected[["FWER", "FWER_upper95"]].to_numpy()).all()
        assert selected.FWER_upper95.ge(selected.FWER).all()
        for scenario, row in selected.iterrows():
            rows.append(dict(stage=stage, scenario=scenario, B=repeats,
                             FWER=row.FWER, U=row.FWER_upper95))
        row = summary.loc["M1"]
        assert row.power_B == repeats and row.conditional_power_B > 1
        power.append(dict(stage=stage, pairs=pairs, power=row.power, MCSE=row.power_MCSE,
                          conditional=row.conditional_power, conditional_MCSE=row.conditional_power_MCSE))
    assert len(rows) == 19 and len(power) == 3
    output = ROOT/"results_v2/figures"
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#666666",
        "text.color": "#252525", "axes.labelcolor": "#252525", "figure.facecolor": "white"})

    fig, ax = plt.subplots(figsize=(9, 8.5))
    for y, row in enumerate(rows):
        color = COLORS[row["stage"]]
        estimate, upper = 100*row["FWER"], 100*row["U"]
        ax.plot([estimate, upper], [y, y], color=color, lw=1.3)
        ax.scatter(estimate, y, color=color, s=30, marker="o", zorder=3, clip_on=False)
        ax.scatter(upper, y, facecolor="white", edgecolor=color, s=42, marker=">", zorder=3)
        ax.text(upper+.16, y, f"U {upper:.2f}%", va="center", fontsize=9, color=color)
    ax.set_yticks(range(len(rows)), [f"{r['stage']}  {r['scenario']}" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(12, max(100*r["U"] for r in rows)+2))
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_xlabel("FWER and one-sided 95% upper bound")
    ax.axvline(5, color="#4B4B4B", lw=1, ls="--")
    ax.axvline(10, color="#4B4B4B", lw=1, ls=":")
    for y in (8.5, 13.5):
        ax.axhline(y, color="#DDDDDD", lw=.7)
    ax.grid(axis="x", color="#E8E8E8", lw=.6)
    ax.set_axisbelow(True)
    ax.set_title("Error control across the 19 predeclared calibration units", loc="left", pad=34)
    ax.text(0, 1.015, "Dot: observed FWER    Open triangle: upper bound    Guides: 5% / 10%",
            transform=ax.transAxes, fontsize=9, va="bottom")
    fig.text(.13, .035, "C1: 1,000 panels/unit; C2: 500; C3: 100. Clopper-Pearson one-sided 95% bounds.\n"
             "Bounds are not claimed simultaneous. No unconditional real-market guarantee.", fontsize=8.5)
    fig.subplots_adjust(left=.13, right=.97, bottom=.13, top=.9)
    fig.savefig(output/"calibration_fwer.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    x = np.arange(3)
    for shift, field, error, color, label, fill in [
        (-.07, "power", "MCSE", "#244A73", "Unconditional power", "#244A73"),
        (.07, "conditional", "conditional_MCSE", "#BA7A2A", "Conditional power", "white")]:
        values = np.array([100*r[field] for r in power])
        uncertainty = np.array([100*r[error] for r in power])
        assert np.isfinite(values).all() and np.isfinite(uncertainty).all()
        ax.errorbar(x+shift, values, yerr=uncertainty, fmt="o", color=color, mfc=fill,
                    markersize=6, capsize=4, lw=1.2, label=label)
    ax.set_xticks(x, [f"{r['stage']}\n{r['pairs']:,} pairs" for r in power])
    ax.set_xlim(-.45, 2.45)
    ax.set_ylim(bottom=0)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_ylabel("M1 detection power")
    ax.set_title("M1 detection across predeclared geometries", loc="left", pad=14)
    ax.grid(axis="y", color="#E8E8E8", lw=.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right")
    fig.text(.11, .035, "Independent-panel means; bars show +/- 1 MCSE, not confidence intervals.\n"
             "Geometries and alternative-pair counts differ; no causal attribution to family size alone.", fontsize=8.5)
    fig.subplots_adjust(left=.11, right=.98, bottom=.23, top=.88)
    fig.savefig(output/"power_by_geometry.png", dpi=180)
    plt.close(fig)
    print(json.dumps(dict(figures=[str(output/"calibration_fwer.png"), str(output/"power_by_geometry.png")],
                          required_units=len(rows), power_geometries=len(power))))


if __name__ == "__main__":
    main()
