"""End-to-end CLI orchestrator for the Brent oil analysis pipeline.

    Extract -> Validate -> Transform -> Load -> Model -> Align -> Narrate -> Report

Run from the project root:

    python pipelines/run_pipeline.py
    python pipelines/run_pipeline.py --variant mean_vol_shift --draws 1000 --chains 2
    python pipelines/run_pipeline.py --skip-model   # just refresh data/processed/*

Every run writes a timestamped, self-contained manifest to
``outputs/reports/run_<timestamp>.json`` recording exactly what ran, on what
data (content hash), with what parameters, and whether the model diagnostics
passed - so any run is auditable after the fact without re-executing it.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.eda import run_adf_test, summary_statistics  # noqa: E402
from src.config import MODEL_CONFIG, PATHS, ModelConfig  # noqa: E402
from src.data.ingestion import load_events, load_raw_prices  # noqa: E402
from src.data.preprocessing import build_processed_prices, save_processed_events, save_processed_prices  # noqa: E402
from src.utils import file_sha256, get_logger, timed_step, write_json  # noqa: E402

logger = get_logger("pipeline")


def run_etl() -> tuple[dict, dict]:
    """Extract -> Validate -> Transform -> Load. Returns (lineage, quality_report)."""
    with timed_step(logger, "extract raw prices"):
        raw_prices = load_raw_prices()

    with timed_step(logger, "validate + transform prices"):
        processed, quality_report = build_processed_prices(raw_prices)

    with timed_step(logger, "load processed prices"):
        save_processed_prices(processed, PATHS.processed_prices_csv)

    events_lineage = None
    if PATHS.raw_events_xlsx.exists():
        with timed_step(logger, "extract + load events"):
            events = load_events()
            save_processed_events(events, PATHS.processed_events_csv)
            events_lineage = {
                "source": str(PATHS.raw_events_xlsx),
                "sha256_16": file_sha256(PATHS.raw_events_xlsx),
                "n_events": len(events),
            }
    else:
        logger.warning("data/events.xlsx not found; skipping events processing.")

    lineage = {
        "raw_prices": {
            "source": str(PATHS.raw_prices_csv),
            "sha256_16": file_sha256(PATHS.raw_prices_csv),
            "n_rows": len(raw_prices),
        },
        "events": events_lineage,
    }
    return lineage, quality_report.to_dict()


def run_eda() -> dict:
    import pandas as pd

    df = pd.read_csv(PATHS.processed_prices_csv, parse_dates=["Date"])
    with timed_step(logger, "stationarity test (ADF) on log returns"):
        adf_result = run_adf_test(df["Log_Return"], name="Log_Return")
    stats = summary_statistics(df)
    return {"summary_statistics": stats, "adf_test": adf_result.to_dict()}


def run_model_and_insights(variant: str, config: ModelConfig) -> dict:
    import pandas as pd

    from src.insights.event_alignment import build_alignment_report
    from src.modeling.change_point_model import (
        plot_posterior_mean_comparison,
        plot_price_with_change_point,
        plot_trace,
        run_single_model,
    )

    df = pd.read_csv(PATHS.processed_prices_csv, parse_dates=["Date"]).dropna(subset=["Log_Return"])
    result = run_single_model(df["Log_Return"].values, df["Date"], variant, config)
    result.summary.to_csv(PATHS.trace_summary_csv)

    var_names = [v for v in result.summary.index]
    plot_trace(result.idata, var_names, PATHS.figures / "change_point_traceplot.png")
    if "mu1" in result.summary.index:
        plot_posterior_mean_comparison(result.idata, PATHS.figures / "posterior_mu_comparison.png")

    events_df = None
    alignment = None
    if PATHS.processed_events_csv.exists() and result.change_date is not None:
        events_df = pd.read_csv(PATHS.processed_events_csv, parse_dates=["Start Date"])
        alignment = build_alignment_report(df, result.change_date, events_df)

    plot_price_with_change_point(df, result.change_date, events_df, PATHS.figures / "price_with_change_point.png")

    return {
        "change_point": result.to_manifest_dict(),
        "diagnostics": result.diagnostics,
        "event_alignment": alignment.to_dict() if alignment else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Brent oil analysis pipeline end-to-end.")
    parser.add_argument("--variant", choices=["mean_shift", "mean_vol_shift"], default="mean_shift")
    parser.add_argument("--draws", type=int, default=MODEL_CONFIG.draws)
    parser.add_argument("--tune", type=int, default=MODEL_CONFIG.tune)
    parser.add_argument("--chains", type=int, default=MODEL_CONFIG.chains)
    parser.add_argument("--seed", type=int, default=MODEL_CONFIG.random_seed)
    parser.add_argument("--skip-model", action="store_true", help="Only run the ETL + EDA steps.")
    parser.add_argument("--skip-narrative", action="store_true", help="Skip AI/template narrative generation.")
    args = parser.parse_args()

    PATHS.ensure_dirs()
    run_started = datetime.now(timezone.utc)
    manifest: dict = {"run_started_utc": run_started.isoformat(), "variant": args.variant}

    lineage, quality_report = run_etl()
    manifest["lineage"] = lineage
    manifest["data_quality"] = quality_report

    manifest["eda"] = run_eda()

    if not args.skip_model:
        config = ModelConfig(draws=args.draws, tune=args.tune, chains=args.chains, random_seed=args.seed)
        manifest["model"] = {"config": vars(config)}
        model_results = run_model_and_insights(args.variant, config)
        manifest["model"].update(model_results)

        if not args.skip_narrative:
            from src.ai.narrative import generate_narrative

            narrative_input = {
                "change_point": model_results["change_point"],
                "diagnostics": model_results["diagnostics"],
                "event_alignment": model_results["event_alignment"],
            }
            manifest["narrative"] = generate_narrative(narrative_input)
            (PATHS.reports / "narrative.txt").write_text(manifest["narrative"]["text"], encoding="utf-8")

    manifest["run_finished_utc"] = datetime.now(timezone.utc).isoformat()
    run_id = run_started.strftime("%Y%m%dT%H%M%SZ")
    write_json(PATHS.logs / f"run_{run_id}.json", manifest)
    write_json(PATHS.reports / "latest_run.json", manifest)

    logger.info("Pipeline complete. Manifest: %s", PATHS.reports / "latest_run.json")
    if "narrative" in manifest:
        print("\n--- Analyst Note ---")
        print(manifest["narrative"]["text"])


if __name__ == "__main__":
    main()
