"""Step 2: terrain layers from the DEM.

Layers (all on the same 30 m UTM grid):
  depression_depth  how deep water can pond before it spills (filled DEM - DEM)
  slope_deg         local slope
  flow_acc          number of upstream cells (D8, O'Callaghan & Mark 1984; Jenson & Domingue 1988)
  upstream_km2      flow_acc as area -> the "A" in Q = C*i*A
  twi               topographic wetness index ln(a / tan b): high = water tends to collect
  hand              height above nearest drainage (Nobre et al. 2011): low = floods easily
  tpi_300, tpi_1000 elevation minus mean elevation around it: negative = local low spot
  streams           1 where upstream area exceeds STREAM_THRESHOLD_CELLS
"""
import numpy as np
import rasterio
from pysheds.grid import Grid
from scipy import ndimage

import config

DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


def _disc(radius_cells):
    r = int(radius_cells)
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y <= r * r).astype("float32")


def tpi(dem, radius_m):
    k = _disc(radius_m / config.CELL_SIZE)
    mean = ndimage.convolve(dem, k / k.sum(), mode="nearest")
    return dem - mean


def slope_degrees(dem):
    gy, gx = np.gradient(dem, config.CELL_SIZE)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def write(name, arr, profile):
    path = config.PROCESSED_DIR / f"{name}.tif"
    p = dict(profile, dtype=str(arr.dtype), nodata=None)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(arr, 1)
    return path


def build_terrain(dem_path):
    with rasterio.open(dem_path) as src:
        profile = src.profile
        dem_np = src.read(1)

    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))

    print("  filling pits and depressions")
    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)

    print("  flow direction and accumulation")
    fdir = grid.flowdir(inflated, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)
    streams = acc > config.STREAM_THRESHOLD_CELLS

    print("  height above nearest drainage")
    hand = np.asarray(grid.compute_hand(fdir, inflated, streams, dirmap=DIRMAP), dtype="float32")
    # ~1.5% of cells (edges, closed basins) never reach a drainage line: treat them as high ground.
    hand = np.where(np.isfinite(hand), hand, np.nanmax(hand))

    acc_np = np.asarray(acc, dtype="float32")
    slope = slope_degrees(dem_np)
    # Specific catchment area (m) over tan(slope); floor the slope so flat cells don't blow up.
    sca = (acc_np + 1.0) * config.CELL_SIZE
    twi = np.log(sca / np.tan(np.radians(np.maximum(slope, 0.1))))

    layers = {
        "dem_filled": np.asarray(flooded, dtype="float32"),
        "depression_depth": (np.asarray(flooded) - dem_np).astype("float32"),
        "slope_deg": slope.astype("float32"),
        "flow_acc": acc_np,
        "upstream_km2": (acc_np + 1.0) * config.CELL_SIZE ** 2 / 1e6,
        "twi": twi.astype("float32"),
        "hand": hand,
        "streams": streams.astype("uint8"),
    }
    for r in config.TPI_RADII_M:
        layers[f"tpi_{r}"] = tpi(dem_np, r).astype("float32")
    layers["flowdir"] = np.asarray(fdir, dtype="int16")

    for name, arr in layers.items():
        write(name, arr, profile)
    print(f"  wrote {len(layers)} layers to {config.PROCESSED_DIR}")
    return grid, fdir, acc
