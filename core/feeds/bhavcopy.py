"""Automated NSE FO Bhavcopy downloader and local Parquet partition manager.

Integrates jugaad-data to download and decompress derivatives bhavcopy archives,
normalizes both legacy and modern UDiff formats, and stores them as compact
Parquet partitions for the walk-forward engine and post-trade validation.
"""

from __future__ import annotations

import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from jugaad_data import nse

import config

logger = logging.getLogger(__name__)


def parse_date(d: Union[date, datetime, str]) -> date:
    """Helper to parse a date, datetime or date string into datetime.date."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    # Try ISO YYYY-MM-DD or DD-MM-YYYY or DD-Mon-YYYY
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(d, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unable to parse date string: {d}")


def normalize_bhavcopy_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw Bhavcopy DataFrame into a unified schema across legacy and UDiff formats."""
    df = df.copy()
    upper_cols = {c.strip().upper(): c for c in df.columns}

    # Case 1: Legacy NSE FO format
    if "INSTRUMENT" in upper_cols and "STRIKE_PR" in upper_cols:
        norm = pd.DataFrame()
        norm["symbol"] = df[upper_cols["SYMBOL"]].astype(str).str.strip()
        norm["instrument"] = df[upper_cols["INSTRUMENT"]].astype(str).str.strip()
        norm["expiry"] = df[upper_cols["EXPIRY_DT"]].astype(str).str.strip()
        norm["strike"] = pd.to_numeric(df[upper_cols["STRIKE_PR"]], errors="coerce").fillna(0.0)
        norm["option_type"] = df[upper_cols["OPTION_TYP"]].astype(str).str.strip().str.upper()
        norm["open"] = pd.to_numeric(df[upper_cols["OPEN"]], errors="coerce").fillna(0.0)
        norm["high"] = pd.to_numeric(df[upper_cols["HIGH"]], errors="coerce").fillna(0.0)
        norm["low"] = pd.to_numeric(df[upper_cols["LOW"]], errors="coerce").fillna(0.0)
        norm["close"] = pd.to_numeric(df[upper_cols["CLOSE"]], errors="coerce").fillna(0.0)
        norm["settle_price"] = pd.to_numeric(df[upper_cols["SETTLE_PR"]], errors="coerce").fillna(0.0)
        contracts_key = next((k for k in ("CONTRACTS", "TTL_TRD_QNTY") if k in upper_cols), None)
        norm["contracts"] = pd.to_numeric(df[upper_cols[contracts_key]], errors="coerce").fillna(0).astype(int) if contracts_key else 0
        norm["open_interest"] = pd.to_numeric(df[upper_cols["OPEN_INT"]], errors="coerce").fillna(0).astype(int)
        norm["change_in_oi"] = pd.to_numeric(df[upper_cols["CHG_IN_OI"]], errors="coerce").fillna(0).astype(int)
        norm["trade_date"] = df[upper_cols["TIMESTAMP"]].astype(str).str.strip()
        return norm

    # Case 2: Post-July 2024 UDiff format
    if "TRADDT" in upper_cols or "TCKRSYMB" in upper_cols or "STRKPRIC" in upper_cols:
        norm = pd.DataFrame()
        sym_key = next((k for k in ("TCKRSYMB", "FININSTRMACTLNM", "SYMBOL") if k in upper_cols), None)
        norm["symbol"] = df[upper_cols[sym_key]].astype(str).str.strip() if sym_key else ""
        inst_key = next((k for k in ("FININSTRMTP", "SGMT") if k in upper_cols), None)
        raw_inst = df[upper_cols[inst_key]].astype(str).str.strip() if inst_key else ""
        inst_map = {"IDF": "FUTIDX", "IDO": "OPTIDX", "STF": "FUTSTK", "STO": "OPTSTK"}
        norm["instrument"] = raw_inst.map(lambda x: inst_map.get(x, x))
        exp_key = next((k for k in ("XPRYDT", "XPIRTNDT", "FININSTRMACTLXPRYDT", "EXPIRY_DT") if k in upper_cols), None)
        norm["expiry"] = df[upper_cols[exp_key]].astype(str).str.strip() if exp_key else ""
        strk_key = next((k for k in ("STRKPRIC", "STRIKE_PR") if k in upper_cols), None)
        norm["strike"] = pd.to_numeric(df[upper_cols[strk_key]], errors="coerce").fillna(0.0) if strk_key else 0.0
        opt_key = next((k for k in ("OPTNTP", "OPTION_TYP") if k in upper_cols), None)
        norm["option_type"] = df[upper_cols[opt_key]].astype(str).str.strip().str.upper() if opt_key else ""
        open_key = next((k for k in ("OPNPRIC", "OPEN") if k in upper_cols), None)
        norm["open"] = pd.to_numeric(df[upper_cols[open_key]], errors="coerce").fillna(0.0) if open_key else 0.0
        high_key = next((k for k in ("HGHPRIC", "HIGH") if k in upper_cols), None)
        norm["high"] = pd.to_numeric(df[upper_cols[high_key]], errors="coerce").fillna(0.0) if high_key else 0.0
        low_key = next((k for k in ("LWPRIC", "LOW") if k in upper_cols), None)
        norm["low"] = pd.to_numeric(df[upper_cols[low_key]], errors="coerce").fillna(0.0) if low_key else 0.0
        close_key = next((k for k in ("CLSPRIC", "CLOSE") if k in upper_cols), None)
        norm["close"] = pd.to_numeric(df[upper_cols[close_key]], errors="coerce").fillna(0.0) if close_key else 0.0
        sttl_key = next((k for k in ("STTLMPRIC", "SETTLE_PR") if k in upper_cols), None)
        norm["settle_price"] = pd.to_numeric(df[upper_cols[sttl_key]], errors="coerce").fillna(0.0) if sttl_key else 0.0
        vol_key = next((k for k in ("TTLTRADGVOL", "CONTRACTS") if k in upper_cols), None)
        norm["contracts"] = pd.to_numeric(df[upper_cols[vol_key]], errors="coerce").fillna(0).astype(int) if vol_key else 0
        oi_key = next((k for k in ("OPNINTRST", "OPEN_INT") if k in upper_cols), None)
        norm["open_interest"] = pd.to_numeric(df[upper_cols[oi_key]], errors="coerce").fillna(0).astype(int) if oi_key else 0
        choi_key = next((k for k in ("CHNGINOPNINTRST", "CHG_IN_OI") if k in upper_cols), None)
        norm["change_in_oi"] = pd.to_numeric(df[upper_cols[choi_key]], errors="coerce").fillna(0).astype(int) if choi_key else 0
        td_key = next((k for k in ("TRADDT", "TIMESTAMP") if k in upper_cols), None)
        norm["trade_date"] = df[upper_cols[td_key]].astype(str).str.strip() if td_key else ""
        return norm

    # Fallback
    clean = df.copy()
    clean.columns = [c.strip().lower() for c in clean.columns]
    return clean


def get_partition_path(target_date: date, output_dir: Path | str = config.HISTORICAL_DATA_DIR) -> Path:
    """Generate partition path in data/historical/year=YYYY/month=MM/fo_YYYYMMDD.parquet."""
    base = Path(output_dir)
    month_dir = base / f"year={target_date.year}" / f"month={target_date.month:02d}"
    return month_dir / f"fo_{target_date.strftime('%Y%m%d')}.parquet"


def download_fo_bhavcopy(
    trade_date: Union[date, datetime, str],
    output_dir: Path | str = config.HISTORICAL_DATA_DIR,
    skip_if_present: bool = True,
) -> Path:
    """Download NSE FO Bhavcopy for a specific trade date and save as Parquet."""
    d = parse_date(trade_date)
    out_file = get_partition_path(d, output_dir)
    
    if skip_if_present and out_file.exists():
        logger.info(f"FO Bhavcopy for {d} already exists at {out_file}")
        return out_file
        
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        raw_csv_text = nse.bhavcopy_fo_raw(d)
    except Exception as e:
        raise FileNotFoundError(f"Failed to download FO Bhavcopy for {d}: {e}") from e
        
    if not raw_csv_text or not raw_csv_text.strip():
        raise ValueError(f"Received empty FO Bhavcopy response for date {d}")
        
    raw_df = pd.read_csv(io.StringIO(raw_csv_text))
    clean_df = normalize_bhavcopy_df(raw_df)
    
    clean_df.to_parquet(out_file, index=False)
    logger.info(f"Saved normalized FO Bhavcopy for {d} to {out_file} ({len(clean_df)} rows)")
    return out_file


def load_fo_bhavcopy(
    trade_date: Union[date, datetime, str],
    data_dir: Path | str = config.HISTORICAL_DATA_DIR,
    auto_download: bool = False,
) -> pd.DataFrame:
    """Load normalized FO Bhavcopy for a date, downloading if requested."""
    d = parse_date(trade_date)
    file_path = get_partition_path(d, data_dir)
    
    if not file_path.exists():
        if auto_download:
            file_path = download_fo_bhavcopy(d, output_dir=data_dir, skip_if_present=True)
        else:
            raise FileNotFoundError(f"Bhavcopy file not found at {file_path}. Run with auto_download=True.")
            
    return pd.read_parquet(file_path)


def filter_nifty_options(
    df: pd.DataFrame,
    expiry: Optional[Union[str, date]] = None,
    strike: Optional[float] = None,
    option_type: Optional[str] = None,
) -> pd.DataFrame:
    """Filter normalized Bhavcopy DataFrame specifically for NIFTY options."""
    # Match symbol NIFTY
    mask = df["symbol"].str.upper() == "NIFTY"
    
    # Exclude futures (option_type should be CE or PE)
    if "option_type" in df.columns:
        mask &= df["option_type"].isin(["CE", "PE"])
        
    if expiry is not None:
        exp_str = expiry.strftime("%d-%b-%Y") if isinstance(expiry, (date, datetime)) else str(expiry).strip()
        mask &= df["expiry"].str.upper() == exp_str.upper()
        
    if strike is not None:
        mask &= (df["strike"] - float(strike)).abs() < 1e-4
        
    if option_type is not None:
        mask &= df["option_type"].str.upper() == option_type.strip().upper()
        
    return df[mask].reset_index(drop=True)
