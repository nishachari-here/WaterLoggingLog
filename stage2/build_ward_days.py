#!/usr/bin/env python3
"""Join ward terrain, cleaned complaint counts, and daily rain into one ward-day table.

One row is one ward on one day. y is 1 when that ward has at least one
water-stagnation complaint that day. drain_30d uses only earlier days.
"""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import STAGE2_OUT, ensure_out


RAIN_COLS = ["rain", "peak", "sm", "rain_lag1", "rain_2d", "rain_3d", "rain_ante7", "peak_2d", "sm_prev"]


def main():
    ensure_out()
    print("STEP 4  ward-day dataset")
    terrain_path = STAGE2_OUT / "ward_terrain.csv"
    daily_path = STAGE2_OUT / "complaint_daily.csv"
    rain_path = STAGE2_OUT / "rain_daily.csv"
    for path in (terrain_path, daily_path, rain_path):
        if not path.exists():
            raise SystemExit(f"STOP: missing {path}. Run the earlier Stage 2 steps first.")

    terrain = pd.read_csv(terrain_path)
    daily = pd.read_csv(daily_path, parse_dates=["date"])
    rain = pd.read_csv(rain_path, parse_dates=["date"])

    if daily["ward_id"].nunique() != 198:
        raise SystemExit(f"STOP: complaint_daily has {daily['ward_id'].nunique()} wards")

    static_cols = [c for c in terrain.columns if c != "ward_name"]
    df = daily.merge(terrain[static_cols], on="ward_id", how="left", validate="many_to_one")
    if df["rain_cell"].isna().any():
        raise SystemExit("STOP: some ward-days have no rain cell")

    df = df.merge(
        rain.rename(columns={"cell": "rain_cell"}),
        on=["rain_cell", "date"],
        how="left",
        validate="many_to_one",
    )
    missing_rain = int(df["rain"].isna().sum())
    if missing_rain:
        sample = df.loc[df["rain"].isna(), ["ward_id", "date", "rain_cell"]].head()
        raise SystemExit(f"STOP: {missing_rain} ward-days have no rain row.\n{sample}")

    df = df.sort_values(["ward_id", "date"])
    df["drain_30d"] = (
        df.groupby("ward_id", sort=False)["n_drain"]
        .transform(lambda s: s.shift(1).rolling(30, min_periods=1).sum())
        .fillna(0.0)
    )
    df["month"] = df["date"].dt.month.astype(int)

    front = ["ward_id", "ward_name", "zone", "date", "y", "n_flood", "n_drain", "n_other",
             "rain_cell", "month", "drain_30d", *RAIN_COLS]
    # ward_name is not in static_cols; take it from terrain.
    df = df.merge(terrain[["ward_id", "ward_name"]], on="ward_id", how="left", validate="many_to_one")
    rest = [c for c in df.columns if c not in front]
    df = df[front + rest]

    if df["y"].isna().any() or df["drain_30d"].isna().any():
        raise SystemExit("STOP: null labels or drain_30d")

    dest = STAGE2_OUT / "ward_days.csv"
    df.to_csv(dest, index=False)
    print(f"ward-days: {len(df)}; wards: {df.ward_id.nunique()}")
    print(f"positives: {int(df.y.sum())}")
    print(f"dates: {df.date.min().date()} to {df.date.max().date()}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
