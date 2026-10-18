from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .engine import METHODS


def charts(run,full,main,output):
    folder=output/"figures";folder.mkdir(exist_ok=True)
    plt.rcParams.update({"figure.dpi":120,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout="constrained")
    for ax,(label,part,domains) in zip(axes,[("T: same L3",full.loc[full.layer=="T"],["L3","L2","GLOBAL"]),
                                          ("H: complete candidates",full,["L2","GLOBAL"])]):
        positions=np.arange(len(domains));width=.25
        for i,method in enumerate(METHODS):
            values=[int(part[f"reject_{d}_{method}"].fillna(False).sum()) for d in domains]
            ax.bar(positions+(i-1)*width,values,width,label=method)
        ax.set_xticks(positions,domains);ax.set_title(label);ax.set_ylabel("Nominal discoveries")
        ax.legend(frameon=False)
    fig.suptitle("Fixed complete families; local L2 totals are not global FWER control")
    fig.savefig(folder/"correction_counts.png");plt.close(fig)
    if main.empty:return
    universe=pd.read_parquet(run/"U.parquet");codes={c:i for i,c in enumerate(universe.ts_code)}
    values=np.load(run/"prices.npy",mmap_mode="r")
    import json
    dates=pd.to_datetime(json.loads((run/"freeze.json").read_text())["calendar"])
    # Predeclared illustration rule: first candidate_id in the first three represented L2 families.
    examples=main.sort_values(["L2","candidate_id"]).groupby("L2",sort=True).head(1).head(3)
    for index,row in enumerate(examples.itertuples(),1):
        a=values[:,codes[row.A]];b=values[:,codes[row.B]]
        fitted=row.alpha+row.beta*b;residual=a-fitted
        fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout="constrained")
        axes[0].plot(dates,a,lw=.8,label=f"P* {row.A}")
        axes[0].plot(dates,fitted,lw=.8,label=f"alpha + beta P* {row.B}")
        axes[0].set_ylabel("Formation coordinate");axes[0].legend(frameon=False)
        axes[1].plot(dates,residual,lw=.8,color="#256d85");axes[1].axhline(0,color="grey",lw=.5)
        axes[1].set_ylabel("OLS residual")
        fig.suptitle(f"{row.candidate_id}: identification-period illustration, no trading claim")
        fig.savefig(folder/f"relation_{index}.png");plt.close(fig)
