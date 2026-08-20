"""Reusable exploratory / statistical analysis functions.

Extracted from the (previously empty) EDA notebook so the same,
tested logic backs the notebook, the CLI pipeline, and the API - instead
of three divergent copy-pasted implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


@dataclass
class StationarityResult:
    series_name: str
    adf_statistic: float
    p_value: float
    n_lags: int
    n_obs: int
    critical_values: dict[str, float]
    is_stationary: bool  # at 5% significance

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_name": self.series_name,
            "adf_statistic": round(self.adf_statistic, 4),
            "p_value": round(self.p_value, 6),
            "n_lags": self.n_lags,
            "n_obs": self.n_obs,
            "critical_values": {k: round(v, 4) for k, v in self.critical_values.items()},
            "is_stationary_5pct": self.is_stationary,
        }


def run_adf_test(series: pd.Series, name: str = "series") -> StationarityResult:
    """Augmented Dickey-Fuller test. H0: series has a unit root (non-stationary)."""
    series = series.dropna()
    stat, p_value, n_lags, n_obs, crit_values, _ = adfuller(series, autolag="AIC")
    return StationarityResult(
        series_name=name,
        adf_statistic=stat,
        p_value=p_value,
        n_lags=n_lags,
        n_obs=n_obs,
        critical_values=crit_values,
        is_stationary=bool(p_value < 0.05),
    )


def summary_statistics(df: pd.DataFrame) -> dict[str, Any]:
    """Descriptive stats for the price and log-return series."""
    price_stats = df["Price"].describe().to_dict()
    return_stats = df["Log_Return"].describe().to_dict()
    return {
        "n_observations": len(df),
        "date_range": [df["Date"].min().strftime("%Y-%m-%d"), df["Date"].max().strftime("%Y-%m-%d")],
        "price": {k: round(v, 4) for k, v in price_stats.items()},
        "log_return": {k: round(v, 6) for k, v in return_stats.items()},
        "annualized_volatility": round(df["Log_Return"].std() * np.sqrt(252), 4),
        "skewness": round(df["Log_Return"].skew(), 4),
        "kurtosis_excess": round(df["Log_Return"].kurt(), 4),
    }
