"""Combine the OSM road graph and DEM-derived drainage graph for graph-learning workflows."""
import pickle

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.spatial import cKDTree

import config

CONNECTOR_RADIUS_M = 75.0
TERRAIN_LAYERS = {
    "dem_filled": "elev_m",
    "slope_deg": "slope_deg",
    "depression_depth": "depression_m",
    "upstream_km2": "upstream_km2",
    "twi": "twi",
    "hand": "hand_m",
    "tpi_300": "tpi300_m",
    "tpi_1000": "tpi1000_m",
}
GRAPH_PATH = config.PROCESSED_DIR / "gnn_graph.pkl"
NODES_PATH = config.PROCESSED_DIR / "gnn_graph_nodes.csv"
EDGES_PATH = config.PROCESSED_DIR / "gnn_graph_edges.csv"


def _node_id(layer, node):
    return f"{layer}:{node}"


def compose(roads, drains, connector_radius_m=CONNECTOR_RADIUS_M):
    """Copy both typed networks and connect road nodes near drainage nodes in metric space."""
    if roads.number_of_nodes() == 0 or drains.number_of_nodes() == 0:
        raise ValueError("Both input networks must contain at least one node")
    roads = ox.project_graph(roads, to_crs=config.CRS_METRIC)
    graph = nx.MultiDiGraph(crs=config.CRS_METRIC, connector_radius_m=connector_radius_m)

    road_nodes = {}
    road_items = list(roads.nodes(data=True))
    road_xy = np.array([(data["x"], data["y"]) for _, data in road_items])
    road_lon, road_lat = Transformer.from_crs(
        config.CRS_METRIC, "EPSG:4326", always_xy=True,
    ).transform(road_xy[:, 0], road_xy[:, 1])
    for (node, data), lon, lat in zip(road_items, road_lon, road_lat):
        node_id = _node_id("road", node)
        road_nodes[node] = node_id
        highway = data.get("highway", "")
        graph.add_node(
            node_id, node_type="road", candidate=True, x=float(data["x"]), y=float(data["y"]),
            lon=float(lon), lat=float(lat),
            road_class="|".join(highway) if isinstance(highway, list) else str(highway),
        )
    for u, v, key, data in roads.edges(keys=True, data=True):
        highway = data.get("highway", "")
        graph.add_edge(
            road_nodes[u], road_nodes[v], key=f"road:{key}", edge_type="road",
            length_m=float(data["length"]), travel_time_s=float(data["travel_time"]),
            road_class="|".join(highway) if isinstance(highway, list) else str(highway),
        )

    drain_nodes = {}
    for node, data in drains.nodes(data=True):
        node_id = _node_id("drain", node)
        drain_nodes[node] = node_id
        graph.add_node(
            node_id, node_type="drain", candidate=True, x=float(data["x"]), y=float(data["y"]),
            lon=float(data["lon"]), lat=float(data["lat"]),
            area_km2=float(data["area_km2"]), elev_m=float(data["elev"]),
        )
    for u, v, data in drains.edges(data=True):
        graph.add_edge(
            drain_nodes[u], drain_nodes[v], key=f"drain:{u}:{v}", edge_type="drain",
            length_m=float(data["length_m"]), area_km2=float(data["area_km2"]),
            drop_m=float(data["drop_m"]),
        )

    if not road_nodes or not drain_nodes:
        return graph

    road_ids = list(road_nodes.values())
    drain_ids = list(drain_nodes.values())
    drain_xy = np.array([(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in drain_ids])
    road_xy = np.array([(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in road_ids])
    distances, indices = cKDTree(drain_xy).query(road_xy, distance_upper_bound=connector_radius_m)
    for connector_index, (road_id, distance, index) in enumerate(zip(road_ids, distances, indices)):
        if not np.isfinite(distance):
            continue
        drain_id = drain_ids[index]
        connector = f"connector:{connector_index}"
        for u, v in ((road_id, drain_id), (drain_id, road_id)):
            graph.add_edge(
                u, v, key=connector, edge_type="road_drain", length_m=float(distance),
                connection_distance_m=float(distance),
            )
    return graph


def add_terrain_features(graph):
    nodes = list(graph.nodes)
    coords = [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in nodes]
    for layer, feature in TERRAIN_LAYERS.items():
        with rasterio.open(config.PROCESSED_DIR / f"{layer}.tif") as src:
            for node, value in zip(nodes, src.sample(coords, masked=True)):
                graph.nodes[node][feature] = float(value) if not np.ma.is_masked(value) else np.nan
    return graph


def _node_table(graph):
    rows = []
    for node, data in graph.nodes(data=True):
        rows.append({
            "node_id": node, "node_type": data["node_type"], "candidate": data["candidate"],
            "x": data["x"], "y": data["y"],
            "lon": data["lon"], "lat": data["lat"], "road_class": data.get("road_class", ""),
            "area_km2": data.get("area_km2", np.nan), "elev_m": data.get("elev_m", np.nan),
            **{feature: data.get(feature, np.nan) for feature in TERRAIN_LAYERS.values()},
        })
    return pd.DataFrame(rows)


def _edge_table(graph):
    rows = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        rows.append({
            "source": u, "target": v, "edge_key": key, "edge_type": data["edge_type"],
            "length_m": data.get("length_m", np.nan),
            "travel_time_s": data.get("travel_time_s", np.nan),
            "area_km2": data.get("area_km2", np.nan),
            "drop_m": data.get("drop_m", np.nan),
            "connection_distance_m": data.get("connection_distance_m", np.nan),
            "road_class": data.get("road_class", ""),
        })
    return pd.DataFrame(rows)


def export(graph):
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PATH, "wb") as stream:
        pickle.dump(graph, stream)
    _node_table(graph).to_csv(NODES_PATH, index=False)
    _edge_table(graph).to_csv(EDGES_PATH, index=False)
    return graph


def build(roads, drains, connector_radius_m=CONNECTOR_RADIUS_M):
    graph = compose(roads, drains, connector_radius_m)
    add_terrain_features(graph)
    return export(graph)
