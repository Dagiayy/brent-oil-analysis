"""Data quality checks run as part of the Validate step of the ETL pipeline.

Produces a JSON-serializable report so pipeline runs are auditable: anyone
looking at outputs/reports/run_<ts>.json can see exactly what quality
issues were found and how they were handled, without re-reading code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class DataQualityReport:
    n_rows: int
    n_duplicate_dates: int
    n_missing_after_reindex: int
    date_range: tuple[str, str]
    n_price_outliers_iqr: int
    outlier_dates: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_duplicate_dates": self.n_duplicate_dates,
            "n_missing_after_reindex": self.n_missing_after_reindex,
            "date_range": list(self.date_range),
            "n_price_outliers_iqr": self.n_price_outliers_iqr,
            "outlier_dates": self.outlier_dates,
            "notes": self.notes,
        }


def check_price_quality(df: pd.DataFrame, date_col: str = "Date", price_col: str = "Price") -> DataQualityReport:
    """Run duplicate/missing/outlier checks on a price series.

    Outliers are flagged (for reporting) using the 1.5*IQR rule on the
    day-over-day percentage change, which is far more meaningful for a
    trending price series than an IQR rule on price levels.
    """
    notes: list[str] = []

    n_dupes = int(df[date_col].duplicated().sum())
    if n_dupes:
        notes.append(f"{n_dupes} duplicate trading dates found and will be aggregated (kept last).")

    pct_change = df[price_col].pct_change().dropna()
    q1, q3 = pct_change.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outlier_mask = (pct_change < lower) | (pct_change > upper)
    outlier_dates = df.loc[pct_change[outlier_mask].index, date_col].dt.strftime("%Y-%m-%d").tolist()
    if outlier_dates:
        notes.append(
            f"{len(outlier_dates)} daily moves fall outside 1.5*IQR of the daily return "
            "distribution (retained - large moves are expected around real shocks, not "
            "removed as errors)."
        )

    return DataQualityReport(
        n_rows=len(df),
        n_duplicate_dates=n_dupes,
        n_missing_after_reindex=0,  # populated by caller after business-day reindex, if used
        date_range=(df[date_col].min().strftime("%Y-%m-%d"), df[date_col].max().strftime("%Y-%m-%d")),
        n_price_outliers_iqr=len(outlier_dates),
        outlier_dates=outlier_dates[:25],  # cap for report readability
        notes=notes,
    )
