from src.ai.narrative import generate_narrative


def _sample_report():
    return {
        "change_point": {"model_name": "mean_shift", "change_index": 120, "change_date": "2020-06-15"},
        "diagnostics": {"reliable": True, "warnings": []},
        "event_alignment": {
            "nearest_event": "OPEC+ Production Cut",
            "days_to_nearest_event": 3,
            "mean_return_before": 0.0001,
            "mean_return_after": 0.0021,
            "annualized_vol_before": 0.25,
            "annualized_vol_after": 0.55,
        },
    }


def test_generate_narrative_falls_back_to_template_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = generate_narrative(_sample_report())

    assert result["source"] == "template"
    assert "2020-06-15" in result["text"]
    assert len(result["text"]) > 0


def test_template_narrative_flags_unreliable_diagnostics(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    report = _sample_report()
    report["diagnostics"] = {"reliable": False, "warnings": ["min ess_bulk=50.0 below threshold 400.0"]}

    result = generate_narrative(report)

    assert "unreliable" in result["text"].lower() or "caution" in result["text"].lower()
