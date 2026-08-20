"""Align a detected change point with the curated events dataset and quantify
the before/after shift in return and volatility.

This is the piece of the original project that the README described as
"Task 3" (correlate change points with real-world events) but that was
never actually implemented anywhere in the codebase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class EventAlignment:
    change_date: pd.Timestamp
    nearest_event: str | None
    nearest_event_date: pd.Timestamp | None
    nearest_event_type: str | None
    days_to_nearest_event: int | None
    mean_return_before: float
    mean_return_after: float
    annualized_vol_before: float
    annualized_vol_after: float
    price_before: float
    price_after: float
    pct_price_change_30d: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_date": str(self.change_date.date()),
            "nearest_event": self.nearest_event,
            "nearest_event_date": str(self.nearest_event_date.date()) if self.nearest_event_date is not None else None,
            "nearest_event_type": self.nearest_event_type,
            "days_to_nearest_event": self.days_to_nearest_event,
            "mean_return_before": round(self.mean_return_before, 6),
            "mean_return_after": round(self.mean_return_after, 6),
            "annualized_vol_before": round(self.annualized_vol_before, 4),
            "annualized_vol_after": round(self.annualized_vol_after, 4),
            "price_before": round(self.price_before, 2),
            "price_after": round(self.price_after, 2),
            "pct_price_change_30d": round(self.pct_price_change_30d, 2),
        }


def find_nearest_event(
    change_date: pd.Timestamp, events: pd.DataFrame, max_window_days: int = 90
) -> pd.Series | None:
    """Return the event closest in time to ``change_date``, or None if the
    nearest event falls outside ``max_window_days`` (avoids spuriously
    attributing a change point to an unrelated, distant event)."""
    if events.empty:
        return None
    diffs = (events["Start Date"] - change_date).abs().dt.days
    idx = diffs.idxmin()
    if diffs.loc[idx] > max_window_days:
        return None
    return events.loc[idx]


def quantify_shift(df: pd.DataFrame, change_date: pd.Timestamp, window_days: int = 30) -> dict[str, float]:
    """Compare return/volatility/price statistics before vs. after the change point."""
    before = df[df["Date"] < change_date]
    after = df[df["Date"] >= change_date]

    mean_before = float(before["Log_Return"].mean()) if len(before) else float("nan")
    mean_after = float(after["Log_Return"].mean()) if len(after) else float("nan")
    vol_before = float(before["Log_Return"].std() * np.sqrt(252)) if len(before) else float("nan")
    vol_after = float(after["Log_Return"].std() * np.sqrt(252)) if len(after) else float("nan")

    price_before = float(before["Price"].iloc[-1]) if len(before) else float("nan")
    after_window = after[after["Date"] <= change_date + pd.Timedelta(days=window_days)]
    price_after = float(after_window["Price"].iloc[-1]) if len(after_window) else float("nan")
    pct_change = ((price_after - price_before) / price_before * 100) if price_before else float("nan")

    return {
        "mean_return_before": mean_before,
        "mean_return_after": mean_after,
        "annualized_vol_before": vol_before,
        "annualized_vol_after": vol_after,
        "price_before": price_before,
        "price_after": price_after,
        "pct_price_change_30d": pct_change,
    }


def build_alignment_report(
    df: pd.DataFrame, change_date: pd.Timestamp, events: pd.DataFrame, max_window_days: int = 90
) -> EventAlignment:
    nearest = find_nearest_event(change_date, events, max_window_days)
    shift = quantify_shift(df, change_date)

    return EventAlignment(
        change_date=change_date,
        nearest_event=str(nearest["Event"]) if nearest is not None else None,
        nearest_event_date=nearest["Start Date"] if nearest is not None else None,
        nearest_event_type=str(nearest.get("Type", "")) if nearest is not None else None,
        days_to_nearest_event=int((nearest["Start Date"] - change_date).days) if nearest is not None else None,
        **shift,
    )
