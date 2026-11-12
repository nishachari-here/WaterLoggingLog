#!/usr/bin/env python3
"""Distance to official BBMP drains and drain length within 500 m."""
from pathlib import Path
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CRS_METRIC,
    CRS_WGS84,
    PROCESSED,
    SWD_PRIMARY,
    SWD_SECONDARY,
    ensure_dirs,
)

BUFFER_M = 500.0


def load_drains():
    frames = []
    for path in (SWD_PRIMARY, SWD_SECONDARY):
        gdf = gpd.read_file(path)
        print(f"  {path.name}: {len(gdf)} {gdf.geometry.geom_type.value_counts().to_dict()}")
        if gdf.crs is None:
            gdf = gdf.set_crs(CRS_WGS84)
        else:
            gdf = gdf.to_crs(CRS_WGS84)
        gdf["geometry"] = shapely.force_2d(gdf.geometry)
        frames.append(gdf[["geometry"]])
    drains = pd.concat(frames, ignore_index=True)
    drains = gpd.GeoDataFrame(drains, geometry="geometry", crs=CRS_WGS84).to_crs(CRS_METRIC)
    drains = drains.explode(index_parts=False).reset_index(drop=True)
    drains = drains[~drains.geometry.is_empty]
    print(f"  exploded line parts: {len(drains)}  total length_m={drains.length.sum():.1f}")
    return drains


def main():
    ensure_dirs()
    print("STEP 5  official drain features")
    t0 = time.perf_counter()
    nodes = pd.read_csv(PROCESSED / "nodes_labelled.csv")
    transformer = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    x_m, y_m = transformer.transform(nodes["lon"].to_numpy(), nodes["lat"].to_numpy())
    pts = shapely.points(x_m, y_m)

    drains = load_drains()
    line_arr = shapely.from_wkb(drains.geometry.to_wkb())
    tree = STRtree(line_arr)
    nearest_idx = np.asarray(tree.nearest(pts))
    dist = shapely.distance(pts, line_arr[nearest_idx])

    density = np.zeros(len(nodes), dtype=np.float64)
    pt_tree = STRtree(pts)
    for line in line_arr:
        minx, miny, maxx, maxy = line.bounds
        box = shapely.box(minx - BUFFER_M, miny - BUFFER_M, maxx + BUFFER_M, maxy + BUFFER_M)
        cand = np.asarray(pt_tree.query(box), dtype=int)
        if cand.size == 0:
            continue
        cand_pts = pts[cand]
        near = shapely.dwithin(cand_pts, line, BUFFER_M)
        if not np.any(near):
            continue
        hit = cand[near]
        buf = shapely.buffer(pts[hit], BUFFER_M)
        density[hit] += shapely.length(shapely.intersection(buf, line))

    nodes["dist_to_official_drain_m"] = dist
    nodes["drain_density_500m"] = density
    elapsed = time.perf_counter() - t0
    print(f"runtime: {elapsed:.1f} s")
    print(
        "dist_to_official_drain_m: "
        f"min={dist.min():.1f} median={np.median(dist):.1f} max={dist.max():.1f}"
    )
    print(
        "drain_density_500m: "
        f"min={density.min():.1f} median={np.median(density):.1f} max={density.max():.1f}"
    )
    dest = PROCESSED / "nodes_labelled_v2.csv"
    nodes.to_csv(dest, index=False)
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
