#!/usr/bin/env python3
"""Attach flood labels and ward/zone to graph nodes.

label = 1 if the node is within 150 m of a merged official BBMP flood point.
labelled_status is "positive" or "unlabelled".
label 0 means "not known to flood", NOT "safe".
"""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CRS_METRIC,
    CRS_WGS84,
    NODES_GRAPH,
    PROCESSED,
    ensure_dirs,
    load_wards,
)

LABEL_RADIUS_M = 150.0


def main():
    ensure_dirs()
    print("STEP 3  label nodes")
    # label 0 = unlabelled ("not known to flood"), NOT a negative "safe" class.
    nodes = pd.read_csv(NODES_GRAPH)
    print(f"loaded {len(nodes)} nodes from {NODES_GRAPH}")

    transformer = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    x_m, y_m = transformer.transform(nodes["lon"].to_numpy(), nodes["lat"].to_numpy())
    node_xy = np.c_[x_m, y_m]

    flood = pd.read_csv(PROCESSED / "flood_points.csv")
    fx, fy = transformer.transform(flood["lon"].to_numpy(), flood["lat"].to_numpy())
    flood_xy = np.c_[fx, fy]
    dist, _ = cKDTree(flood_xy).query(node_xy, k=1)
    label = (dist <= LABEL_RADIUS_M).astype(int)
    # label 0 means "not known to flood", NOT "safe".
    labelled_status = np.where(label == 1, "positive", "unlabelled")

    node_gdf = gpd.GeoDataFrame(
        nodes,
        geometry=gpd.points_from_xy(node_xy[:, 0], node_xy[:, 1]),
        crs=CRS_METRIC,
    )
    wards = load_wards().to_crs(CRS_METRIC)[["ward_id", "ward_name", "zone", "geometry"]]
    joined = gpd.sjoin(node_gdf, wards, predicate="within", how="left")
    n_multi = int(joined.index.duplicated().sum())
    if n_multi:
        print(f"WARNING: {n_multi} nodes matched multiple wards; keeping lowest ward_id.")
        joined = joined.sort_values("ward_id").loc[~joined.index.duplicated(keep="first")]
    still = joined["ward_id"].isna()
    if still.any():
        extra = gpd.sjoin(
            node_gdf.loc[still[still].index],
            wards,
            predicate="intersects",
            how="left",
        )
        extra = extra.sort_values("ward_id").loc[~extra.index.duplicated(keep="first")]
        joined.loc[extra.index, ["ward_id", "ward_name", "zone"]] = extra[["ward_id", "ward_name", "zone"]]

    out = nodes.copy()
    out["label"] = label
    out["labelled_status"] = labelled_status
    out["ward_id"] = joined["ward_id"].fillna(-1).astype(int).to_numpy()
    out["ward_name"] = joined["ward_name"].where(joined["ward_id"].notna(), pd.NA).to_numpy()
    zone = joined["zone"].copy()
    zone = zone.where(joined["ward_id"].notna(), "outside")
    out["zone"] = zone.to_numpy()

    n_out = int((out["zone"] == "outside").sum())
    n_pos = int(out["label"].sum())
    print(f"total nodes: {len(out)}")
    print(f"positives: {n_pos}  positive rate: {n_pos / len(out):.6f}")
    print(f"nodes outside every ward: {n_out}")
    print("nodes per zone:")
    print(out.groupby("zone").size().to_string())
    print("positives per zone:")
    print(out.groupby("zone")["label"].sum().to_string())

    dest = PROCESSED / "nodes_labelled.csv"
    out.to_csv(dest, index=False)
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
