import pandas as pd
import pytest

from src.config import Paths


@pytest.fixture
def prepared_paths(tmp_path, processed_prices_df, synthetic_events) -> Paths:
    paths = Paths(data_raw=tmp_path / "raw", data_processed=tmp_path / "processed", outputs=tmp_path / "outputs")
    paths.ensure_dirs()

    prices_out = processed_prices_df.copy()
    prices_out["Date"] = prices_out["Date"].dt.strftime("%Y-%m-%d")
    prices_out.to_csv(paths.processed_prices_csv, index=False)

    events_out = synthetic_events.copy()
    events_out["Start Date"] = events_out["Start Date"].dt.strftime("%Y-%m-%d")
    events_out.to_csv(paths.processed_events_csv, index=False)

    return paths


@pytest.fixture
def api_client(prepared_paths, monkeypatch):
    import app as flask_app_module
    import data_loader

    monkeypatch.setattr(data_loader, "PATHS", prepared_paths)
    flask_app_module.app.config.update(TESTING=True)
    with flask_app_module.app.test_client() as client:
        yield client


def test_health(api_client):
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "ok"


def test_prices_endpoint_returns_data(api_client):
    resp = api_client.get("/api/prices")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert len(body["data"]) > 0
    assert "Log_Return" in body["data"][0]


def test_prices_endpoint_emits_valid_json_despite_leading_nan_volatility(api_client):
    """Volatility_21d is NaN for the rolling-window warm-up rows. Python's
    json.loads tolerates a literal NaN token, but that's not valid JSON
    (RFC 8259) and browsers' JSON.parse rejects it - assert on the raw body,
    not resp.get_json(), so this actually catches the bug."""
    resp = api_client.get("/api/prices")
    raw = resp.get_data(as_text=True)
    assert "NaN" not in raw
    assert resp.get_json()["data"][0]["Volatility_21d"] is None


def test_prices_endpoint_date_filter(api_client, prepared_paths):
    df = pd.read_csv(prepared_paths.processed_prices_csv, parse_dates=["Date"])
    mid_date = df["Date"].iloc[len(df) // 2].strftime("%Y-%m-%d")

    resp = api_client.get(f"/api/prices?start={mid_date}&end={mid_date}")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]) == 1


def test_prices_endpoint_missing_data_returns_404(tmp_path, monkeypatch):
    import app as flask_app_module
    import data_loader

    empty_paths = Paths(data_raw=tmp_path / "raw", data_processed=tmp_path / "processed", outputs=tmp_path / "outputs")
    monkeypatch.setattr(data_loader, "PATHS", empty_paths)

    with flask_app_module.app.test_client() as client:
        resp = client.get("/api/prices")
    assert resp.status_code == 404
    assert resp.get_json()["status"] == "error"


def test_events_endpoint(api_client):
    resp = api_client.get("/api/events")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]) == 2


def test_stats_endpoint(api_client):
    resp = api_client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "volatility" in data
    assert "average_change" in data


def test_change_point_endpoint(api_client, prepared_paths):
    summary = pd.DataFrame({"mean": [0.001, 0.002, 50.0, 0.02]}, index=["mu1", "mu2", "tau", "sigma"])
    summary.to_csv(prepared_paths.trace_summary_csv)

    resp = api_client.get("/api/change-point")
    assert resp.status_code == 200
    assert "change_date" in resp.get_json()["data"]


def test_change_point_endpoint_missing_returns_404(api_client):
    resp = api_client.get("/api/change-point")
    assert resp.status_code == 404


def test_insights_endpoint_404_when_no_report_yet(api_client):
    resp = api_client.get("/api/insights")
    assert resp.status_code == 404
