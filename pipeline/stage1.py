"""Stage 1 (where): which places look like the official BBMP flood points?

Positives are the flood points; the background is random locations inside the BBMP boundary. Background
points are unlabelled, not confirmed safe, so average precision is reported next to AUC. Validation holds
out one BBMP zone at a time: random splits leak neighbours and inflate the score.

This is the baseline with terrain features only. The GraphSAGE model on the combined graph and the
drain / built-up features are the next additions and must be scored on the same zone folds.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry import Point
from shapely.prepared import prep
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config
from pipeline import labels
from pipeline.hotspots import focal_layers

N_BACKGROUND = 4000
MIN_DIST_M = 300  # background points stay this far from any flood point


def _raster(name):
    with rasterio.open(config.PROCESSED_DIR / f"{name}.tif") as src:
        return src.read(1)


def background(city, flood_xy, rng):
    inside, tree = prep(city), cKDTree(flood_xy)
    minx, miny, maxx, maxy = city.bounds
    pts = []
    while len(pts) < N_BACKGROUND:
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if inside.contains(Point(x, y)) and tree.query([x, y])[0] > MIN_DIST_M:
            pts.append((x, y))
    return np.array(pts)


def dataset():
    """X (terrain features), y (1 = flood point), zone of every sample."""
    wards = labels.wards().to_crs(config.CRS_METRIC)
    pts = labels.flood_points()
    flood_xy = np.c_[pts.geometry.x, pts.geometry.y]
    bg = background(wards.union_all(), flood_xy, np.random.default_rng(config.RANDOM_SEED))
    xy = np.r_[flood_xy, bg]
    y = np.r_[np.ones(len(flood_xy)), np.zeros(len(bg))]

    focal, tf = focal_layers()
    layers = dict(focal, elev=_raster("dem_utm"), slope=_raster("slope_deg"))
    layers["dist_stream_m"] = ndimage.distance_transform_edt(_raster("streams") == 0) * config.CELL_SIZE
    rows, cols = rasterio.transform.rowcol(tf, xy[:, 0], xy[:, 1])
    X = pd.DataFrame({k: v[np.asarray(rows), np.asarray(cols)] for k, v in layers.items()})
    X["log_upstream"] = np.log10(X.pop("upstream_km2"))

    joined = gpd.sjoin(gpd.GeoDataFrame(geometry=gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=config.CRS_METRIC),
                       wards[["zone", "geometry"]], predicate="within", how="left")
    zone = joined[~joined.index.duplicated()].zone.to_numpy()
    ok = pd.notna(zone)  # a few points sit exactly on the boundary
    return X[ok].reset_index(drop=True), y[ok], zone[ok]


def models():
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "random_forest": RandomForestClassifier(400, min_samples_leaf=5, class_weight="balanced", n_jobs=-1,
                                                random_state=0),
        "grad_boost": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300,
                                                     class_weight="balanced", random_state=0),
    }


def run():
    X, y, zone = dataset()
    rows, by_zone = [], []
    for name, model in models().items():
        pooled = np.zeros(len(y))
        aucs = []
        for z in sorted(set(zone)):
            te = zone == z
            model.fit(X[~te], y[~te])
            pooled[te] = model.predict_proba(X[te])[:, 1]
            aucs.append(roc_auc_score(y[te], pooled[te]))
            by_zone.append({"model": name, "zone": z, "flood_points": int(y[te].sum()), "auc": aucs[-1]})
        top20 = np.quantile(pooled[y == 0], 0.8)
        rows.append({"model": name, "mean_zone_auc": np.mean(aucs), "min_zone_auc": min(aucs),
                     "max_zone_auc": max(aucs), "pooled_auc": roc_auc_score(y, pooled),
                     "avg_precision": average_precision_score(y, pooled), "base_rate": y.mean(),
                     "flood_points_in_top20pct_area": float((pooled[y == 1] > top20).mean())})
    summary, by_zone = pd.DataFrame(rows).round(3), pd.DataFrame(by_zone).round(3)
    config.OUT_DIR.mkdir(exist_ok=True)
    summary.to_csv(config.OUT_DIR / "stage1_metrics.csv", index=False)
    by_zone.to_csv(config.OUT_DIR / "stage1_by_zone.csv", index=False)
    return summary, by_zone, int(y.sum()), int((y == 0).sum())
