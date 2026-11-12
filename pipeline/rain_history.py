"""Hourly rain and soil moisture, 2020 to mid-2025, from the Open-Meteo archive API (free, no key).

The archive grid is coarse (about 10 km), so wards are grouped into 0.1 degree cells and each cell is
fetched once. The result is kept in data/rain/rain_hourly.csv so training does not depend on the API.
"""
import time

import pandas as pd
import requests
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import config

URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE = config.ROOT / "data" / "rain" / "rain_hourly.csv"
YEARS = range(2020, 2026)
LAST_DAY = "2025-06-30"


def cell_of(lat, lon):
    return f"{round(lat, 1)}_{round(lon, 1)}"


def hourly(wards):
    """Long table: time, cell, mm (rain in that hour), sm (soil moisture 0-7 cm)."""
    if CACHE.exists():
        return pd.read_csv(CACHE, parse_dates=["time"])
    cells = sorted({cell_of(a, o) for a, o in zip(wards.lat, wards.lon)})
    lats, lons = [c.split("_")[0] for c in cells], [c.split("_")[1] for c in cells]
    frames = []
    for y in YEARS:
        params = {"latitude": ",".join(lats), "longitude": ",".join(lons), "start_date": f"{y}-01-01",
                  "end_date": f"{y}-12-31" if y < 2025 else LAST_DAY,
                  "hourly": "precipitation,soil_moisture_0_to_7cm", "timezone": "Asia/Kolkata"}
        for _ in range(4):
            r = requests.get(URL, params=params, timeout=180)
            if r.status_code == 200:
                break
            time.sleep(20)  # the free tier rate-limits long requests
        r.raise_for_status()
        data = r.json()
        for cell, loc in zip(cells, data if isinstance(data, list) else [data]):
            frames.append(pd.DataFrame({"time": pd.to_datetime(loc["hourly"]["time"]), "cell": cell,
                                        "mm": loc["hourly"]["precipitation"],
                                        "sm": loc["hourly"]["soil_moisture_0_to_7cm"]}))
        print(f"  rain {y} fetched")
    out = pd.concat(frames)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE, index=False)
    return out


def daily_features(wards):
    """Per cell and day: rain totals, peak hour, lags and antecedent soil moisture."""
    r = hourly(wards)
    r["date"] = r.time.dt.normalize()
    d = r.groupby(["cell", "date"]).agg(rain=("mm", "sum"), peak=("mm", "max"), sm=("sm", "mean")).reset_index()
    c = d.groupby("cell", sort=False)
    d["rain_lag1"] = c.rain.shift(1).fillna(0)
    d["rain_3d"] = c.rain.transform(lambda s: s.rolling(3, min_periods=1).sum())
    d["rain_ante7"] = c.rain.transform(lambda s: s.shift(1).rolling(7, min_periods=1).sum()).fillna(0)
    d["peak_2d"] = c.peak.transform(lambda s: s.rolling(2, min_periods=1).max())
    d["sm_prev"] = c.sm.shift(1).bfill()
    return d
