"""Typical home values by ZIP code in Dallas-Fort Worth.

Source: Zillow Home Value Index (ZHVI), all homes (single-family + condo), mid-tier,
smoothed and seasonally adjusted. Free public download from
https://www.zillow.com/research/data/ -- no scraping.

Map coordinates: U.S. Census Bureau Gazetteer, the center point of each ZIP (ZCTA).

Refresh the saved data (Zillow updates monthly):  python home_values.py
"""

from pathlib import Path

import pandas as pd

ZHVI_URL = ("https://files.zillowstatic.com/research/public_csvs/zhvi/"
            "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")
DFW_METRO = "Dallas-Fort Worth-Arlington, TX"
DATA_FILE = Path(__file__).parent / "data" / "dfw_zip_home_values.csv"
SOURCE_NOTE = "Home values: Zillow Home Value Index (ZHVI), zillow.com/research/data"


# ---------- Refresh from Zillow ----------

def tidy_zhvi(raw):
    """Turn Zillow's wide table (one column per month) into one row per DFW ZIP."""
    dfw = raw[raw["Metro"] == DFW_METRO]
    months = sorted(c for c in raw.columns if c[:2] in ("19", "20"))
    latest, year_ago = months[-1], months[-13]
    out = pd.DataFrame({
        "zip": dfw["RegionName"].astype(str).str.zfill(5),
        "city": dfw["City"],
        "county": dfw["CountyName"],
        "typical_value": dfw[latest].round(0),
        "value_1yr_ago": dfw[year_ago].round(0),
    })
    out["change_1yr"] = (out["typical_value"] / out["value_1yr_ago"] - 1).round(4)
    out["as_of"] = latest
    return out.dropna(subset=["typical_value"]).sort_values("zip").reset_index(drop=True)


def refresh(url=ZHVI_URL, path=DATA_FILE):
    """Download the national file (~120 MB), keep DFW, save a small CSV."""
    print("Downloading Zillow ZHVI (about 120 MB)...")
    df = tidy_zhvi(pd.read_csv(url))
    path.parent.mkdir(exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} DFW ZIP codes (as of {df['as_of'].iloc[0]}) to {path}")
    return df


# ---------- ZIP locations for the map (U.S. Census Bureau) ----------

LOCATIONS_URL = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
                 "2024_Gaz_zcta_national.zip")
LOCATIONS_FILE = Path(__file__).parent / "data" / "dfw_zip_locations.csv"
LOCATIONS_NOTE = "ZIP locations: U.S. Census Bureau 2024 Gazetteer (ZCTA centers)"


def tidy_locations(raw, zips):
    """Keep the center point of each ZIP we have home values for."""
    raw.columns = [c.strip() for c in raw.columns]       # the last header has trailing spaces
    raw["zip"] = raw["GEOID"].astype(str).str.zfill(5)
    out = raw[raw["zip"].isin(set(zips))]
    return (out.rename(columns={"INTPTLAT": "lat", "INTPTLONG": "lon"})[["zip", "lat", "lon"]]
            .sort_values("zip").reset_index(drop=True))


def refresh_locations(url=LOCATIONS_URL, path=LOCATIONS_FILE):
    """Download the national Census file (~1 MB), keep the DFW ZIPs, save a small CSV."""
    raw = pd.read_csv(url, sep="\t", dtype={"GEOID": str}, compression="zip")
    df = tidy_locations(raw, load()["zip"])
    df.to_csv(path, index=False)
    print(f"Saved map locations for {len(df)} DFW ZIP codes to {path}")
    return df


# ---------- Lookups used by the app ----------

def load(path=DATA_FILE, locations=LOCATIONS_FILE):
    """Home values by ZIP, with map coordinates added when the locations file exists."""
    df = pd.read_csv(path, dtype={"zip": str})
    if Path(locations).exists():
        df = df.merge(pd.read_csv(locations, dtype={"zip": str}), on="zip", how="left")
    return df


def areas(df):
    """Counties and cities to choose from, largest (most ZIPs) first."""
    return {
        "county": df["county"].value_counts().index.tolist(),
        "city": df["city"].value_counts().index.tolist(),
    }


def zips_in(df, county=None, city=None):
    """ZIPs in the chosen county and/or city, cheapest first."""
    rows = df
    if county:
        rows = rows[rows["county"] == county]
    if city:
        rows = rows[rows["city"] == city]
    return rows.sort_values("typical_value").reset_index(drop=True)


def with_affordability(df, max_price):
    """Add a column saying whether the typical home in each ZIP is within budget."""
    out = df.copy()
    out["within_budget"] = out["typical_value"] <= max_price
    out["gap"] = (out["typical_value"] - max_price).clip(lower=0)
    return out


if __name__ == "__main__":
    refresh()
    refresh_locations()
