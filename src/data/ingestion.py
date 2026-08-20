"""Extract step: load and schema-validate the raw source files.

Two raw sources feed this project:
  * data/raw/BrentOilPrices.csv - daily Brent spot price, 1987-present.
  * data/events.xlsx            - curated list of ~15 major geopolitical /
                                   OPEC / macroeconomic events.

Both loaders raise ``DataValidationError`` on schema drift so pipeline
failures are loud and specific rather than surfacing as a confusing
downstream KeyError three steps later.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import PATHS
from src.utils import get_logger

logger = get_logger(__name__)


class DataValidationError(ValueError):
    """Raised when a source file does not match the expected schema."""


# BrentOilPrices.csv silently switches date format partway through (a real
# data-quality issue in the source file, not a hypothetical one): rows up to
# 2020-04-21 are like "20-May-87" (%d-%b-%y), and every row from 2020-04-22
# onward is like "Apr 22, 2020" (%b %d, %Y). Parsing with a single format
# silently dropped the entire last ~2.5 years of data (~7% of rows) -
# including the 2022 Russia-Ukraine oil shock. Try each known format in turn
# instead of accepting that loss.
_DATE_FORMATS = ("%d-%b-%y", "%b %d, %Y")


def _parse_mixed_format_dates(raw: pd.Series) -> pd.Series:
    parsed = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    remaining = raw
    for fmt in _DATE_FORMATS:
        if remaining.empty:
            break
        attempt = pd.to_datetime(remaining, format=fmt, errors="coerce")
        parsed.loc[attempt.notna().index[attempt.notna()]] = attempt[attempt.notna()]
        remaining = remaining[attempt.isna()]
    return parsed


def load_raw_prices(path: Path | None = None) -> pd.DataFrame:
    """Load the raw Brent price series.

    Expected columns: Date (mixed formats - see ``_DATE_FORMATS``), Price (USD/barrel, float).
    """
    path = path or PATHS.raw_prices_csv
    if not path.exists():
        raise FileNotFoundError(
            f"Raw price file not found at {path}. Place BrentOilPrices.csv under data/raw/."
        )

    df = pd.read_csv(path)

    missing_cols = {"Date", "Price"} - set(df.columns)
    if missing_cols:
        raise DataValidationError(f"BrentOilPrices.csv is missing required columns: {missing_cols}")

    df["Date"] = _parse_mixed_format_dates(df["Date"])
    n_bad_dates = df["Date"].isna().sum()
    if n_bad_dates:
        logger.warning("Dropping %d rows with unparseable dates", n_bad_dates)
        df = df.dropna(subset=["Date"])

    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    n_bad_prices = df["Price"].isna().sum()
    if n_bad_prices:
        logger.warning("Dropping %d rows with non-numeric price", n_bad_prices)
        df = df.dropna(subset=["Price"])

    if (df["Price"] <= 0).any():
        raise DataValidationError("Encountered non-positive oil prices; refusing to proceed.")

    df = df.sort_values("Date").reset_index(drop=True)
    logger.info("Loaded %d raw price rows spanning %s to %s", len(df), df["Date"].min().date(), df["Date"].max().date())
    return df


def load_events(path: Path | None = None) -> pd.DataFrame:
    """Load the curated events workbook (data/events.xlsx).

    Expected columns (case-insensitive, flexible ordering): Event/Name,
    Start Date, Description, Region, Type.
    """
    path = path or PATHS.raw_events_xlsx
    if not path.exists():
        raise FileNotFoundError(f"Events workbook not found at {path}.")

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    # Normalize common column-name variants seen in hand-curated spreadsheets.
    rename_map = {}
    for col in df.columns:
        lower = col.lower()
        if lower in {"event", "name", "event name"}:
            rename_map[col] = "Event"
        elif lower in {"start date", "date"}:
            rename_map[col] = "Start Date"
        elif lower == "description":
            rename_map[col] = "Description"
        elif lower == "region":
            rename_map[col] = "Region"
        elif lower == "type":
            rename_map[col] = "Type"
    df = df.rename(columns=rename_map)

    required = {"Event", "Start Date"}
    missing = required - set(df.columns)
    if missing:
        raise DataValidationError(f"events.xlsx is missing required columns: {missing}")

    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    n_bad = df["Start Date"].isna().sum()
    if n_bad:
        logger.warning("Dropping %d events with unparseable Start Date", n_bad)
        df = df.dropna(subset=["Start Date"])

    for optional_col in ("Description", "Region", "Type"):
        if optional_col not in df.columns:
            df[optional_col] = ""

    df = df.sort_values("Start Date").reset_index(drop=True)
    logger.info("Loaded %d curated events", len(df))
    return df
