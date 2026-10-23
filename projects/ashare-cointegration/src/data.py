"""Official SW2021 event history and BaoStock recorded-price audits."""
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd

# 689 is the STAR depositary-receipt range, not ordinary A shares.
ORDINARY_CODE_PATTERN = r"^(sh\.(60|688)|sz\.(00|30))"


def industry_snapshot(source):
    catalogue = pd.read_excel(source/"SwClassCode_2021.xls",dtype=str)
    catalogue.columns=["industry_code","L1_name","L2_name","L3_name"]
    catalogue["level"]=np.where(catalogue.L3_name.notna(),"L3",
                                np.where(catalogue.L2_name.notna(),"L2","L1"))
    if catalogue.industry_code.duplicated().any():
        raise ValueError("Conflicting industry catalogue")
    l3=catalogue.loc[catalogue.level=="L3"].copy()
    l3["L1"]=l3.industry_code.str[:2]+"0000"
    l3["L2"]=l3.industry_code.str[:4]+"00"
    for parent,level in [("L1","L1"),("L2","L2")]:
        parents=catalogue.loc[catalogue.level==level].set_index("industry_code")
        if not l3[parent].isin(parents.index).all():
            raise ValueError("Missing catalogue parent")
        if not (l3[parent+"_name"].to_numpy()==parents.loc[l3[parent],parent+"_name"].to_numpy()).all():
            raise ValueError("Catalogue parent/name mismatch")
    history=pd.read_excel(source/"StockClassifyUse_stock_live.xls",dtype=str)
    history.columns=["symbol","effective_from","industry_code","source_updated_at"]
    history["effective_from"]=pd.to_datetime(history.effective_from,errors="raise")
    history=history.loc[history.effective_from<pd.Timestamp("2026-01-01")].copy()
    history=history.drop_duplicates(["symbol","effective_from","industry_code"])
    last=history.groupby("symbol").effective_from.transform("max")
    active=history.loc[history.effective_from==last].copy()
    conflicts=active.symbol[active.symbol.duplicated(keep=False)].unique()
    active=active.loc[~active.symbol.isin(conflicts)]
    active=active.merge(l3,on="industry_code",how="left",validate="many_to_one")
    active=active.rename(columns={"industry_code":"L3"})
    active["snapshot_type"]="reconstructed_from_current_official_history"
    return catalogue,active,conflicts


def initial_universe(source):
    catalogue,industry,conflicts=industry_snapshot(source)
    basic=pd.read_csv(source/"stock_basic.csv",dtype=str).fillna("")
    asof=pd.read_csv(source/"stock_asof_20251231.csv",dtype=str)
    if basic.code.duplicated().any() or asof.code.duplicated().any():
        raise ValueError("Duplicate source security identity")
    asof_codes=set(asof.code)
    asof_ordinary=set(asof.loc[asof.code.str.match(ORDINARY_CODE_PATTERN),"code"])
    if asof_ordinary-set(basic.code):
        raise ValueError("As-of ordinary shares missing from identity response")
    dates=pd.read_csv(source/"calendar.csv",dtype=str)
    calendar=dates.loc[dates.is_trading_day=="1","calendar_date"].tolist()
    if len(calendar)!=len(set(calendar)) or calendar!=sorted(calendar):
        raise ValueError("Invalid trading calendar")
    basic["symbol"]=basic.code.str[3:]
    basic["ts_code"]=basic.symbol+"."+basic.code.str[:2].str.upper()
    basic["name"]=basic.code.map(asof.set_index("code").code_name).fillna(basic.code_name)
    basic=basic.merge(industry,on="symbol",how="left",validate="many_to_one")
    ordinary=(basic.type=="1") & basic.code.str.match(ORDINARY_CODE_PATTERN)
    labels=[]
    for i,r in basic.iterrows():
        reasons=[]
        if not ordinary.iloc[i]: reasons.append("instrument_or_uncovered_market")
        if not r.ipoDate or r.ipoDate>calendar[0]: reasons.append("listing_history")
        if r.code not in asof_codes or (r.outDate and r.outDate<="2025-12-31"):
            reasons.append("end_2025_survival_or_unknown")
        if r.symbol in conflicts or pd.isna(r.L2): reasons.append("classification")
        labels.append(reasons)
    basic["exclusion_tags"]=labels
    basic["primary_exclusion"]=basic.exclusion_tags.map(lambda x:x[0] if x else None)
    basic["raw_data_status"]="not_checked";basic["adjustment_status"]="not_checked"
    basic["end_ST_status"]="not_checked"
    return basic,catalogue,calendar


def audit_quotes(raw,hfq,factors,calendar):
    """Zero-tolerance Decimal identity, no guessed latent rounding model."""
    reasons=[]
    info=dict(raw_data_status="failed",adjustment_status="not_checked",
              end_ST_status="unknown",N_rows=len(raw),adjustment_max_decimal_error=None)
    last=raw.loc[raw.date==calendar[-1]]
    if len(last)==1 and last.isST.iloc[0] in ("0","1"):
        info["end_ST_status"]="ST" if last.isST.iloc[0]=="1" else "non_ST"
    if info["end_ST_status"]!="non_ST":
        reasons.append("end_2025_ST_or_unknown")
    prices=pd.to_numeric(raw.close,errors="coerce")
    volume=pd.to_numeric(raw.volume,errors="coerce")
    if (raw.date.tolist()!=calendar or not np.isfinite(prices).all() or not (prices>0).all()
        or not raw.tradestatus.eq("1").all() or not (volume>0).all()):
        reasons.append("raw_data_and_continuity")
        return info,reasons,None
    info["raw_data_status"]="passed"
    if hfq is None or factors is None:
        return info,reasons,None
    if hfq.date.tolist()!=calendar:
        info["adjustment_status"]="direct_calendar_mismatch"
        return info,reasons+["adjustment"],None
    factors=factors.drop_duplicates().sort_values("dividOperateDate")
    if factors.dividOperateDate.duplicated().any():
        info["adjustment_status"]="conflicting_factor_events"
        return info,reasons+["adjustment"],None
    factors["date"]=pd.to_datetime(factors.dividOperateDate)
    raw=raw.copy();raw["date_dt"]=pd.to_datetime(raw.date)
    expanded=pd.merge_asof(raw,factors[["date","dividOperateDate","backAdjustFactor"]],
                           left_on="date_dt",right_on="date",direction="backward")
    if expanded.backAdjustFactor.isna().any():
        info["adjustment_status"]="missing_historical_seed"
        return info,reasons+["adjustment"],None
    f=pd.to_numeric(expanded.backAdjustFactor,errors="coerce")
    if not np.isfinite(f).all() or not (f>0).all():
        info["adjustment_status"]="nonpositive_or_nonfinite_factor"
        return info,reasons+["adjustment"],None
    errors=[abs(Decimal(p)*Decimal(fac)-Decimal(q)) for p,fac,q in
            zip(raw.close,expanded.backAdjustFactor,hfq.close)]
    maximum=max(errors)
    info.update(adjustment_max_decimal_error=str(maximum),
                seed_factor=str(expanded.backAdjustFactor.iloc[0]),
                seed_effective_date=expanded.dividOperateDate.iloc[0],
                factor_events=len(factors),ever_ST=bool(raw.isST.eq("1").any()),
                adjustment_comparison="native exact recorded-decimal identity",
                adjustment_bound="0 in recorded-decimal coordinates")
    if maximum!=0:
        info["adjustment_status"]="recorded_decimal_identity_mismatch"
        return info,reasons+["adjustment"],None
    info["adjustment_status"]="passed_recorded_coordinate"
    adjusted=prices.to_numpy(float)*f.to_numpy(float)/f.iloc[0]
    return info,reasons,adjusted
