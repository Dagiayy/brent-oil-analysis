import numpy as np
import pandas as pd

from src.data.preprocessing import (
    add_rolling_volatility,
    build_processed_prices,
    compute_log_returns,
    deduplicate_and_reindex,
)
from src.data.quality import check_price_quality


def test_compute_log_returns_matches_manual_calculation():
    df = pd.DataFrame({"Date": pd.date_range("2020-01-01", periods=4), "Price": [10.0, 11.0, 9.0, 9.0]})
    out = compute_log_returns(df)

    expected = np.log(np.array([11.0, 9.0, 9.0]) / np.array([10.0, 11.0, 9.0]))
    assert np.allclose(out["Log_Return"].values, expected)
    assert len(out) == 3  # first row's undefined return is dropped, not left as NaN


def test_deduplicate_and_reindex_keeps_last_and_sorts():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2020-01-02", "2020-01-01", "2020-01-01"]),
            "Price": [11.0, 10.0, 10.5],  # second 2020-01-01 row should win
        }
    )
    out = deduplicate_and_reindex(df)

    assert list(out["Date"]) == list(pd.to_datetime(["2020-01-01", "2020-01-02"]))
    assert out.loc[out["Date"] == "2020-01-01", "Price"].item() == 10.5


def test_build_processed_prices_reports_no_duplicates_for_clean_data(synthetic_raw_prices):
    df = synthetic_raw_prices.copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%y")
    processed, report = build_processed_prices(df)

    assert report.n_duplicate_dates == 0
    assert "Log_Return" in processed.columns
    assert "Volatility_21d" in processed.columns
    assert processed["Date"].is_monotonic_increasing


def test_check_price_quality_flags_duplicate_dates():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-02"]),
            "Price": [10.0, 10.0, 11.0],
        }
    )
    report = check_price_quality(df)
    assert report.n_duplicate_dates == 1
    assert any("duplicate" in note for note in report.notes)


def test_check_price_quality_flags_large_moves_as_outliers():
    dates = pd.date_range("2020-01-01", periods=30)
    prices = np.full(30, 50.0)
    prices[15] = 200.0  # one dramatic one-day spike
    df = pd.DataFrame({"Date": dates, "Price": prices})

    report = check_price_quality(df)
    assert report.n_price_outliers_iqr >= 1


def test_add_rolling_volatility_is_nan_before_window_then_populated():
    df = pd.DataFrame({"Log_Return": np.random.default_rng(0).normal(0, 0.01, size=50)})
    out = add_rolling_volatility(df, window=21)

    assert out["Volatility_21d"].iloc[:20].isna().all()
    assert out["Volatility_21d"].iloc[20:].notna().all()
