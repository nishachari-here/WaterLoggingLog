"""Project-wide settings: study area, projection, paths and terrain thresholds."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Study area (lon/lat). Covers BBMP limits plus a margin so that catchments
# draining into the city are not cut off at the edge.
BBOX = {"west": 77.42, "south": 12.78, "east": 77.82, "north": 13.18}

# UTM zone 43N gives metric cells, so slopes and areas come out in metres.
CRS_METRIC = "EPSG:32643"
CELL_SIZE = 30.0  # metres, matches Copernicus GLO-30

# Copernicus GLO-30 DSM tiles on the public AWS bucket (no login needed).
DEM_TILES = ["N12_00_E077_00", "N13_00_E077_00"]
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_{t}_DEM/Copernicus_DSM_COG_10_{t}_DEM.tif")

# Paths
RAW_DIR = ROOT / "data" / "raw"
DEM_RAW_DIR = RAW_DIR / "dem"
PROCESSED_DIR = ROOT / "data" / "processed"
HOTSPOTS_CSV = ROOT / "data" / "hotspots.csv"
OUT_DIR = ROOT / "outputs"

# Terrain thresholds
STREAM_THRESHOLD_CELLS = 500   # ~0.45 km2 upstream area -> treated as a drainage line (for HAND)
SAMPLE_RADIUS_M = 150          # hotspot coords and a 30 m DEM are both fuzzy, so sample a small disc
TPI_RADII_M = (300, 1000)      # local and neighbourhood "how low is this spot" windows
N_CONTROL_POINTS = 600         # random non-hotspot locations for the terrain-only baseline
CONTROL_MIN_DIST_M = 1000      # keep controls this far from any listed hotspot
RANDOM_SEED = 42
