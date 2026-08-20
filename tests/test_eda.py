import numpy as np
import pandas as pd

from src.analysis.eda import run_adf_test, summary_statistics


def test_adf_test_rejects_unit_root_for_white_noise():
    rng = np.random.default_rng(0)
    stationary_series = pd.Series(rng.normal(0, 1, size=1000))

    result = run_adf_test(stationary_series, name="white_noise")

    assert result.is_stationary is True
    assert result.p_value < 0.05


def test_adf_test_fails_to_reject_for_random_walk():
    rng = np.random.default_rng(0)
    random_walk = pd.Series(np.cumsum(rng.normal(0, 1, size=1000)))

    result = run_adf_test(random_walk, name="random_walk")

    assert result.is_stationary is False


def test_summary_statistics_shape(processed_prices_df):
    stats = summary_statistics(processed_prices_df)

    assert stats["n_observations"] == len(processed_prices_df)
    assert "price" in stats and "log_return" in stats
    assert "annualized_volatility" in stats
