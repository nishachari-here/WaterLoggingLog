"""Shared paths for Stage 2 preprocessing.

Reads Stage 1 outputs and the cached rain file. Does not regenerate them
and does not call the rain API.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
STAGE2_OUT = PROCESSED / "stage2"
OPENCITY = ROOT / "data" / "opencity"

WARDS_CSV = PROCESSED / "wards.csv"
WARDS_GEOJSON = PROCESSED / "wards.geojson"
NODES_V2 = PROCESSED / "nodes_labelled_v2.csv"
FLOOD_POINTS = PROCESSED / "flood_points.csv"
RAIN_HOURLY = ROOT / "data" / "rain" / "rain_hourly.csv"

# Same 0.1-degree cell id as pipeline/rain_history.cell_of.
def cell_of(lat, lon) -> str:
    return f"{round(float(lat), 1)}_{round(float(lon), 1)}"


TERRAIN_MEAN_COLS = [
    "elev_m",
    "slope_deg",
    "depression_m",
    "upstream_km2",
    "twi",
    "hand_m",
    "tpi300_m",
    "tpi1000_m",
    "dist_to_official_drain_m",
    "drain_density_500m",
]


def ensure_out():
    STAGE2_OUT.mkdir(parents=True, exist_ok=True)
    return STAGE2_OUT
