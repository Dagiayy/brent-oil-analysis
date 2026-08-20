import numpy as np
import pandas as pd

from src.insights.event_alignment import build_alignment_report, find_nearest_event, quantify_shift


def test_find_nearest_event_picks_closest_in_time(synthetic_events):
    change_date = pd.Timestamp("2020-03-20")
    nearest = find_nearest_event(change_date, synthetic_events, max_window_days=90)

    assert nearest["Event"] == "Synthetic Event A"  # 2020-03-15, 5 days away vs. B at 78 days


def test_find_nearest_event_returns_none_outside_window(synthetic_events):
    change_date = pd.Timestamp("2022-01-01")
    nearest = find_nearest_event(change_date, synthetic_events, max_window_days=30)

    assert nearest is None


def test_find_nearest_event_empty_events_returns_none():
    change_date = pd.Timestamp("2020-03-20")
    assert find_nearest_event(change_date, pd.DataFrame(columns=["Event", "Start Date"])) is None


def test_quantify_shift_detects_mean_shift():
    dates = pd.date_range("2020-01-01", periods=20)
    returns = np.array([0.0] * 10 + [0.1] * 10)
    prices = 100 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({"Date": dates, "Price": prices, "Log_Return": returns})

    shift = quantify_shift(df, change_date=dates[10])

    assert shift["mean_return_before"] == 0.0
    assert shift["mean_return_after"] > shift["mean_return_before"]


def test_build_alignment_report_end_to_end(synthetic_events, processed_prices_df):
    change_date = processed_prices_df["Date"].iloc[len(processed_prices_df) // 2]
    report = build_alignment_report(processed_prices_df, change_date, synthetic_events)

    d = report.to_dict()
    assert d["change_date"] == str(change_date.date())
    assert "mean_return_before" in d
    assert "mean_return_after" in d
