"""OpenStreetMap layers via OSMnx (Overpass API, free, no key). Cached under data/raw/osm."""
import geopandas as gpd
import osmnx as ox
import truststore

import config

# Use the Windows/macOS certificate store: antivirus HTTPS scanning adds a root that certifi lacks.
truststore.inject_into_ssl()

OSM_DIR = config.RAW_DIR / "osm"
ROADS = OSM_DIR / "roads_major.graphml"
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
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    g = ox.graph_from_bbox(_bbox(), network_type="drive", custom_filter=ROAD_FILTER)
    g = ox.add_edge_speeds(g)
    g = ox.add_edge_travel_times(g)
    ox.save_graphml(g, ROADS)
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
