"""Bayesian change-point detection for the Brent crude log-return series.

Model design
------------
The original version of this module modeled the switch point ``tau`` as a
``DiscreteUniform`` combined with ``pm.math.switch``. Because ``tau`` is
discrete, PyMC cannot use a single NUTS sampler for the whole model - it
falls back to a compound step (Metropolis-within-Gibbs for ``tau``, NUTS for
the rest), which mixes very poorly for this kind of model. The trace
committed in this repo before this rewrite showed effective sample sizes of
only ~60-120 out of 8,000 draws and missing r_hat diagnostics - i.e. the
original posterior was not trustworthy.

This version replaces the hard switch with a **sigmoid relaxation**:
``weight = sigmoid((t - tau) / smoothness)`` is a smooth, differentiable
approximation of the step function, so ``tau`` can be modeled as continuous
and the *entire* model can be sampled with NUTS. This is a standard trick
for Bayesian change-point models and produces dramatically better mixing
(see ``diagnose_trace`` / the r_hat and ESS thresholds in ``src.config``).

Three model variants are provided so the change is judged against explicit
baselines rather than assumed a priori:

* ``null``          - single (mu, sigma), i.e. "no change point" baseline.
* ``mean_shift``     - mean shifts at tau, shared volatility (the case this
                        project originally targeted).
* ``mean_vol_shift``  - both mean *and* volatility shift at tau (oil price
                        regime changes are usually volatility regime changes
                        too, e.g. 2020 COVID crash, 2008 financial crisis).

``compare_models`` ranks the three with PSIS-LOO/WAIC via ArviZ so the report
can state *which* hypothesis the data actually supports, instead of just
fitting one model and reporting on faith.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

if __package__ in (None, ""):
    # Allow `python src/modeling/change_point_model.py ...` (documented in the
    # README) in addition to `python -m src.modeling.change_point_model` /
    # importing this module normally - both of the latter already have the
    # project root on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import arviz as az
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymc as pm

from src.config import MODEL_CONFIG, PATHS, ModelConfig
from src.utils import get_logger, timed_step

logger = get_logger(__name__)

ModelVariant = Literal["null", "mean_shift", "mean_vol_shift"]
SWITCH_SMOOTHNESS_FRACTION = 0.005  # sigmoid steepness as a fraction of n observations


@dataclass
class ChangePointResult:
    model_name: str
    change_index: int | None
    change_date: pd.Timestamp | None
    tau_mean: float | None
    tau_hdi: tuple[float, float] | None
    summary: pd.DataFrame
    diagnostics: dict[str, Any]
    idata: az.InferenceData = field(repr=False)

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "change_index": self.change_index,
            "change_date": str(self.change_date.date()) if isinstance(self.change_date, pd.Timestamp) else None,
            "tau_mean": round(self.tau_mean, 2) if self.tau_mean is not None else None,
            "tau_hdi_3_97": [round(v, 2) for v in self.tau_hdi] if self.tau_hdi else None,
            "diagnostics": self.diagnostics,
        }


def _build_model(returns: np.ndarray, variant: ModelVariant, smoothness: float) -> pm.Model:
    n = len(returns)
    idx = np.arange(n)

    with pm.Model() as model:
        if variant == "null":
            mu = pm.Normal("mu", mu=0, sigma=1)
            sigma = pm.HalfNormal("sigma", sigma=1)
            pm.Normal("obs", mu=mu, sigma=sigma, observed=returns)
            return model

        tau = pm.Uniform("tau", lower=0, upper=n - 1)
        weight = pm.math.sigmoid((idx - tau) / smoothness)

        mu1 = pm.Normal("mu1", mu=0, sigma=1)
        mu2 = pm.Normal("mu2", mu=0, sigma=1)
        mu = mu1 * (1 - weight) + mu2 * weight

        if variant == "mean_shift":
            sigma = pm.HalfNormal("sigma", sigma=1)
            pm.Normal("obs", mu=mu, sigma=sigma, observed=returns)
        elif variant == "mean_vol_shift":
            sigma1 = pm.HalfNormal("sigma1", sigma=1)
            sigma2 = pm.HalfNormal("sigma2", sigma=1)
            sigma = sigma1 * (1 - weight) + sigma2 * weight
            pm.Normal("obs", mu=mu, sigma=sigma, observed=returns)
        else:
            raise ValueError(f"Unknown model variant: {variant}")

    return model


def _sample(model: pm.Model, config: ModelConfig) -> az.InferenceData:
    with model:
        idata = pm.sample(
            draws=config.draws,
            tune=config.tune,
            chains=config.chains,
            target_accept=config.target_accept,
            random_seed=config.random_seed,
            return_inferencedata=True,
            progressbar=False,
        )
        pm.compute_log_likelihood(idata, progressbar=False)
    return idata


def diagnose_trace(idata: az.InferenceData, var_names: list[str], config: ModelConfig) -> dict[str, Any]:
    """Summarize convergence diagnostics and flag the run if it fails thresholds."""
    summary = az.summary(idata, var_names=var_names)
    max_r_hat = float(summary["r_hat"].max()) if "r_hat" in summary else float("nan")
    min_ess_bulk = float(summary["ess_bulk"].min())

    warnings: list[str] = []
    if not np.isnan(max_r_hat) and max_r_hat > config.max_r_hat:
        warnings.append(f"max r_hat={max_r_hat:.4f} exceeds threshold {config.max_r_hat}")
    if min_ess_bulk < config.min_ess_bulk:
        warnings.append(f"min ess_bulk={min_ess_bulk:.1f} below threshold {config.min_ess_bulk}")

    n_divergences = int(idata.sample_stats["diverging"].sum()) if "diverging" in idata.sample_stats else 0
    if n_divergences:
        warnings.append(f"{n_divergences} divergent transitions")

    return {
        "max_r_hat": None if np.isnan(max_r_hat) else round(max_r_hat, 4),
        "min_ess_bulk": round(min_ess_bulk, 1),
        "n_divergences": n_divergences,
        "reliable": len(warnings) == 0,
        "warnings": warnings,
    }


def run_single_model(
    returns: np.ndarray,
    dates: pd.Series,
    variant: ModelVariant,
    config: ModelConfig = MODEL_CONFIG,
) -> ChangePointResult:
    n = len(returns)
    smoothness = max(1.0, n * SWITCH_SMOOTHNESS_FRACTION)

    with timed_step(logger, f"sample '{variant}' model (n={n}, draws={config.draws}, chains={config.chains})"):
        model = _build_model(returns, variant, smoothness)
        idata = _sample(model, config)

    if variant == "null":
        var_names = ["mu", "sigma"]
    elif variant == "mean_shift":
        var_names = ["mu1", "mu2", "tau", "sigma"]
    else:
        var_names = ["mu1", "mu2", "tau", "sigma1", "sigma2"]

    summary = az.summary(idata, var_names=var_names)
    diagnostics = diagnose_trace(idata, var_names, config)

    change_index = change_date = tau_mean = None
    tau_hdi = None
    if variant != "null":
        tau_samples = idata.posterior["tau"].values.flatten()
        tau_mean = float(tau_samples.mean())
        change_index = int(round(tau_mean))
        change_index = min(max(change_index, 0), n - 1)
        change_date = pd.Timestamp(dates.iloc[change_index])
        hdi = az.hdi(idata, var_names=["tau"], prob=0.94)["tau"].values
        tau_hdi = (float(hdi[0]), float(hdi[1]))

    return ChangePointResult(
        model_name=variant,
        change_index=change_index,
        change_date=change_date,
        tau_mean=tau_mean,
        tau_hdi=tau_hdi,
        summary=summary,
        diagnostics=diagnostics,
        idata=idata,
    )


def compare_models(results: dict[str, ChangePointResult]) -> pd.DataFrame:
    """Rank fitted models by PSIS-LOO (higher elpd_loo = better predictive fit).

    arviz-stats >=1.0 always uses PSIS-LOO for ``compare`` (the old ``ic``
    switch between WAIC/LOO was removed - LOO is the recommended default)."""
    idata_dict = {name: r.idata for name, r in results.items()}
    comparison = az.compare(idata_dict)
    return comparison


def plot_trace(idata: az.InferenceData, var_names: list[str], out_path: Path) -> None:
    az.plot_trace(idata, var_names=var_names)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110)
    plt.close("all")


def plot_posterior_mean_comparison(idata: az.InferenceData, out_path: Path) -> None:
    mu1 = idata.posterior["mu1"].values.flatten()
    mu2 = idata.posterior["mu2"].values.flatten()

    plt.figure(figsize=(10, 6))
    plt.hist(mu1, bins=50, alpha=0.5, label="mu1 (before)", color="skyblue")
    plt.hist(mu2, bins=50, alpha=0.5, label="mu2 (after)", color="orange")
    plt.axvline(mu1.mean(), color="blue", linestyle="--")
    plt.axvline(mu2.mean(), color="red", linestyle="--")
    plt.legend()
    plt.title("Posterior Distributions of Mean Log Return, Before vs. After Change Point")
    plt.xlabel("Mean Log Return")
    plt.ylabel("Frequency")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110)
    plt.close("all")


def plot_price_with_change_point(
    df: pd.DataFrame, change_date: pd.Timestamp | None, events: pd.DataFrame | None, out_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(df["Date"], df["Price"], color="steelblue", linewidth=0.9, label="Brent spot price")
    if change_date is not None:
        ax.axvline(change_date, color="crimson", linestyle="--", linewidth=1.5, label=f"Detected change point ({change_date.date()})")
    if events is not None and not events.empty:
        for _, ev in events.iterrows():
            ax.axvline(ev["Start Date"], color="gray", alpha=0.25, linewidth=0.8)
    ax.set_title("Brent Crude Oil Price with Detected Change Point")
    ax.set_xlabel("Date")
    ax.set_ylabel("USD / barrel")
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def run_change_point_analysis(
    data_path: str | Path,
    output_dir: str | Path = PATHS.outputs,
    variant: ModelVariant = "mean_shift",
    config: ModelConfig = MODEL_CONFIG,
) -> tuple[az.InferenceData, pd.Timestamp | None, pd.DataFrame]:
    """Backward-compatible single-model entry point (used by the CLI and notebooks).

    Kept signature-compatible with the original implementation
    (``trace, change_date, summary_df``) while delegating to the upgraded,
    better-mixing model internally.
    """
    output_dir = Path(output_dir)
    figures_dir = output_dir / "figures"
    logs_dir = output_dir / "logs"
    figures_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path, parse_dates=["Date"])
    df = df.dropna(subset=["Log_Return"])
    returns = df["Log_Return"].values

    result = run_single_model(returns, df["Date"], variant, config)
    result.summary.to_csv(logs_dir / "trace_summary.csv")

    var_names = ["mu1", "mu2", "tau", "sigma"] if variant == "mean_shift" else list(result.summary.index)
    plot_trace(result.idata, [v for v in var_names if v in result.summary.index], figures_dir / "change_point_traceplot.png")
    if "mu1" in result.summary.index:
        plot_posterior_mean_comparison(result.idata, figures_dir / "posterior_mu_comparison.png")

    if not result.diagnostics["reliable"]:
        logger.warning("Model diagnostics flagged this run as unreliable: %s", result.diagnostics["warnings"])

    return result.idata, result.change_date, result.summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bayesian change-point detection on Brent oil log returns.")
    parser.add_argument("--data", type=str, default=str(PATHS.processed_prices_csv))
    parser.add_argument("--output", type=str, default=str(PATHS.outputs))
    parser.add_argument("--variant", choices=["null", "mean_shift", "mean_vol_shift", "compare"], default="mean_shift")
    parser.add_argument("--draws", type=int, default=MODEL_CONFIG.draws)
    parser.add_argument("--tune", type=int, default=MODEL_CONFIG.tune)
    parser.add_argument("--chains", type=int, default=MODEL_CONFIG.chains)
    parser.add_argument("--seed", type=int, default=MODEL_CONFIG.random_seed)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_config = ModelConfig(draws=args.draws, tune=args.tune, chains=args.chains, random_seed=args.seed)

    if args.variant == "compare":
        df = pd.read_csv(args.data, parse_dates=["Date"]).dropna(subset=["Log_Return"])
        results = {
            name: run_single_model(df["Log_Return"].values, df["Date"], name, run_config)
            for name in ("null", "mean_shift", "mean_vol_shift")
        }
        comparison = compare_models(results)
        print(comparison)
        out_dir = Path(args.output) / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(out_dir / "model_comparison.csv")
    else:
        idata, change_date, summary = run_change_point_analysis(args.data, args.output, args.variant, run_config)
        print(f"Most probable change point date: {change_date.date() if change_date is not None else 'N/A'}")
        print(summary)
