#!/usr/bin/env python3
"""Assign each ward-day to train, tune, or test by calendar year.

Train 2020-02-08 through 2022-12-31.
Tune all of 2023.
Test 2024-01-01 through 2025-06-19.

No random split and no model fitting.
"""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import STAGE2_OUT, ensure_out

SUMMARY_PATH = Path(__file__).resolve().parent / "split_summary.csv"


def assign_split(dates: pd.Series) -> pd.Series:
    year = dates.dt.year
    split = pd.Series(pd.NA, index=dates.index, dtype="object")
    split = split.mask(year <= 2022, "train")
    split = split.mask(year == 2023, "tune")
    split = split.mask(year >= 2024, "test")
    if split.isna().any():
        raise SystemExit("STOP: a date was not assigned a split")
    return split


def main():
    ensure_out()
    print("STEP 5  temporal splits")
    src = STAGE2_OUT / "ward_days.csv"
    if not src.exists():
        raise SystemExit(f"STOP: missing {src}")

    df = pd.read_csv(src, parse_dates=["date"])
    df["split"] = assign_split(df["date"])

    dest = STAGE2_OUT / "ward_days_split.csv"
    df.to_csv(dest, index=False)

    summary = (
        df.groupby("split", sort=False)
        .agg(ward_days=("y", "size"), positive_ward_days=("y", "sum"),
             date_min=("date", "min"), date_max=("date", "max"), wards=("ward_id", "nunique"))
        .reindex(["train", "tune", "test"])
        .reset_index()
    )
    summary["date_min"] = summary["date_min"].dt.date.astype(str)
    summary["date_max"] = summary["date_max"].dt.date.astype(str)
    summary.to_csv(SUMMARY_PATH, index=False)
    summary.to_csv(STAGE2_OUT / "split_summary.csv", index=False)

    print(summary.to_string(index=False))
    print(f"wrote {dest}")
    print(f"wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
