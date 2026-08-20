"""Deprecated location - kept as a thin re-export.

The real implementation now lives in ``src.data.preprocessing`` /
``src.data.ingestion`` (split into ingestion, quality checks, and
transformation so each piece is independently testable). Import from there
in new code; this module just forwards the public functions.
"""
from src.data.ingestion import load_events, load_raw_prices  # noqa: F401
from src.data.preprocessing import (  # noqa: F401
    add_rolling_volatility,
    build_processed_prices,
    compute_log_returns,
    deduplicate_and_reindex,
    save_processed_events,
    save_processed_prices,
)
