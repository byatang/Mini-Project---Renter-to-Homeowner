import pandas as pd
import pytest

import home_values as hv


@pytest.fixture
def raw():
    """A tiny stand-in for Zillow's national file: 13 months, two DFW ZIPs, one elsewhere."""
    months = [f"2025-{m:02d}-28" for m in range(8, 13)] + [f"2026-{m:02d}-28" for m in range(1, 9)]
    rows = [
        ("75001", "Addison", "Dallas County", hv.DFW_METRO, 400_000, 420_000),
        ("76104", "Fort Worth", "Tarrant County", hv.DFW_METRO, 200_000, 190_000),
        ("78701", "Austin", "Travis County", "Austin-Round Rock, TX", 500_000, 550_000),
    ]
    data = []
    for zip_code, city, county, metro, first, last in rows:
        values = {m: first + (last - first) * i / 12 for i, m in enumerate(months)}
        data.append({"RegionID": 1, "RegionName": int(zip_code), "City": city,
                     "CountyName": county, "Metro": metro, **values})
    return pd.DataFrame(data)


def test_tidy_keeps_only_dfw_with_latest_value_and_yearly_change(raw):
    df = hv.tidy_zhvi(raw)
    assert df["zip"].tolist() == ["75001", "76104"]
    addison = df.iloc[0]
    assert addison["typical_value"] == 420_000
    assert addison["value_1yr_ago"] == 400_000
    assert addison["change_1yr"] == pytest.approx(0.05)
    assert addison["as_of"] == "2026-08-28"


def test_zip_codes_keep_leading_zeros(raw):
    raw["RegionName"] = [1001, 76104, 78701]
    assert hv.tidy_zhvi(raw)["zip"].iloc[0] == "01001"


def test_filter_and_affordability(raw):
    df = hv.tidy_zhvi(raw)
    assert hv.zips_in(df, county="Tarrant County")["zip"].tolist() == ["76104"]
    assert hv.zips_in(df)["zip"].tolist() == ["76104", "75001"]  # cheapest first

    flagged = hv.with_affordability(df, 300_000).set_index("zip")
    assert flagged.loc["76104", "within_budget"]
    assert not flagged.loc["75001", "within_budget"]
    assert flagged.loc["75001", "gap"] == 120_000
    assert flagged.loc["76104", "gap"] == 0


def test_saved_data_file_looks_right():
    df = hv.load()
    assert len(df) > 200
    assert df["zip"].str.fullmatch(r"\d{5}").all()
    assert {"Dallas County", "Tarrant County", "Collin County", "Denton County"} <= set(df["county"])
