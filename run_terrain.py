"""Runs the terrain layer end to end: DEM -> hydrology rasters -> hotspot features -> maps.

    .venv\\Scripts\\python run_terrain.py
"""
import config
from pipeline import dem, hotspots, hydrology, maps


def main():
    print("[1/4] DEM")
    dem_path = dem.build_dem()
    print("[2/4] terrain layers")
    grid, fdir, acc = hydrology.build_terrain(dem_path)
    print("[3/4] hotspot features, catchments, terrain-only baseline")
    hot, ctrl, summary, catch = hotspots.build_hotspot_table(grid, fdir, acc)
    print(summary.to_string(index=False))
    cols = ["name", "elev_m", "upstream_km2", "hand_m", "tpi300_m", "catchment_km2", "terrain_score_pctl"]
    print(hot[cols].round(2).to_string(index=False))
    print("[4/4] maps")
    maps.static_figure(hot)
    maps.web_map(hot, catch)
    print(f"done -> {config.OUT_DIR}")


if __name__ == "__main__":
    main()
