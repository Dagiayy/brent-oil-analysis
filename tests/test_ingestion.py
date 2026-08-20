import pandas as pd
import pytest

from src.data.ingestion import DataValidationError, load_events, load_raw_prices


def test_load_raw_prices_parses_and_sorts(tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("Date,Price\n02-Jan-20,11.0\n01-Jan-20,10.0\n", encoding="utf-8")

    df = load_raw_prices(csv_path)

    assert list(df["Price"]) == [10.0, 11.0]
    assert df["Date"].is_monotonic_increasing


def test_load_raw_prices_handles_mixed_date_formats(tmp_path):
    """Regression test: the real BrentOilPrices.csv switches from '%d-%b-%y'
    to '%b %d, %Y' partway through, which silently dropped ~7% of rows
    (the entire 2020-2022 tail, including the 2022 Russia-Ukraine shock)
    before _parse_mixed_format_dates was introduced."""
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        'Date,Price\n20-Apr-20,10.0\n"Apr 22, 2020",11.0\n"Nov 14, 2022",90.0\n',
        encoding="utf-8",
    )

    df = load_raw_prices(csv_path)

    assert len(df) == 3
    assert list(df["Date"]) == list(pd.to_datetime(["2020-04-20", "2020-04-22", "2022-11-14"]))
    assert list(df["Price"]) == [10.0, 11.0, 90.0]
    assert df["Date"].is_monotonic_increasing


def test_load_raw_prices_missing_column_raises(tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("Date,Value\n01-Jan-20,10.0\n", encoding="utf-8")

    with pytest.raises(DataValidationError):
        load_raw_prices(csv_path)


def test_load_raw_prices_rejects_non_positive_prices(tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("Date,Price\n01-Jan-20,-5.0\n", encoding="utf-8")

    with pytest.raises(DataValidationError):
        load_raw_prices(csv_path)


def test_load_raw_prices_drops_unparseable_rows(tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("Date,Price\n01-Jan-20,10.0\nnot-a-date,11.0\n02-Jan-20,not-a-number\n", encoding="utf-8")

    df = load_raw_prices(csv_path)

    assert len(df) == 1


def test_load_events_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_events(tmp_path / "does_not_exist.xlsx")


def test_load_events_normalizes_column_names(tmp_path):
    xlsx_path = tmp_path / "events.xlsx"
    pd.DataFrame(
        {
            "Event Name": ["Test Event"],
            "date": ["2020-01-01"],
            "Description": ["desc"],
        }
    ).to_excel(xlsx_path, index=False)

    df = load_events(xlsx_path)

    assert list(df.columns[:2]) == ["Event", "Start Date"]
    assert df.loc[0, "Event"] == "Test Event"
