import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))


@pytest.fixture
def synthetic_raw_prices() -> pd.DataFrame:
    """A clean, dd-Mon-yy formatted raw price frame, matching BrentOilPrices.csv."""
    dates = pd.bdate_range("2020-01-01", periods=250)
    rng = np.random.default_rng(42)
    prices = 50 + np.cumsum(rng.normal(0, 0.5, size=len(dates)))
    prices = np.abs(prices) + 10
    return pd.DataFrame({"Date": dates.strftime("%d-%b-%y"), "Price": prices.round(2)})


@pytest.fixture
def synthetic_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Event": ["Synthetic Event A", "Synthetic Event B"],
            "Start Date": pd.to_datetime(["2020-03-15", "2020-06-01"]),
            "Description": ["desc a", "desc b"],
            "Region": ["Global", "Global"],
            "Type": ["Conflict", "OPEC"],
        }
    )


@pytest.fixture
def processed_prices_df(synthetic_raw_prices) -> pd.DataFrame:
    from src.data.preprocessing import build_processed_prices

    df = synthetic_raw_prices.copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%y")
    processed, _ = build_processed_prices(df)
    return processed
