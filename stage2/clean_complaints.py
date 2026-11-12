#!/usr/bin/env python3
"""Clean BBMP grievance complaints into ward-day counts.

Ward-name matching is the existing one-to-one map in pipeline/labels.py.
The hour on Grievance Date is not used (the export is 1-12 with no AM/PM).
Does not download anything.
"""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.labels import (
    DRAIN_SUBCATS,
    FIRST_DAY,
    FLOOD_SUBCAT,
    LAST_DAY,
    NO_WARD,
    OPENCITY,
    ward_name_map,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import STAGE2_OUT, WARDS_CSV, ensure_out


def main():
    ensure_out()
    print("STEP 2  complaint cleaning")
    wards = pd.read_csv(WARDS_CSV)
    if len(wards) != 198:
        raise SystemExit(f"STOP: expected 198 wards, got {len(wards)}")
    name_to_id = dict(zip(wards["ward_name"], wards["ward_id"]))
    id_to_zone = dict(zip(wards["ward_id"], wards["zone"]))

    files = sorted(OPENCITY.glob("griev_*.csv"))
    if len(files) != 6:
        raise SystemExit(f"STOP: expected 6 griev_*.csv files, found {len(files)}")
    raw = pd.concat(
        [pd.read_csv(f, usecols=["Complaint ID", "Sub Category", "Grievance Date", "Ward Name"],
                     low_memory=False) for f in files],
        ignore_index=True,
    )
    n_raw = len(raw)
    n_missing_ward = int(raw["Ward Name"].isna().sum())
    n_non_ward = int((raw["Ward Name"] == NO_WARD).sum())
    g = raw.dropna(subset=["Ward Name"])
    g = g[g["Ward Name"] != NO_WARD].copy()

    mapping = ward_name_map(sorted(g["Ward Name"].unique()), wards["ward_name"].tolist())
    unmatched_map = [src for src, dst in mapping.items() if dst not in name_to_id]
    if unmatched_map:
        raise SystemExit(f"STOP: mapped ward names missing from wards.csv: {unmatched_map}")

    g["ward_name"] = g["Ward Name"].map(mapping)
    g["ward_id"] = g["ward_name"].map(name_to_id).astype(int)
    g["zone"] = g["ward_id"].map(id_to_zone)
    g["date"] = pd.to_datetime(g["Grievance Date"]).dt.normalize()
    g["sub"] = g["Sub Category"].astype(str).str.strip().str.lower()
    g["kind"] = "other"
    g.loc[g["sub"].eq(FLOOD_SUBCAT), "kind"] = "flood"
    g.loc[g["sub"].isin(DRAIN_SUBCATS), "kind"] = "drain"

    clean = pd.DataFrame({
        "complaint_id": g["Complaint ID"],
        "ward_id": g["ward_id"],
        "ward_name": g["ward_name"],
        "zone": g["zone"],
        "date": g["date"],
        "sub": g["sub"],
        "kind": g["kind"],
    })
    clean_path = STAGE2_OUT / "complaints_clean.csv"
    clean.to_csv(clean_path, index=False)

    sub_counts = (
        clean.groupby(["kind", "sub"], as_index=False)
        .size()
        .rename(columns={"size": "n"})
        .sort_values(["kind", "n"], ascending=[True, False])
    )
    sub_counts.to_csv(STAGE2_OUT / "complaint_subcategory_counts.csv", index=False)

    flood = clean[clean["kind"] == "flood"]
    if flood.empty:
        raise SystemExit("STOP: no water-stagnation complaints")
    if flood["date"].min() < pd.Timestamp(FIRST_DAY) or flood["date"].max() > pd.Timestamp(LAST_DAY):
        raise SystemExit(
            f"STOP: flood complaints span {flood['date'].min().date()} to {flood['date'].max().date()}, "
            f"outside {FIRST_DAY} .. {LAST_DAY}"
        )

    calendar = pd.date_range(FIRST_DAY, LAST_DAY, name="date")
    idx = pd.MultiIndex.from_product([wards["ward_id"].tolist(), calendar], names=["ward_id", "date"])

    def daily(mask):
        return clean[mask].groupby(["ward_id", "date"]).size().reindex(idx, fill_value=0)

    daily_df = pd.DataFrame({
        "n_flood": daily(clean["kind"].eq("flood")),
        "n_drain": daily(clean["kind"].eq("drain")),
        "n_other": daily(clean["kind"].eq("other")),
    }).reset_index()
    daily_df["y"] = (daily_df["n_flood"] > 0).astype(int)
    daily_path = STAGE2_OUT / "complaint_daily.csv"
    daily_df.to_csv(daily_path, index=False)

    print(f"raw complaints: {n_raw}")
    print(f"dropped missing ward: {n_missing_ward}; dropped '{NO_WARD}': {n_non_ward}")
    print(f"kept: {len(clean)}; flood rows: {int((clean.kind == 'flood').sum())}; "
          f"drain rows: {int((clean.kind == 'drain').sum())}")
    print(f"positive ward-days: {int(daily_df.y.sum())} of {len(daily_df)}")
    print(f"flood complaint dates: {flood['date'].min().date()} to {flood['date'].max().date()}")
    print(f"wrote {clean_path}")
    print(f"wrote {daily_path}")


if __name__ == "__main__":
    main()
