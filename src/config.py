"""Centralized configuration for the Brent oil analysis pipeline.

All file paths and runtime settings are resolved relative to the project
root so that scripts, notebooks, tests, and the Flask API resolve the same
locations regardless of the working directory they are invoked from.
Values can be overridden with environment variables (see .env.example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at import time
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).resolve() if value else default


@dataclass(frozen=True)
class Paths:
    root: Path = PROJECT_ROOT
    data_raw: Path = field(default_factory=lambda: _env_path("BRENT_DATA_RAW", PROJECT_ROOT / "data" / "raw"))
    data_processed: Path = field(
        default_factory=lambda: _env_path("BRENT_DATA_PROCESSED", PROJECT_ROOT / "data" / "processed")
    )
    outputs: Path = field(default_factory=lambda: _env_path("BRENT_OUTPUTS", PROJECT_ROOT / "outputs"))
    figures: Path = field(init=False)
    logs: Path = field(init=False)
    reports: Path = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "figures", self.outputs / "figures")
        object.__setattr__(self, "logs", self.outputs / "logs")
        object.__setattr__(self, "reports", self.outputs / "reports")

    @property
    def raw_prices_csv(self) -> Path:
        return self.data_raw / "BrentOilPrices.csv"

    @property
    def raw_events_xlsx(self) -> Path:
        return self.root / "data" / "events.xlsx"

    @property
    def processed_prices_csv(self) -> Path:
        return self.data_processed / "brent_log_returns.csv"

    @property
    def processed_events_csv(self) -> Path:
        return self.data_processed / "events.csv"

    @property
    def trace_summary_csv(self) -> Path:
        return self.logs / "trace_summary.csv"

    def ensure_dirs(self) -> None:
        for path in (self.data_processed, self.figures, self.logs, self.reports):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ModelConfig:
    """Bayesian change point model hyperparameters."""

    draws: int = int(os.getenv("BRENT_MCMC_DRAWS", "2000"))
    tune: int = int(os.getenv("BRENT_MCMC_TUNE", "1500"))
    chains: int = int(os.getenv("BRENT_MCMC_CHAINS", "4"))
    target_accept: float = float(os.getenv("BRENT_MCMC_TARGET_ACCEPT", "0.95"))
    random_seed: int = int(os.getenv("BRENT_RANDOM_SEED", "42"))
    # Diagnostic thresholds used to flag a run as unreliable.
    max_r_hat: float = 1.01
    min_ess_bulk: float = 400.0


@dataclass(frozen=True)
class APIConfig:
    host: str = os.getenv("FLASK_HOST", "0.0.0.0")
    port: int = int(os.getenv("FLASK_PORT", "5000"))
    debug: bool = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")


PATHS = Paths()
MODEL_CONFIG = ModelConfig()
API_CONFIG = APIConfig()
