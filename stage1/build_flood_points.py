#!/usr/bin/env python3
"""Build official BBMP flood points (no synthetic labels)."""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CRS_METRIC,
    CRS_WGS84,
    FLOOD_KMLS,
    PROCESSED,
    canonical_zone,
    ensure_dirs,
    load_wards,
)

MERGE_M = 100.0
EXPECTED_RAW = 399
EXPECTED_INSIDE = 395
EXPECTED_MERGED = 372


def _name_series(gdf: gpd.GeoDataFrame) -> pd.Series:
    if "LocationName" in gdf.columns:
        name = gdf["LocationName"].copy()
        if "Name" in gdf.columns:
            name = name.fillna(gdf["Name"])
        return name
    if "Name" in gdf.columns:
        return gdf["Name"].copy()
    raise KeyError(f"No name column in columns {list(gdf.columns)}")


def read_flood_layers() -> gpd.GeoDataFrame:
    frames = []
    for layer, path in FLOOD_KMLS.items():
        gdf = gpd.read_file(path)
        print(f"  {path.name}: {len(gdf)} features, columns={list(gdf.columns)}")
        if gdf.crs is None:
            gdf = gdf.set_crs(CRS_WGS84)
        else:
            gdf = gdf.to_crs(CRS_WGS84)
        gdf["geometry"] = shapely.force_2d(gdf.geometry)
        frames.append(
            gpd.GeoDataFrame(
                {
                    "name": _name_series(gdf).astype(str).str.replace("\n", " ").str.strip(),
                    "ward_attr": gdf["WARD_NAME"] if "WARD_NAME" in gdf.columns else pd.NA,
                    "zone_attr": gdf["ZONE"] if "ZONE" in gdf.columns else pd.NA,
                    "layer": layer,
                    "geometry": gdf.geometry,
                },
                crs=CRS_WGS84,
            )
        )
    out = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=CRS_WGS84)


def merge_clusters(points: gpd.GeoDataFrame, radius_m: float) -> gpd.GeoDataFrame:
    metric = points.to_crs(CRS_METRIC)
    xy = np.c_[metric.geometry.x, metric.geometry.y]
    n = len(metric)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j in cKDTree(xy).query_pairs(radius_m):
        union(i, j)
    comp = np.array([find(i) for i in range(n)])

    rows = []
    for cid in np.unique(comp):
        idx = np.flatnonzero(comp == cid)
        centroid = xy[idx].mean(axis=0)
        rep = idx[np.argmin(np.linalg.norm(xy[idx] - centroid, axis=1))]
        members = metric.iloc[idx]
        layers = "|".join(sorted(set(members["layer"].tolist())))
        geom = shapely.Point(float(xy[rep, 0]), float(xy[rep, 1]))
        rows.append(
            {
                "name": metric.iloc[rep]["name"],
                "ward_attr": metric.iloc[rep]["ward_attr"],
                "zone_attr": metric.iloc[rep]["zone_attr"],
                "layer": layers,
                "geometry": geom,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS_METRIC)


def spatial_join_wards(points_metric: gpd.GeoDataFrame, wards: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    wards_m = wards.to_crs(CRS_METRIC)[["ward_id", "ward_name", "zone", "geometry"]]
    joined = gpd.sjoin(points_metric, wards_m, predicate="within", how="left")
    dup = joined.index.duplicated(keep=False).sum()
    if dup:
        print(f"WARNING: {dup} flood-point rows matched more than one ward; keeping first by ward_id.")
        joined = joined.sort_values("ward_id").loc[~joined.index.duplicated(keep="first")]
    missing = joined["ward_id"].isna().sum()
    if missing:
        leftover = joined[joined["ward_id"].isna()].drop(columns=["index_right", "ward_id", "ward_name", "zone"], errors="ignore")
        extra = gpd.sjoin(leftover, wards_m, predicate="intersects", how="left")
        extra = extra.sort_values("ward_id").loc[~extra.index.duplicated(keep="first")]
        joined.loc[extra.index, ["ward_id", "ward_name", "zone"]] = extra[["ward_id", "ward_name", "zone"]]
        still = joined["ward_id"].isna().sum()
        print(f"  within-miss {missing}; after intersects still missing {still}")
    return joined


def main():
    ensure_dirs()
    print("STEP 1  flood points")
    raw = read_flood_layers()
    print(f"raw flood points: {len(raw)} (expected {EXPECTED_RAW})")
    if abs(len(raw) - EXPECTED_RAW) > 10:
        print(f"WARNING: raw count {len(raw)} is far from {EXPECTED_RAW}")

    wards = load_wards()
    city = wards.to_crs(CRS_METRIC).union_all()
    metric = raw.to_crs(CRS_METRIC)
    inside = metric[metric.within(city)].copy()
    print(f"inside 2015 ward boundary: {len(inside)} (expected ~{EXPECTED_INSIDE}; dropped {len(metric) - len(inside)})")
    if abs(len(inside) - EXPECTED_INSIDE) > 15:
        print(f"WARNING: inside count {len(inside)} is far from {EXPECTED_INSIDE}")

    merged = merge_clusters(inside.to_crs(CRS_WGS84), MERGE_M)
    print(f"after {MERGE_M:.0f} m merge: {len(merged)} (expected ~{EXPECTED_MERGED})")
    if abs(len(merged) - EXPECTED_MERGED) > 20:
        print(f"WARNING: merged count {len(merged)} is far from {EXPECTED_MERGED}")

    joined = spatial_join_wards(merged, wards)
    wgs = joined.to_crs(CRS_WGS84)
    out = pd.DataFrame(
        {
            "name": wgs["name"].values,
            "ward": wgs["ward_name"].values,
            "zone": wgs["zone"].values,
            "layer": wgs["layer"].values,
            "lat": wgs.geometry.y.values,
            "lon": wgs.geometry.x.values,
            "ward_attr": wgs["ward_attr"].values,
            "zone_attr": wgs["zone_attr"].values,
        }
    )
    if out["zone"].isna().any():
        n = int(out["zone"].isna().sum())
        raise SystemExit(f"STOP: {n} merged flood points have no ward/zone after spatial join.")

    def _cmp_zone(attr, official):
        if pd.isna(attr) or str(attr).strip() == "" or str(attr) == "nan":
            return False
        try:
            return canonical_zone(attr) != official
        except ValueError:
            return True

    def _cmp_ward(attr, official):
        if pd.isna(attr) or str(attr).strip() == "" or str(attr) == "nan":
            return False
        a = " ".join(str(attr).replace("\xa0", " ").split()).strip().lower()
        b = " ".join(str(official).replace("\xa0", " ").split()).strip().lower()
        return a != b

    zone_dis = sum(_cmp_zone(a, z) for a, z in zip(out["zone_attr"], out["zone"]))
    ward_dis = sum(_cmp_ward(a, w) for a, w in zip(out["ward_attr"], out["ward"]))
    n_with_zone_attr = int(out["zone_attr"].notna().sum())
    n_with_ward_attr = int(out["ward_attr"].notna().sum())
    print(f"zone_attr vs spatial zone disagreements: {zone_dis} / {n_with_zone_attr} points that had a KML zone")
    print(f"ward_attr vs spatial ward disagreements: {ward_dis} / {n_with_ward_attr} points that had a KML ward")
    print(f"counts: {len(raw)} -> {len(inside)} -> {len(out)}")

    dest = PROCESSED / "flood_points.csv"
    out.to_csv(dest, index=False)
    print(f"wrote {dest} ({len(out)} rows)")


if __name__ == "__main__":
    main()
