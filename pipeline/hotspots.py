"""Step 3: terrain features at each hotspot, its upstream catchment, and the terrain-only baseline.

The terrain-only baseline is one of the two baselines in the methodology. It ranks every cell by
how "flood-prone the ground looks" and then checks whether the known hotspots rank higher than
random control locations. Features are taken over a SAMPLE_RADIUS_M disc because both the hotspot
coordinates and a 30 m DSM are fuzzy at street scale.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio import features
from scipy import ndimage
from scipy.stats import rankdata
from shapely.geometry import Point, shape

import config
from pipeline.hydrology import DIRMAP, _disc

# feature name -> (source layer, focal operation, +1 if "higher = more flood-prone" else -1)
FEATURES = {
    "upstream_km2": ("upstream_km2", "max", +1),
    "twi": ("twi", "max", +1),
    "depression_m": ("depression_depth", "max", +1),
    "hand_m": ("hand", "min", -1),
    "tpi300_m": ("tpi_300", "min", -1),
    "tpi1000_m": ("tpi_1000", "min", -1),
}


def read(name):
    with rasterio.open(config.PROCESSED_DIR / f"{name}.tif") as src:
        return src.read(1), src.transform


def focal_layers():
    k = _disc(config.SAMPLE_RADIUS_M / config.CELL_SIZE).astype(bool)
    out = {}
    for feat, (layer, op, _) in FEATURES.items():
        arr, transform = read(layer)
        f = ndimage.maximum_filter if op == "max" else ndimage.minimum_filter
        out[feat] = f(arr.astype("float32"), footprint=k, mode="nearest")
    return out, transform


def terrain_score(focal):
    """Mean percentile rank of all features, each oriented so that high = flood-prone. 0..100."""
    ranks = []
    for feat, (_, _, sign) in FEATURES.items():
        v = sign * focal[feat].ravel()
        ranks.append(rankdata(v) / v.size)
    return (100 * np.mean(ranks, axis=0)).reshape(focal["twi"].shape).astype("float32")


def load_hotspots():
    df = pd.read_csv(config.HOTSPOTS_CSV)
    to_utm = Transformer.from_crs("EPSG:4326", config.CRS_METRIC, always_xy=True)
    df["x"], df["y"] = to_utm.transform(df.lon.values, df.lat.values)
    return df


def control_points(transform, shape_, hot_xy, rng):
    """Random cells at least CONTROL_MIN_DIST_M from every hotspot and 2 km from the grid edge."""
    margin = int(2000 / config.CELL_SIZE)
    pts = []
    while len(pts) < config.N_CONTROL_POINTS:
        r = rng.integers(margin, shape_[0] - margin)
        c = rng.integers(margin, shape_[1] - margin)
        x, y = rasterio.transform.xy(transform, r, c)
        if np.min(np.hypot(hot_xy[:, 0] - x, hot_xy[:, 1] - y)) >= config.CONTROL_MIN_DIST_M:
            pts.append((f"ctrl_{len(pts):03d}", x, y))
    return pd.DataFrame(pts, columns=["id", "x", "y"])


def sample(df, layers, transform):
    rows, cols = rasterio.transform.rowcol(transform, df.x.values, df.y.values)
    rows, cols = np.asarray(rows), np.asarray(cols)
    out = df.copy()
    for name, arr in layers.items():
        out[name] = arr[rows, cols]
    return out


def auc(pos, neg):
    """Probability a random hotspot scores higher than a random control (Mann-Whitney AUC)."""
    allv = np.concatenate([pos, neg])
    r = rankdata(allv)[: len(pos)]
    return (r.sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def snap_cell(acc, transform, x, y):
    """Highest-accumulation cell within the sample radius: where the hotspot's water actually runs."""
    rad = int(config.SAMPLE_RADIUS_M / config.CELL_SIZE)
    r0, c0 = rasterio.transform.rowcol(transform, x, y)
    win = acc[r0 - rad:r0 + rad + 1, c0 - rad:c0 + rad + 1]
    dr, dc = np.unravel_index(np.argmax(win), win.shape)
    return r0 - rad + dr, c0 - rad + dc


def catchments(df, grid, fdir, acc):
    """Snap each hotspot to its drainage cell and delineate everything that drains to it.
    Area is the A in the rational method."""
    acc_np = np.asarray(acc)
    tf = grid.affine
    polys, records = [], []
    for h in df.itertuples():
        r, c = snap_cell(acc_np, tf, h.x, h.y)
        sx, sy = rasterio.transform.xy(tf, r, c)
        # Index form: coordinate snapping can land on the neighbouring cell and miss the channel.
        mask = np.asarray(grid.catchment(x=c, y=r, fdir=fdir, dirmap=DIRMAP, xytype="index"),
                          dtype="uint8")
        geoms = [shape(g) for g, v in features.shapes(mask, mask=mask.astype(bool), transform=tf) if v == 1]
        poly = max(geoms, key=lambda g: g.area) if geoms else Point(sx, sy).buffer(15)
        area_km2 = mask.sum() * config.CELL_SIZE ** 2 / 1e6
        polys.append(poly)
        records.append({"id": h.id, "name": h.name, "catchment_km2": round(area_km2, 3),
                        "snap_dist_m": round(float(np.hypot(sx - h.x, sy - h.y)), 1)})
    return gpd.GeoDataFrame(records, geometry=polys, crs=config.CRS_METRIC)


def build_hotspot_table(grid, fdir, acc):
    focal, transform = focal_layers()
    score = terrain_score(focal)
    with rasterio.open(config.PROCESSED_DIR / "dem_utm.tif") as src:
        profile = src.profile
    with rasterio.open(config.PROCESSED_DIR / "terrain_score.tif", "w",
                       **dict(profile, dtype="float32", nodata=None)) as dst:
        dst.write(score, 1)

    dem, _ = read("dem_utm")
    slope, _ = read("slope_deg")
    layers = dict(focal, terrain_score=score, elev_m=dem, slope_deg=slope)

    hot = load_hotspots()
    rng = np.random.default_rng(config.RANDOM_SEED)
    ctrl = control_points(transform, score.shape, hot[["x", "y"]].values, rng)
    hot_f, ctrl_f = sample(hot, layers, transform), sample(ctrl, layers, transform)

    # Where each hotspot sits among the random controls (100 = more flood-prone-looking than all).
    for feat in list(FEATURES) + ["terrain_score"]:
        sign = FEATURES[feat][2] if feat in FEATURES else +1
        c = sign * ctrl_f[feat].values
        hot_f[f"{feat}_pctl"] = [round(100 * np.mean(c < sign * v), 1) for v in hot_f[feat]]

    summary = pd.DataFrame([
        {"feature": feat,
         "auc_hotspot_vs_control": round(auc(s * hot_f[feat].values, s * ctrl_f[feat].values), 3),
         "hotspot_median": round(float(hot_f[feat].median()), 3),
         "control_median": round(float(ctrl_f[feat].median()), 3)}
        for feat, s in [(f, FEATURES[f][2]) for f in FEATURES] + [("terrain_score", +1)]
    ])

    catch = catchments(hot, grid, fdir, acc)
    hot_f = hot_f.merge(catch[["id", "catchment_km2", "snap_dist_m"]], on="id")

    config.OUT_DIR.mkdir(exist_ok=True)
    hot_f.drop(columns=["x", "y"]).round(3).to_csv(config.OUT_DIR / "hotspot_terrain_features.csv", index=False)
    ctrl_f.round(3).to_csv(config.PROCESSED_DIR / "control_points.csv", index=False)
    summary.to_csv(config.OUT_DIR / "terrain_baseline_summary.csv", index=False)
    catch.to_crs("EPSG:4326").to_file(config.OUT_DIR / "hotspot_catchments.geojson", driver="GeoJSON")
    return hot_f, ctrl_f, summary, catch
