"""Flood-aware routing on the OSM arterial road graph (OSMnx + NetworkX, offline, no API key).

Red hotspots become no-go zones: every road segment touching one is removed. Amber hotspots
become slow zones: travel time on those segments is multiplied by AMBER_PENALTY, so the route
avoids them when a reasonable detour exists. Zone radius defaults to RED_RADIUS_M / AMBER_RADIUS_M
and can be replaced per hotspot by the standing-water extent measured on the field visit.
"""
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform as shp_transform

import config
from pipeline import osm

RED_RADIUS_M = 300
AMBER_RADIUS_M = 200
AMBER_PENALTY = 4.0

# Preset places for the demo (lat, lon)
PLACES = {
    "RV College of Engineering": (12.9237, 77.4987),
    "Koramangala (Forum)": (12.9346, 77.6115),
    "HSR Layout": (12.9116, 77.6474),
    "Marathahalli": (12.9592, 77.6974),
    "Whitefield (ITPL)": (12.9868, 77.7370),
    "Electronic City": (12.8452, 77.6602),
    "MG Road metro": (12.9755, 77.6066),
    "Majestic (KSR station)": (12.9781, 77.5697),
    "Jayanagar 4th Block": (12.9250, 77.5838),
    "Indiranagar 100 ft Rd": (12.9784, 77.6408),
    "Hebbal": (13.0450, 77.5900),
    "Yelahanka": (13.1007, 77.5963),
    "Manyata Tech Park": (13.0475, 77.6206),
}

_to_utm = Transformer.from_crs("EPSG:4326", config.CRS_METRIC, always_xy=True).transform


class Router:
    def __init__(self):
        self.g = osm.roads()
        nodes = ox.graph_to_gdfs(self.g, edges=False)
        self.node_ids = nodes.index.to_numpy()
        self.node_lonlat = nodes[["x", "y"]].to_numpy()
        edges = ox.graph_to_gdfs(self.g, nodes=False)
        self.edges = edges[["geometry", "travel_time", "length"]].to_crs(config.CRS_METRIC)

    def nearest_node(self, lat, lon):
        dx = (self.node_lonlat[:, 0] - lon) * np.cos(np.radians(lat))
        dy = self.node_lonlat[:, 1] - lat
        return self.node_ids[np.argmin(dx * dx + dy * dy)]

    def zones(self, assessed):
        """Circular flood zones (UTM) around red and amber hotspots."""
        rows = []
        for h in assessed.itertuples():
            if h.status not in ("red", "amber"):
                continue
            r = RED_RADIUS_M if h.status == "red" else AMBER_RADIUS_M
            x, y = _to_utm(h.lon, h.lat)
            rows.append({"id": h.id, "name": h.name, "status": h.status, "geometry": Point(x, y).buffer(r)})
        return gpd.GeoDataFrame(rows, geometry="geometry", crs=config.CRS_METRIC) if rows else None

    def _affected(self, zones):
        if zones is None:
            return set(), set()
        hit = gpd.sjoin(self.edges, zones[["geometry", "status"]], predicate="intersects")
        blocked = set(hit[hit.status == "red"].index)
        slow = set(hit[hit.status == "amber"].index) - blocked
        return blocked, slow

    def _path(self, s, t, blocked=frozenset(), slow=frozenset()):
        def weight(u, v, data):
            best = None
            for k, d in data.items():
                if (u, v, k) in blocked:
                    continue
                w = d["travel_time"] * (AMBER_PENALTY if (u, v, k) in slow else 1.0)
                best = w if best is None or w < best else best
            return best  # None hides the edge from Dijkstra

        try:
            return nx.shortest_path(self.g, s, t, weight=weight)
        except nx.NetworkXNoPath:
            return None

    def _describe(self, path, zones):
        coords, length, time = [], 0.0, 0.0
        for u, v in zip(path[:-1], path[1:]):
            d = min(self.g[u][v].values(), key=lambda e: e["travel_time"])
            length += d["length"]
            time += d["travel_time"]
            seg = list(d["geometry"].coords) if "geometry" in d else [
                (self.g.nodes[u]["x"], self.g.nodes[u]["y"]), (self.g.nodes[v]["x"], self.g.nodes[v]["y"])]
            coords.extend(seg if not coords else seg[1:])
        crosses = []
        if zones is not None and len(coords) > 1:
            line = shp_transform(_to_utm, LineString(coords))
            crosses = [f"{z.name} ({z.status})" for z in zones.itertuples() if line.intersects(z.geometry)]
        return {"latlon": [(lat, lon) for lon, lat in coords], "km": length / 1000,
                "min": time / 60, "crosses": crosses}

    def route(self, origin, dest, assessed):
        """origin/dest: (lat, lon). Returns the usual fastest route and the flood-aware one."""
        s, t = self.nearest_node(*origin), self.nearest_node(*dest)
        zones = self.zones(assessed)
        usual = self._path(s, t)
        blocked, slow = self._affected(zones)
        safe = self._path(s, t, blocked, slow)
        return {
            "zones": zones,
            "usual": self._describe(usual, zones) if usual else None,
            "safe": self._describe(safe, zones) if safe else None,
            "blocked_segments": len(blocked),
        }
