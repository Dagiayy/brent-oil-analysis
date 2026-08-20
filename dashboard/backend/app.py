"""Flask API for the Brent Oil Price dashboard.

Route handlers only deal with HTTP concerns; data access lives in
``data_loader.py`` and is fully driven by ``src.config`` so the API always
reads the same files the CLI pipeline (``pipelines/run_pipeline.py``)
writes. Debug mode, port, and CORS origins are environment-driven - see
.env.example - instead of hardcoded, so this is safe to containerize.
"""
from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import data_loader  # noqa: E402

from src.config import API_CONFIG  # noqa: E402

app = Flask(__name__)
CORS(app, origins=[o.strip() for o in API_CONFIG.cors_origins.split(",")])


def _success(data):
    return jsonify({"status": "success", "data": data}), 200


def _error(message: str, status: int = 500):
    return jsonify({"status": "error", "message": message}), status


@app.errorhandler(data_loader.DataNotAvailableError)
def handle_data_not_available(err: data_loader.DataNotAvailableError):
    return _error(str(err), 404)


@app.errorhandler(HTTPException)
def handle_http_exception(err: HTTPException):
    # Preserve Flask/Werkzeug's own status codes (404 on unmatched routes,
    # 405 on wrong method, etc.) instead of collapsing everything to 500.
    return _error(err.description or err.name, err.code or 500)


@app.errorhandler(Exception)
def handle_unexpected_error(err: Exception):
    app.logger.exception("Unhandled error while serving %s", request.path)
    return _error("An internal error occurred.", 500)


@app.route("/api/health")
def health():
    return _success({"status": "ok"})


@app.route("/api/prices")
def prices():
    start = request.args.get("start")
    end = request.args.get("end")
    df = data_loader.get_prices(start, end)
    if df.empty:
        return _error("No price data in selected range.", 404)
    df = df.copy()
    df["Date"] = df["Date"].astype(str)
    # Volatility_21d is NaN for the first 20 rows (rolling window warm-up).
    # Python's json module happily emits a literal `NaN` token for float
    # nan, but that is not valid JSON (RFC 8259) - browsers' JSON.parse
    # rejects it. Convert to None so it serializes as `null` instead.
    df = df.astype(object).where(df.notna(), None)
    return _success(df.to_dict(orient="records"))


@app.route("/api/events")
def events():
    start = request.args.get("start")
    end = request.args.get("end")
    df = data_loader.get_events(start, end)
    if df.empty:
        return _error("No event data in selected range.", 404)
    df = df.copy()
    df["Start Date"] = df["Start Date"].astype(str)
    return _success(df.to_dict(orient="records"))


@app.route("/api/change-point")
def change_point():
    return _success(data_loader.get_change_point())


@app.route("/api/stats")
def stats():
    start = request.args.get("start")
    end = request.args.get("end")
    return _success(data_loader.get_stats(start, end))


@app.route("/api/insights")
def insights():
    """Latest pipeline run manifest: diagnostics, event alignment, AI/template narrative."""
    report = data_loader.get_latest_report()
    if report is None:
        return _error("No pipeline run found yet. Run `python pipelines/run_pipeline.py` first.", 404)
    return _success(report)


if __name__ == "__main__":
    app.run(host=API_CONFIG.host, port=API_CONFIG.port, debug=API_CONFIG.debug)
