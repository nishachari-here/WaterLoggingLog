# Waterlogging Early-Warning for Bengaluru Flood Hotspots

EL Phase-I, SDG 9, RVCE. This repo holds the **terrain layer** (methodology step 2), the **drain graph**
with blockage what-ifs (step 3), a placeholder **risk model** (step 4 physics), and a **dashboard with
flood-aware rerouting**. See [docs/plan.md](docs/plan.md) for the overall plan and field-visit protocol.

## Run it

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run_terrain.py
.venv\Scripts\python run_network.py
.venv\Scripts\python run_gnn_graph.py
.venv\Scripts\python run_backtest.py
.venv\Scripts\python run_leadtime.py
.venv\Scripts\python server.py
```

`server.py` starts the **web dashboard** at http://localhost:8000. It's a FastAPI JSON API (`/api/meta`,
`/api/assess`, `/api/drains`) over the same pipeline, plus a hand-built Leaflet frontend in `web/`
(OpenStreetMap tiles, light and dark themes, phone layout). The older Streamlit version still works with
`.venv\Scripts\streamlit run app.py`.

`run_backtest.py` scores the methods on 2022–2025 hotspot-days against 24 news-documented flood days
(`data/events/flood_events.csv`). `run_leadtime.py` repeats the test on forecasts issued 0–3 days ahead
(2024–2025) and counts the alerts the dashboard would have raised. Results and caveats are in
[docs/backtest.md](docs/backtest.md).

`run_terrain.py` downloads two Copernicus GLO-30 tiles (~80 MB, public AWS bucket, no login) and takes about
a minute. `run_network.py` pulls OSM roads, drains and lakes through the Overpass API (a few minutes the first
time, then cached). All of it is free, with no API keys.
`run_gnn_graph.py` rebuilds the DEM drainage network without adding hand-listed hotspot nodes, downloads
the full drivable street graph on its first run, and writes a combined typed graph plus node/edge CSVs under
`data/processed/`. Road nodes within 75 m of drainage nodes get bidirectional spatial connector edges;
these indicate proximity, not verified culvert or hydraulic connections.

## Network layer and dashboard

| File | What it does |
|---|---|
| `pipeline/osm.py` | Arterial road graph for routing plus a full drivable graph for graph-learning candidates, 3k OSM waterways, 3.9k water bodies |
| `pipeline/drain_graph.py` | Directed drainage graph: DEM drainage lines merged into segments, each tagged with OSM drain overlap, lake, and the arterial roads that cross it (culverts). Nodes come from the DEM network, not the hotspot CSV. |
| `pipeline/combined_graph.py` | Namespaced road and drainage nodes, typed edges, proximity connectors and sampled DEM features; exports pickle and CSVs for ML preprocessing. |
| `pipeline/risk.py` | Rational-method runoff vs capacity per segment, giving a per-hotspot rain threshold, the bottleneck segment (min-cut on the flow tree), what-if blocking, and a "clear these first" ranking. Field log rows override the placeholder capacity. |
| `pipeline/routing.py` | Red hotspots are 300 m no-go zones and amber ones 200 m slow zones (×4 travel time). Dijkstra on OSMnx/NetworkX gives the usual route and the flood-aware route. |
| `pipeline/rain.py` | Open-Meteo hourly forecast per hotspot: peak for each of the next four 24 h windows |
| `app.py` | Streamlit dashboard. **Red alert / amber / green** for the next 24 h, plus **watch** when the forecast 1–3 days out reaches a hotspot's threshold (dashed orange ring, outlook column). Also: rain sliders (today and later) or live forecast, blockage slider, culvert picker, route picker, map, threshold and priority tables. |

**Placeholder capacities.** Until field data arrives, a segment draining 1 km² is assumed to cope with
50 mm/h, and capacity scales with A^0.85 (`I_REF`, `EXPONENT` in `risk.py`). This gives thresholds of
19–45 mm/h at 20% blockage. To replace them, copy `data/field/field_log_template.csv` to
`data/field/field_log.csv` and fill one row per measured drain. Set `local_catchment_km2` to the area that
reaches that roadside drain; if it's left blank, it defaults to the smaller of the DEM catchment and 0.5 km².

**Not modelled.** Water spreading along streets, pump stations in underpasses, and lake overflow. A road is
blocked by distance to a red hotspot, not by simulated flood extent.

## What it does

| Step | File | Output |
|---|---|---|
| 1. DEM | `pipeline/dem.py` | Mosaic, clip and reproject to a 30 m UTM 43N grid → `data/processed/dem_utm.tif` |
| 2. Terrain | `pipeline/hydrology.py` | Depression depth, slope, D8 flow direction and accumulation, upstream area, TWI, HAND, TPI (300 m, 1 km), drainage lines |
| 3. Hotspots | `pipeline/hotspots.py` | Features per hotspot, upstream catchment polygon, terrain-only baseline vs 600 random control points |
| 4. Maps | `pipeline/maps.py` | `outputs/terrain_overview.png`, `outputs/terrain_map.html` (Leaflet + OSM, no API key) |
| Field bridge | `pipeline/capacity.py` | Manning drain capacity, rational-method runoff, per-hotspot critical rain intensity |

Outputs in `outputs/`:
- `hotspot_terrain_features.csv`: one row per hotspot. `*_pctl` columns give the percentage of random control locations that look less flood-prone than the hotspot on that feature.
- `terrain_baseline_summary.csv`: AUC of each terrain feature at separating hotspots from controls.
- `hotspot_catchments.geojson`: area draining to each hotspot (the `A` in Q = C·i·A).

`run_gnn_graph.py` writes `data/processed/gnn_graph.pkl`, `gnn_graph_nodes.csv`, and
`gnn_graph_edges.csv`. These are a spatial graph and static node features, **not a training dataset**:
the repository does not yet contain complete time-indexed flood labels or graph-wide rainfall features
needed to train or validate a spatio-temporal GNN.

## First results (12 original hotspots, 600 controls)

The terrain-only score separates hotspots from random spots with **AUC 0.71**. The strongest single
features are depression depth (0.83) and local low-spot TPI-300 (0.74). Valley-floor hotspots score
93–100 (Silk Board, Madiwala, Koramangala, KR Circle, Manyata). **Underpasses do not show up** (HAL–Marathahalli 47,
Hebbal 50, Kadubeesanahalli 59), because a 30 m surface model cannot see a man-made dip under a road.
That gap is why we take field measurements, and it is the case for the full model over a terrain-only map.
These results describe the original 12 locations only. The terrain outputs have since been regenerated
for 18 listed locations; use `outputs/terrain_baseline_summary.csv` for that run's metrics. The six added
locations are approximate candidates, not field-verified positives. The original metrics are indicative,
not a result to report as final.

## Known limits

- Copernicus GLO-30 is a **surface** model (it includes buildings and trees). FABDEM (bare-earth, free for research) is a drop-in upgrade.
- Hotspot coordinates in `data/hotspots.csv` are approximate apart from MG Road. Replace them with GPS fixes from the field visit.
- The six newly added candidate locations are provisional monitoring points, not field-verified flood reports; confirm their exact low points and flood history before treating them as validated hotspots.
- Snapping looks for the highest-accumulation cell within a 150 m square window, so the snap distance can reach ~210 m (see `snap_dist_m`).
