"""Smoke tests for the Bayesian model. Marked slow: runs real (tiny) MCMC
sampling rather than mocking pymc, since the whole point of this module's
rewrite is the sampler's mixing behavior - a mock would test nothing real.
Skips cleanly if pymc is not installed rather than failing collection.
"""
import numpy as np
import pandas as pd
import pytest

pymc = pytest.importorskip("pymc")

from src.config import ModelConfig  # noqa: E402
from src.modeling.change_point_model import run_single_model  # noqa: E402

FAST_CONFIG = ModelConfig(draws=100, tune=100, chains=2, target_accept=0.9, random_seed=1)


@pytest.fixture(scope="module")
def synthetic_series():
    rng = np.random.default_rng(1)
    n = 200
    change_at = 120
    returns = np.concatenate([rng.normal(0.0, 0.01, change_at), rng.normal(0.05, 0.01, n - change_at)])
    dates = pd.Series(pd.date_range("2020-01-01", periods=n))
    return returns, dates, change_at


@pytest.mark.slow
def test_mean_shift_model_runs_and_returns_expected_shape(synthetic_series):
    returns, dates, _ = synthetic_series

    result = run_single_model(returns, dates, "mean_shift", FAST_CONFIG)

    assert result.change_index is not None
    assert 0 <= result.change_index < len(returns)
    assert set(result.summary.index) == {"mu1", "mu2", "tau", "sigma"}
    assert "reliable" in result.diagnostics


@pytest.mark.slow
def test_mean_shift_model_recovers_approximate_change_point(synthetic_series):
    returns, dates, true_change_at = synthetic_series

    result = run_single_model(returns, dates, "mean_shift", FAST_CONFIG)

    # With only 100 draws/100 tune this is a coarse check, not a convergence
    # guarantee - it verifies the sigmoid-relaxed model points at roughly the
    # right place, not that it's fully converged (see the real pipeline run
    # in outputs/logs for converged diagnostics).
    assert abs(result.change_index - true_change_at) < 40


@pytest.mark.slow
def test_null_model_runs_without_tau():
    rng = np.random.default_rng(2)
    returns = rng.normal(0, 0.01, 100)
    dates = pd.Series(pd.date_range("2020-01-01", periods=100))

    result = run_single_model(returns, dates, "null", FAST_CONFIG)

    assert result.change_index is None
    assert set(result.summary.index) == {"mu", "sigma"}
