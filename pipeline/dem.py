"""Step 1: download the DEM tiles, mosaic them and cut a metric (UTM) grid over the study area."""
import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

import config


def download_tiles():
    config.DEM_RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in config.DEM_TILES:
        url = config.DEM_URL.format(t=t)
        path = config.DEM_RAW_DIR / url.rsplit("/", 1)[1]
        if not path.exists():
            print(f"  downloading {path.name}")
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            path.write_bytes(r.content)
        paths.append(path)
    return paths


def utm_grid():
    """Target grid: the UTM rectangle that encloses the lon/lat bbox, snapped to the cell size."""
    to_utm = Transformer.from_crs("EPSG:4326", config.CRS_METRIC, always_xy=True)
    b = config.BBOX
    xs, ys = to_utm.transform([b["west"], b["east"], b["west"], b["east"]],
                              [b["south"], b["south"], b["north"], b["north"]])
    c = config.CELL_SIZE
    left, right = np.floor(min(xs) / c) * c, np.ceil(max(xs) / c) * c
    bottom, top = np.floor(min(ys) / c) * c, np.ceil(max(ys) / c) * c
    width, height = int((right - left) / c), int((top - bottom) / c)
    return from_origin(left, top, c, c), width, height


def build_dem():
    """Returns the path of the study-area DEM in UTM (float32, metres)."""
    out = config.PROCESSED_DIR / "dem_utm.tif"
    if out.exists():
        return out
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    srcs = [rasterio.open(p) for p in download_tiles()]
    mosaic, mosaic_tf = merge(srcs)
    src_crs = srcs[0].crs
    for s in srcs:
        s.close()

    transform, width, height = utm_grid()
    dem = np.full((height, width), np.nan, dtype="float32")
    reproject(mosaic[0].astype("float32"), dem,
              src_transform=mosaic_tf, src_crs=src_crs,
              dst_transform=transform, dst_crs=config.CRS_METRIC,
              resampling=Resampling.bilinear, dst_nodata=np.nan)
    if np.isnan(dem).any():
        raise RuntimeError("DEM has gaps inside the study area; check BBOX against DEM_TILES")

    profile = dict(driver="GTiff", height=height, width=width, count=1, dtype="float32",
                   crs=config.CRS_METRIC, transform=transform, nodata=-9999.0, compress="deflate")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(dem, 1)
    print(f"  DEM {width}x{height} cells, elevation {dem.min():.0f}-{dem.max():.0f} m")
    return out
