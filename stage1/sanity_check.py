#!/usr/bin/env python3
"""Sanity-check labels against flood points and write a map."""
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CRS_METRIC,
    CRS_WGS84,
    PROCESSED,
    TERRAIN_FEATURES,
    ensure_dirs,
    load_wards,
)

LABEL_RADIUS_M = 150.0
STAGE1 = Path(__file__).resolve().parent
RNG = np.random.default_rng(0)


def main():
    ensure_dirs()
    print("STEP 4  sanity checks")
    nodes = pd.read_csv(PROCESSED / "nodes_labelled.csv")
    flood = pd.read_csv(PROCESSED / "flood_points.csv")
    transformer = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    nx_, ny_ = transformer.transform(nodes["lon"].to_numpy(), nodes["lat"].to_numpy())
    fx, fy = transformer.transform(flood["lon"].to_numpy(), flood["lat"].to_numpy())
    node_xy = np.c_[nx_, ny_]
    flood_xy = np.c_[fx, fy]

    tree = cKDTree(node_xy)
    dist, _ = tree.query(flood_xy, k=1)
    none_mask = dist > LABEL_RADIUS_M
    n_none = int(none_mask.sum())
    print(f"flood points with no node within {LABEL_RADIUS_M:.0f} m: {n_none} / {len(flood)}")
    if n_none:
        miss = flood.loc[none_mask, ["name", "layer", "zone", "lat", "lon"]]
        print(miss.to_string(index=False))

    neighbors = tree.query_ball_point(flood_xy, r=LABEL_RADIUS_M)
    counts = np.array([len(ix) for ix in neighbors], dtype=int)
    print(
        "positive nodes per flood point: "
        f"min={counts.min()} median={np.median(counts):.1f} max={counts.max()} mean={counts.mean():.2f}"
    )

    print("NaN / inf in candidate terrain features:")
    for col in TERRAIN_FEATURES:
        if col not in nodes.columns:
            print(f"  STOP missing column {col}")
            raise SystemExit(f"missing feature {col}")
        n_nan = int(nodes[col].isna().sum())
        n_inf = int(np.isinf(pd.to_numeric(nodes[col], errors="coerce")).sum())
        print(f"  {col}: NaN={n_nan} inf={n_inf}")

    stats = (
        nodes.groupby("zone")
        .agg(n_nodes=("label", "size"), n_positive=("label", "sum"))
        .reset_index()
    )
    stats["positive_rate"] = stats["n_positive"] / stats["n_nodes"]
    stats_path = STAGE1 / "label_stats.csv"
    stats.to_csv(stats_path, index=False)
    print(f"wrote {stats_path}")
    print(stats.to_string(index=False))

    wards = load_wards().to_crs(CRS_WGS84)
    pos = nodes[nodes["label"] == 1]
    unlab = nodes[nodes["label"] == 0]
    if len(unlab) > 50_000:
        unlab = unlab.sample(50_000, random_state=0)
        print(f"downsampled unlabelled nodes to {len(unlab)} for the map")

    fig, ax = plt.subplots(figsize=(10, 10))
    wards.boundary.plot(ax=ax, linewidth=0.3, color="0.4", zorder=1)
    ax.scatter(unlab["lon"], unlab["lat"], s=0.2, c="0.75", linewidths=0, zorder=2, label="unlabelled nodes")
    ax.scatter(pos["lon"], pos["lat"], s=2.0, c="red", linewidths=0, zorder=3, label="positive nodes")
    ax.scatter(flood["lon"], flood["lat"], s=8, c="black", linewidths=0, zorder=4, label="flood points")
    ax.set_xlabel("lon")
    ax.set_ylabel("lat")
    ax.set_title("Stage 1 labels: nodes within 150 m of official BBMP flood points")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(markerscale=4, loc="upper right")
    fig.tight_layout()
    map_path = STAGE1 / "labels_map.png"
    fig.savefig(map_path, dpi=150)
    plt.close(fig)
    print(f"wrote {map_path}")


if __name__ == "__main__":
    main()
