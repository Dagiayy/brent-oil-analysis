"""Transform + Load steps: raw prices -> analysis-ready log-return series.

This module is the piece that was missing from the original project: the
README documented an EDA notebook that would produce
``data/processed/brent_log_returns.csv``, but no such notebook or script
existed, so both the change-point model and the dashboard API had nothing
to read. ``build_processed_prices`` is the single source of truth for that
transformation, used by the CLI pipeline, the notebooks, and the tests.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.quality import DataQualityReport, check_price_quality
from src.utils import get_logger

logger = get_logger(__name__)


def deduplicate_and_reindex(df: pd.DataFrame, date_col: str = "Date") -> pd.DataFrame:
    """Collapse duplicate trading dates and drop exact duplicate rows."""
    df = df.drop_duplicates(subset=[date_col], keep="last")
    df = df.sort_values(date_col).reset_index(drop=True)
    return df


def compute_log_returns(df: pd.DataFrame, price_col: str = "Price") -> pd.DataFrame:
    """Add a Log_Return column: log(P_t / P_{t-1}).

    Log returns are used instead of raw price deltas because they are
    approximately stationary and additive across time, which is what the
    downstream ADF test and Bayesian change-point model require.
    """
    df = df.copy()
    df["Log_Return"] = np.log(df[price_col] / df[price_col].shift(1))
    n_before = len(df)
    df = df.dropna(subset=["Log_Return"]).reset_index(drop=True)
    logger.info("Computed log returns (%d -> %d rows after dropping first-day NaN)", n_before, len(df))
    return df


def add_rolling_volatility(df: pd.DataFrame, window: int = 21) -> pd.DataFrame:
    """Add an annualized rolling realized-volatility column for EDA/analysis."""
    df = df.copy()
    df[f"Volatility_{window}d"] = df["Log_Return"].rolling(window).std() * np.sqrt(252)
    return df


def build_processed_prices(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, DataQualityReport]:
    """Run the full Validate -> Transform pipeline on raw price data.

    Returns the processed dataframe (Date, Price, Log_Return, rolling
    volatility) alongside a data quality report for lineage/audit purposes.
    """
    quality_report = check_price_quality(raw_df)

    df = deduplicate_and_reindex(raw_df)
    df = compute_log_returns(df)
    df = add_rolling_volatility(df)
    return df, quality_report


def save_processed_prices(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    logger.info("Wrote %d processed rows to %s", len(out), path)


def save_processed_events(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["Start Date"] = out["Start Date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    logger.info("Wrote %d processed events to %s", len(out), path)
