"""Methodology step 3: the drain network as a directed graph.

Bengaluru's mapped drains in OSM are fragmented, so the connectivity comes from the DEM: every cell
with more than STREAM_THRESHOLD_CELLS upstream is a drainage line, and D8 flow direction says where
it goes next. Cells are merged into segments between junctions (and split every MAX_SEGMENT_M).
OSM then annotates each segment: is there a mapped drain along it, does it run through a lake,
and which arterial roads cross it (each crossing is a culvert, the usual blockage point).

Each hotspot is attached as its own node: its drainage cell is traced downstream until it joins
the network, so every hotspot has a path to an outlet.
"""
import pickle

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import rasterio
from pyproj import Transformer
from shapely.geometry import LineString

import config
from pipeline import osm
from pipeline.hotspots import load_hotspots, snap_cell

GRAPH_PKL = config.PROCESSED_DIR / "drain_graph.pkl"
EDGES_GEOJSON = config.OUT_DIR / "drain_graph_edges.geojson"
MAX_SEGMENT_M = 1000
OSM_DRAIN_BUFFER_M = 40
MIN_LAKE_M2 = 10_000

# pysheds D8 codes -> (row offset, col offset)
OFFSETS = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}


def _read(name):
    with rasterio.open(config.PROCESSED_DIR / f"{name}.tif") as src:
        return src.read(1), src.transform


def downstream_index(fdir):
    """Flat index of the cell each cell drains into, -1 where water leaves the grid."""
    h, w = fdir.shape
    dr = np.zeros(fdir.shape, dtype=np.int64)
    dc = np.zeros(fdir.shape, dtype=np.int64)
    for code, (a, b) in OFFSETS.items():
        m = fdir == code
        dr[m], dc[m] = a, b
    rows, cols = np.indices(fdir.shape)
    r2, c2 = rows + dr, cols + dc
    ok = np.isin(fdir, list(OFFSETS)) & (r2 >= 0) & (r2 < h) & (c2 >= 0) & (c2 < w)
    return np.where(ok, r2 * w + c2, -1).ravel()


def _segments(mask, ds, key):
    """Walk downstream from every key cell to the next key cell. Returns [(start, end, cells)]."""
    key = set(key)
    queue, segs = list(key), []
    max_cells = int(MAX_SEGMENT_M / config.CELL_SIZE)
    while queue:
        k = queue.pop()
        if ds[k] < 0:
            continue
        cells, cur = [k], ds[k]
        while cur not in key and len(cells) < max_cells:
            cells.append(cur)
            cur = ds[cur]
        if cur not in key:  # long run: split here
            key.add(cur)
            queue.append(cur)
        segs.append((k, cur, cells + [cur]))
    return segs, key


def build():
    fdir, tf = _read("flowdir")
    acc, _ = _read("flow_acc")
    elev, _ = _read("dem_filled")
    h, w = fdir.shape
    ds = downstream_index(fdir)
    acc_f, elev_f = acc.ravel(), elev.ravel()
    mask = acc_f > config.STREAM_THRESHOLD_CELLS

    # Attach hotspots: trace each one's drainage cell down until it meets the network.
    hot = load_hotspots()
    hot_cell = {}
    for hs in hot.itertuples():
        r, c = snap_cell(acc, tf, hs.x, hs.y)
        cur = r * w + c
        hot_cell[hs.id] = cur
        while cur >= 0 and not mask[cur]:
            mask[cur] = True
            cur = ds[cur]

    cells = np.flatnonzero(mask)
    targets = ds[cells]
    indeg = np.bincount(targets[targets >= 0], minlength=h * w)
    key = cells[(indeg[cells] != 1) | (ds[cells] < 0)]
    segs, key = _segments(mask, ds, list(key) + list(hot_cell.values()))

    to_ll = Transformer.from_crs(config.CRS_METRIC, "EPSG:4326", always_xy=True)

    def xy(idx):
        r, c = np.divmod(np.asarray(idx), w)
        xs, ys = rasterio.transform.xy(tf, r, c)
        return np.asarray(xs), np.asarray(ys)

    g = nx.DiGraph(crs=config.CRS_METRIC)
    key = np.fromiter(key, dtype=np.int64)
    kx, ky = xy(key)
    klon, klat = to_ll.transform(kx, ky)
    for i, k in enumerate(key):
        g.add_node(int(k), x=float(kx[i]), y=float(ky[i]), lon=float(klon[i]), lat=float(klat[i]),
                   area_km2=float((acc_f[k] + 1) * config.CELL_SIZE ** 2 / 1e6), elev=float(elev_f[k]))
    for hid, k in hot_cell.items():
        g.nodes[int(k)]["hotspot"] = hid

    rows = []
    for u, v, path in segs:
        px, py = xy(path)
        line = LineString(np.column_stack([px, py]))
        area = (acc_f[path[-2]] + 1) * config.CELL_SIZE ** 2 / 1e6
        g.add_edge(int(u), int(v), length_m=float(line.length), area_km2=float(area),
                   drop_m=float(elev_f[u] - elev_f[v]))
        rows.append({"u": int(u), "v": int(v), "area_km2": area, "geometry": line})
    edges = gpd.GeoDataFrame(rows, crs=config.CRS_METRIC)
    _annotate(g, edges)
    print(f"  drain graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} segments, "
          f"{sum(1 for *_, d in g.edges(data=True) if d['culverts'])} with road crossings, "
          f"{sum(1 for *_, d in g.edges(data=True) if d['in_lake'])} through lakes")

    with open(GRAPH_PKL, "wb") as f:
        pickle.dump(g, f)
    _export(g, edges)
    return g


def _annotate(g, edges):
    ww = osm.waterways().to_crs(config.CRS_METRIC)
    drains = ww.buffer(OSM_DRAIN_BUFFER_M).union_all()
    edges["on_osm_drain"] = edges.geometry.intersection(drains).length / edges.length.clip(lower=1)

    lakes = osm.waterbodies().to_crs(config.CRS_METRIC)
    lakes = lakes[lakes.area >= MIN_LAKE_M2]
    mid = edges.copy()
    mid["geometry"] = edges.geometry.interpolate(0.5, normalized=True)
    hit = gpd.sjoin(mid, lakes[["geometry", "name"]], predicate="within", how="left")
    hit = hit[~hit.index.duplicated()]
    edges["lake"] = hit["name"].where(hit["index_right"].notna())
    edges["in_lake"] = hit["index_right"].notna()

    roads = ox.graph_to_gdfs(osm.roads(), nodes=False).reset_index().to_crs(config.CRS_METRIC)
    roads["road"] = roads["name"].apply(lambda n: n[0] if isinstance(n, list) else n).fillna(
        roads["highway"].astype(str))
    x = gpd.sjoin(edges[["geometry"]], roads[["geometry", "road"]], predicate="intersects")
    crossings = x.groupby(level=0)["road"].apply(lambda s: sorted(set(s)))
    edges["culverts"] = crossings.reindex(edges.index).apply(lambda v: v if isinstance(v, list) else [])

    for r in edges.itertuples():
        d = g.edges[r.u, r.v]
        d["on_osm_drain"] = round(float(r.on_osm_drain), 2)
        d["in_lake"] = bool(r.in_lake)
        d["lake"] = r.lake if isinstance(r.lake, str) else None
        d["culverts"] = r.culverts


def _export(g, edges):
    """GeoJSON of the main channels (>= 1 km2) plus every segment on a hotspot's path, for the map."""
    keep = edges["area_km2"] >= 1.0
    on_path = set()
    for n, d in g.nodes(data=True):
        if "hotspot" in d:
            for u, v in nx.dfs_edges(g, n):
                on_path.add((u, v))
                if g.edges[u, v]["area_km2"] > 50:
                    break
    keep |= np.array([(u, v) in on_path for u, v in zip(edges.u, edges.v)])
    out = edges[keep].copy()
    out["culverts"] = out["culverts"].apply(", ".join)
    out["geometry"] = out.simplify(10)
    out.to_crs("EPSG:4326").to_file(EDGES_GEOJSON, driver="GeoJSON")


def load():
    with open(GRAPH_PKL, "rb") as f:
        return pickle.load(f)


def hotspot_nodes(g):
    return {d["hotspot"]: n for n, d in g.nodes(data=True) if "hotspot" in d}
