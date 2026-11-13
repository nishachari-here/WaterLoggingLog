"""OpenStreetMap layers via OSMnx (Overpass API, free, no key). Cached under data/raw/osm."""
import geopandas as gpd
import osmnx as ox
import truststore

import config

# Use the Windows/macOS certificate store: antivirus HTTPS scanning adds a root that certifi lacks.
truststore.inject_into_ssl()

OSM_DIR = config.RAW_DIR / "osm"
ROADS = OSM_DIR / "roads_major.graphml"
ALL_ROADS = OSM_DIR / "roads_drive.graphml"
WATERWAYS = OSM_DIR / "waterways.gpkg"
WATERBODIES = OSM_DIR / "waterbodies.gpkg"

# Arterial roads only: a commuter's route is decided on these, and the city-wide graph stays small.
ROAD_FILTER = ('["highway"~"motorway|trunk|primary|secondary|tertiary|'
               'motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"]')


def _bbox():
    b = config.BBOX
    return (b["west"], b["south"], b["east"], b["north"])


def roads():
    """Directed drivable graph with length (m) and travel_time (s) on every edge."""
    if ROADS.exists():
        return ox.load_graphml(ROADS)

    gnn_pkl = config.ROOT / "data" / "graphs" / "gnn_graph.pkl"
    if gnn_pkl.exists():
        import pickle
        import networkx as nx
        from shapely.geometry import LineString

        with open(gnn_pkl, "rb") as f:
            full_g = pickle.load(f)

        major_classes = {"motorway", "trunk", "primary", "secondary", "tertiary"}
        rg = nx.MultiDiGraph(crs="EPSG:4326")

        for u, v, k, d in full_g.edges(keys=True, data=True):
            if d.get("edge_type") == "road":
                cls = str(d.get("road_class", ""))
                if any(m in cls for m in major_classes):
                    u_data = full_g.nodes[u]
                    v_data = full_g.nodes[v]
                    if u not in rg:
                        rg.add_node(u, x=float(u_data["lon"]), y=float(u_data["lat"]))
                    if v not in rg:
                        rg.add_node(v, x=float(v_data["lon"]), y=float(v_data["lat"]))
                    geom = LineString([(float(u_data["lon"]), float(u_data["lat"])),
                                       (float(v_data["lon"]), float(v_data["lat"]))])
                    length = float(d.get("length_m") or 50.0)
                    tt = float(d.get("travel_time_s") or (length / 11.1))
                    rg.add_edge(u, v, k, geometry=geom, length=length, travel_time=tt, highway=cls)

        return rg

    OSM_DIR.mkdir(parents=True, exist_ok=True)
    g = ox.graph_from_bbox(_bbox(), network_type="drive", custom_filter=ROAD_FILTER)
    g = ox.add_edge_speeds(g)
    g = ox.add_edge_travel_times(g)
    ox.save_graphml(g, ROADS)
    return g


def all_roads():
    """Full drivable OSM graph, including local streets, for graph-learning candidates."""
    if ALL_ROADS.exists():
        return ox.load_graphml(ALL_ROADS)
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    g = ox.graph_from_bbox(_bbox(), network_type="drive")
    g = ox.add_edge_speeds(g)
    g = ox.add_edge_travel_times(g)
    ox.save_graphml(g, ALL_ROADS)
    return g


def _features(path, tags, geom_types):
    if path.exists():
        return gpd.read_file(path)
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    gdf = ox.features_from_bbox(_bbox(), tags=tags).reset_index().rename(columns={"id": "osmid"})
    gdf = gdf[gdf.geom_type.isin(geom_types)]
    keep = [c for c in ["osmid", "name", "waterway", "natural", "water", "geometry"] if c in gdf.columns]
    gdf = gdf[keep].copy()
    gdf["osmid"] = gdf["osmid"].astype(str)
    gdf.to_file(path, driver="GPKG")
    return gdf


def waterways():
    return _features(WATERWAYS, {"waterway": ["drain", "canal", "stream", "river", "ditch"]},
                     ["LineString", "MultiLineString"])


def waterbodies():
    return _features(WATERBODIES, {"natural": "water"}, ["Polygon", "MultiPolygon"])


if __name__ == "__main__":
    g = roads()
    print(f"roads: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    print(f"waterways: {len(waterways())} lines")
    print(f"water bodies: {len(waterbodies())} polygons")
