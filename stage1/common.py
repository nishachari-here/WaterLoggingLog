"""Shared paths and zone-name cleaning for Stage 1 data prep."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OPENCITY = ROOT / "data" / "opencity"
GRAPH_DIR = ROOT / "data" / "graph"
PROCESSED = ROOT / "data" / "processed"
EXPORT = ROOT / "export"

CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:32643"

NODES_GRAPH = GRAPH_DIR / "gnn_graph_nodes.csv"
EDGES_GRAPH = GRAPH_DIR / "gnn_graph_edges.csv"

FLOOD_KMLS = {
    "flood_vulnerable": OPENCITY / "flood_vulnerable.kml",
    "flood_prone": OPENCITY / "flood_prone.kml",
    "low_lying": OPENCITY / "low_lying.kml",
}

WARDS_2015 = OPENCITY / "wards_2015.kml"
SWD_PRIMARY = OPENCITY / "swd_primary.kml"
SWD_SECONDARY = OPENCITY / "swd_secondary.kml"

# Eight terrain features written by pipeline/combined_graph.py (TERRAIN_LAYERS values).
TERRAIN_FEATURES = [
    "elev_m",
    "slope_deg",
    "depression_m",
    "upstream_km2",
    "twi",
    "hand_m",
    "tpi300_m",
    "tpi1000_m",
]

DRAIN_FEATURES = [
    "dist_to_official_drain_m",
    "drain_density_500m",
]

# Observed spellings -> the 8 BBMP zone names requested for hold-out.
# Lowercased, whitespace-normalised keys. See stage1/INSPECT.md.
ZONE_NAME_MAP = {
    "bommanahalli": "Bommanahalli",
    "dasarahalli": "Dasarahalli",
    "east": "East",
    "mahadevapura": "Mahadevapura",
    "rajarajeshwari nagar": "Rajarajeshwari Nagar",
    "rajarajeswari nagar": "Rajarajeshwari Nagar",
    "rr nagar": "Rajarajeshwari Nagar",
    "south": "South",
    "west": "West",
    "yelahanka": "Yelahanka",
}

EXPECTED_ZONES = [
    "Bommanahalli",
    "Dasarahalli",
    "East",
    "Mahadevapura",
    "Rajarajeshwari Nagar",
    "South",
    "West",
    "Yelahanka",
]


def norm_key(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\xa0", " ").replace("\u00a0", " ")
    return " ".join(text.split()).strip().lower()


def canonical_zone(value):
    key = norm_key(value)
    if not key:
        return pd.NA
    if key not in ZONE_NAME_MAP:
        raise ValueError(f"Unmapped zone name {value!r} (key={key!r}). Stop rather than guess.")
    return ZONE_NAME_MAP[key]


def ensure_dirs():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    EXPORT.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)


def load_wards():
    """198-ward 2015 map with canonical 8-zone names. See INSPECT.md."""
    import geopandas as gpd

    wards = gpd.read_file(WARDS_2015)
    if wards.crs is None:
        wards = wards.set_crs(CRS_WGS84)
    else:
        wards = wards.to_crs(CRS_WGS84)
    if "Ward_Name" not in wards.columns or "Zone" not in wards.columns or "Name" not in wards.columns:
        raise ValueError(f"Unexpected ward columns: {list(wards.columns)}")
    ward_id = (
        wards["Name"].astype(str).str.replace("\xa0", " ", regex=False)
        .str.extract(r"(\d+)", expand=False)
    )
    if ward_id.isna().any():
        raise ValueError("Could not parse ward_id from Name")
    wards = wards.copy()
    wards["ward_id"] = ward_id.astype(int)
    wards["ward_name"] = wards["Ward_Name"].astype(str).str.replace("\xa0", " ").str.strip()
    wards["zone"] = wards["Zone"].map(canonical_zone)
    if wards["zone"].isna().any():
        raise ValueError("Unmapped zone in ward file")
    if wards["ward_id"].nunique() != len(wards):
        raise ValueError("Duplicate ward_id")
    if sorted(wards["zone"].unique()) != EXPECTED_ZONES:
        raise ValueError(f"Zones are {sorted(wards['zone'].unique())}, expected {EXPECTED_ZONES}")
    return wards[["ward_id", "ward_name", "zone", "geometry"]]
