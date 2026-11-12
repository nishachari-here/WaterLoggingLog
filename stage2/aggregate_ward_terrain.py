#!/usr/bin/env python3
"""Aggregate Stage 1 node terrain onto the 198 BBMP wards.

Uses data/processed/nodes_labelled_v2.csv (already labelled and ward-tagged).
Does not rebuild the graph, rasters, or flood points.
"""
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    FLOOD_POINTS,
    NODES_V2,
    STAGE2_OUT,
    TERRAIN_MEAN_COLS,
    WARDS_CSV,
    WARDS_GEOJSON,
    cell_of,
    ensure_out,
)

CRS_METRIC = "EPSG:32643"


def main():
    ensure_out()
    print("STEP 1  ward terrain aggregation")
    for path in (NODES_V2, WARDS_CSV, WARDS_GEOJSON, FLOOD_POINTS):
        if not path.exists():
            raise SystemExit(f"STOP: missing Stage 1 input {path}")

    wards = pd.read_csv(WARDS_CSV)
    if len(wards) != 198 or wards["ward_id"].nunique() != 198:
        raise SystemExit(f"STOP: expected 198 wards, got {len(wards)}")

    geom = gpd.read_file(WARDS_GEOJSON)
    if geom.crs is None:
        raise SystemExit("STOP: wards.geojson has no CRS")
    area = geom.to_crs(CRS_METRIC)
    area_km2 = pd.Series(
        (area.geometry.area / 1e6).to_numpy(),
        index=area["ward_id"].astype(int).to_numpy(),
    )

    use_cols = ["ward_id", "node_type", "label", *TERRAIN_MEAN_COLS]
    nodes = pd.read_csv(NODES_V2, usecols=use_cols)
    inside = nodes[nodes["ward_id"] > 0].copy()
    missing_wards = set(wards["ward_id"]) - set(inside["ward_id"].unique())
    if missing_wards:
        raise SystemExit(f"STOP: wards with no Stage 1 nodes: {sorted(missing_wards)}")

    grouped = inside.groupby("ward_id", sort=True)
    means = grouped[TERRAIN_MEAN_COLS].mean()
    means.columns = [f"{c}_mean" for c in TERRAIN_MEAN_COLS]
    out = means.reset_index()
    out["n_nodes"] = grouped.size().to_numpy()
    out["n_road_nodes"] = grouped["node_type"].apply(lambda s: int((s == "road").sum())).to_numpy()
    out["n_drain_nodes"] = grouped["node_type"].apply(lambda s: int((s == "drain").sum())).to_numpy()
    out["n_positive_nodes"] = grouped["label"].sum().astype(int).to_numpy()
    out["positive_node_frac"] = out["n_positive_nodes"] / out["n_nodes"]
    out["hand_lt2_frac"] = grouped["hand_m"].apply(lambda s: float((s < 2).mean())).to_numpy()

    out = wards.merge(out, on="ward_id", how="left", validate="one_to_one")
    out["area_km2"] = out["ward_id"].map(area_km2)
    out["rain_cell"] = [cell_of(a, o) for a, o in zip(out["centroid_lat"], out["centroid_lon"])]

    floods = pd.read_csv(FLOOD_POINTS)
    counts = floods["ward"].value_counts()
    unknown = sorted(set(counts.index) - set(wards["ward_name"]))
    if unknown:
        raise SystemExit(f"STOP: flood-point ward names not in wards.csv: {unknown}")
    out["n_flood_pts"] = out["ward_name"].map(counts).fillna(0).astype(int)
    out["flood_pts_per_km2"] = out["n_flood_pts"] / out["area_km2"]

    null_cols = [c for c in out.columns if out[c].isna().any()]
    if null_cols:
        raise SystemExit(f"STOP: terrain aggregation nulls in {null_cols}")

    dest = STAGE2_OUT / "ward_terrain.csv"
    out = out.sort_values("ward_id")
    out.to_csv(dest, index=False)
    print(f"wards: {len(out)}")
    print(f"nodes inside wards: {int(out.n_nodes.sum())} (outside nodes excluded)")
    print(f"official flood points assigned: {int(out.n_flood_pts.sum())}")
    print(f"rain cells used: {sorted(out.rain_cell.unique())}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
