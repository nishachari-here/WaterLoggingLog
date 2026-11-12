#!/usr/bin/env python3
"""Daily rain and soil-moisture features from the cached hourly file.

Reads data/rain/rain_hourly.csv only. Does not call the Open-Meteo API.
Feature definitions match pipeline/rain_history.daily_features.
"""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAIN_HOURLY, STAGE2_OUT, ensure_out


def main():
    ensure_out()
    print("STEP 3  rainfall feature engineering")
    if not RAIN_HOURLY.exists():
        raise SystemExit(f"STOP: cached rain file missing: {RAIN_HOURLY}. Not downloading.")

    hourly = pd.read_csv(RAIN_HOURLY, parse_dates=["time"])
    needed = {"time", "cell", "mm", "sm"}
    if not needed.issubset(hourly.columns):
        raise SystemExit(f"STOP: rain columns {list(hourly.columns)} missing {needed - set(hourly.columns)}")
    if hourly[["mm", "sm"]].isna().any().any():
        raise SystemExit("STOP: rain cache has null mm or sm")

    hourly["date"] = hourly["time"].dt.normalize()
    daily = (
        hourly.groupby(["cell", "date"], sort=True)
        .agg(rain=("mm", "sum"), peak=("mm", "max"), sm=("sm", "mean"), n_hours=("mm", "size"))
        .reset_index()
    )
    bad_hours = daily.loc[daily["n_hours"] != 24, ["cell", "date", "n_hours"]]
    if len(bad_hours):
        raise SystemExit(f"STOP: {len(bad_hours)} cell-days are not 24 hours. First:\n{bad_hours.head()}")

    by_cell = daily.groupby("cell", sort=False)
    daily["rain_lag1"] = by_cell["rain"].shift(1)
    daily["rain_3d"] = by_cell["rain"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    daily["rain_ante7"] = by_cell["rain"].transform(lambda s: s.shift(1).rolling(7, min_periods=1).sum())
    daily["peak_2d"] = by_cell["peak"].transform(lambda s: s.rolling(2, min_periods=1).max())
    daily["sm_prev"] = by_cell["sm"].shift(1)
    # First calendar day of the archive has no previous day. Ward-days start in February.
    daily["rain_lag1"] = daily["rain_lag1"].fillna(0.0)
    daily["rain_ante7"] = daily["rain_ante7"].fillna(0.0)
    daily["sm_prev"] = daily.groupby("cell", sort=False)["sm_prev"].bfill()
    daily["rain_2d"] = daily["rain"] + daily["rain_lag1"]

    keep = ["cell", "date", "rain", "peak", "sm", "rain_lag1", "rain_2d", "rain_3d",
            "rain_ante7", "peak_2d", "sm_prev"]
    out = daily[keep].copy()
    if out[keep[2:]].isna().any().any():
        raise SystemExit("STOP: daily rain features contain nulls after fill")

    dest = STAGE2_OUT / "rain_daily.csv"
    out.to_csv(dest, index=False)
    print(f"hourly rows: {len(hourly)}; cells: {sorted(hourly['cell'].unique())}")
    print(f"daily rows: {len(out)}; {out['date'].min().date()} to {out['date'].max().date()}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
