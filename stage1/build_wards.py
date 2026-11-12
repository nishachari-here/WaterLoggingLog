#!/usr/bin/env python3
"""Export the 2015 BBMP ward polygons used for zone hold-out."""
from pathlib import Path
import sys

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CRS_METRIC, CRS_WGS84, PROCESSED, ensure_dirs, load_wards


def main():
    ensure_dirs()
    print("STEP 2  wards")
    wards = load_wards()
    metric = wards.to_crs(CRS_METRIC)
    centroids = metric.centroid.to_crs(CRS_WGS84)
    table = wards[["ward_id", "ward_name", "zone"]].copy()
    table["centroid_lat"] = centroids.y.values
    table["centroid_lon"] = centroids.x.values
    n_zones = table["zone"].nunique()
    print(f"wards: {len(table)} (expected 198)")
    print(f"zones: {n_zones} (expected 8) -> {sorted(table['zone'].unique())}")
    if len(table) != 198 or n_zones != 8:
        raise SystemExit("STOP: ward/zone counts do not match 198 wards and 8 zones.")

    csv_path = PROCESSED / "wards.csv"
    gj_path = PROCESSED / "wards.geojson"
    table.to_csv(csv_path, index=False)
    gpd.GeoDataFrame(
        table.assign(geometry=wards.geometry.values),
        geometry="geometry",
        crs=CRS_WGS84,
    ).to_file(gj_path, driver="GeoJSON")
    print(f"wrote {csv_path}")
    print(f"wrote {gj_path}")


if __name__ == "__main__":
    main()
