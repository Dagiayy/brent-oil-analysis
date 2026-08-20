"""Data access layer for the Flask API.

Keeps pandas/IO concerns out of the route handlers in ``app.py`` so the
routes only deal with HTTP (status codes, query params, JSON shaping) and
this module owns "how do I read the processed data". Reuses the same
``src.config`` paths as the pipeline, so the API and the CLI pipeline can
never disagree about where data lives.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import PATHS  # noqa: E402


class DataNotAvailableError(Exception):
    """Raised when a required processed artifact hasn't been generated yet."""


def _date_filter(df: pd.DataFrame, col: str, start: str | None, end: str | None) -> pd.DataFrame:
    if not start and not end:
        return df
    start_dt = pd.to_datetime(start, utc=True).tz_convert(None) if start else None
    end_dt = pd.to_datetime(end, utc=True).tz_convert(None) if end else None

    if start_dt is not None and end_dt is not None and start == end:
        return df[df[col].dt.date == start_dt.date()]
    if start_dt is not None:
        df = df[df[col] >= start_dt]
    if end_dt is not None:
        df = df[df[col] <= end_dt]
    return df


def get_prices(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    if not PATHS.processed_prices_csv.exists():
        raise DataNotAvailableError(
            "Processed price data not found. Run `python pipelines/run_pipeline.py` first."
        )
    df = pd.read_csv(PATHS.processed_prices_csv)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    return _date_filter(df, "Date", start, end)


def get_events(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    if not PATHS.processed_events_csv.exists():
        raise DataNotAvailableError(
            "Processed events data not found. Run `python pipelines/run_pipeline.py` first."
        )
    df = pd.read_csv(PATHS.processed_events_csv)
    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    df = df.dropna(subset=["Start Date"])
    return _date_filter(df, "Start Date", start, end)


def get_change_point() -> dict[str, Any]:
    if not PATHS.trace_summary_csv.exists():
        raise DataNotAvailableError(
            "No model output found. Run `python pipelines/run_pipeline.py` first."
        )
    summary_df = pd.read_csv(PATHS.trace_summary_csv, index_col=0)
    if "tau" not in summary_df.index:
        raise DataNotAvailableError("Model output does not contain a 'tau' (change point) parameter.")

    tau_mean = int(float(summary_df.loc["tau", "mean"]))
    price_df = get_prices()

    if tau_mean >= len(price_df):
        tau_mean = len(price_df) - 1
    change_date = price_df.iloc[tau_mean]["Date"]

    return {"tau_index": tau_mean, "change_date": str(change_date.date())}


def get_stats(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    df = get_prices(start, end)
    if df.empty:
        raise DataNotAvailableError("No price data in the selected range.")
    return {
        "volatility": round(float(df["Log_Return"].std()), 6),
        "average_change": round(float(df["Log_Return"].mean()), 6),
    }


def get_latest_report() -> dict[str, Any] | None:
    report_path = PATHS.reports / "latest_run.json"
    if not report_path.exists():
        return None
    import json

    return json.loads(report_path.read_text(encoding="utf-8"))
