# Stage 1 inspection (nothing modified in this step)

Inspection date: 12 November 2026. Graph CSVs were copied from
`/Users/krishna/Downloads/` into `data/graph/` (53 MB nodes, 57 MB edges).
Those directories are gitignored because the files exceed 50 MB.

## 1. `data/opencity/README.md`

OpenCity copies downloaded 11 November 2026 (Public Domain; originals BBMP /
KSRSAC). The site was 502 on 12 November 2026 so the repo keeps local copies.

| File | Contents | Expected rows |
| --- | --- | --- |
| `flood_vulnerable.kml` | BBMP flood-vulnerable points | 200 |
| `flood_prone.kml` | BBMP flood-prone locations | 70 |
| `low_lying.kml` | BBMP low-lying areas | 129 |
| `swd_primary.kml` / `swd_secondary.kml` | Official stormwater drains 2022 | 163 lines / 870 lines |
| `wards_2015.kml` | BBMP 198-ward map | 198 |
| `wards_2022.kml` | BBMP 243-ward map | 243 |
| `griev_*.csv` | Grievances (Stage 2; ignored here) | — |

Flood-point total expected: 200 + 70 + 129 = 399.

## 2. Graph nodes — `data/graph/gnn_graph_nodes.csv`

- Rows: **248,287** (unique `node_id`)
- Columns and dtypes:

| column | dtype |
| --- | --- |
| node_id | str |
| node_type | str |
| candidate | bool |
| x | float64 |
| y | float64 |
| lon | float64 |
| lat | float64 |
| road_class | str |
| area_km2 | float64 |
| elev_m | float64 |
| slope_deg | float64 |
| depression_m | float64 |
| upstream_km2 | float64 |
| twi | float64 |
| hand_m | float64 |
| tpi300_m | float64 |
| tpi1000_m | float64 |

First 3 rows (truncated numbers):

| node_id | node_type | candidate | x | y | lon | lat | road_class | area_km2 | elev_m | slope_deg | depression_m | upstream_km2 | twi | hand_m | tpi300_m | tpi1000_m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| road:17327095 | road | True | 781997.05 | 1428672.51 | 77.598721 | 12.910542 | NaN | NaN | 908.93 | 3.252 | 0.0 | 0.1071 | 11.048 | 10.759 | 0.152 | 4.509 |
| road:248007842 | road | True | 781968.27 | 1428913.81 | 77.598478 | 12.912724 | NaN | NaN | 913.01 | 0.750 | 0.0 | 0.0648 | 12.014 | 14.836 | 0.526 | 6.861 |
| road:305154531 | road | True | 782026.74 | 1428674.84 | 77.598994 | 12.910560 | NaN | NaN | 908.80 | 6.033 | 0.0 | 0.1089 | 10.444 | 10.623 | 0.552 | 4.431 |

- **Node id:** `node_id` (strings such as `road:17327095`, `drain:…`; **not** contiguous 0..N-1).
- **Coordinates:** `lon`/`lat` are geographic (lat 12.78–13.18, lon 77.42–77.82) → **EPSG:4326**.
  `x`/`y` are in the hundreds of thousands / millions (x 762315–806175, y 1414035–1458765) → **EPSG:32643** (UTM 43N), matching `config.CRS_METRIC` and `pipeline/combined_graph.py`.
- **8 terrain features:** `elev_m`, `slope_deg`, `depression_m`, `upstream_km2`, `twi`, `hand_m`, `tpi300_m`, `tpi1000_m` (all complete, 0 NaNs).
- `node_type`: road 245,269 / drain 3,018. `candidate` is True for every node.
- `road_class` is NaN on 247,922 nodes (only 365 road nodes have it). `area_km2` is NaN on all road nodes (filled only on drain nodes).

## 3. Graph edges — `data/graph/gnn_graph_edges.csv`

- Rows: **619,776**
- Columns: `source` (str), `target` (str), `edge_key` (str), `edge_type` (str), `length_m` (float), `travel_time_s` (float), `area_km2` (float), `drop_m` (float), `connection_distance_m` (float), `road_class` (str).
- **Source / target:** `source`, `target`.
- **Directed:** yes. 617,766 unique (source, target) pairs; **593,724** of those also have the reverse pair. 216 self-loops. `edge_type` counts: road 606,059; road_drain 10,758; drain 2,959.
- **Edge features:** yes — `edge_key`, `edge_type`, `length_m`, `travel_time_s`, `area_km2`, `drop_m`, `connection_distance_m`, `road_class`.
- Every endpoint exists in the node file (0 missing src/tgt). 1 node has no incident edge.
- Node ids are **not** contiguous integers; they are OSM/drain string ids as above.

## 4. Label-leak / hotspot columns

**None of the node columns look like hotspot or physics-risk leakage.** There is no `hotspot_id`, `risk`, `is_hotspot`, distance-to-hotspot, or event-count column.

Still **excluded from the Colab feature list** (not terrain; some are ids/coords or mostly missing):

- `node_id`, `node_type`, `candidate`, `x`, `y`, `lon`, `lat`, `road_class`, `area_km2`

`candidate` is a graph-builder flag (always True), not a flood label. `area_km2` is the DEM drainage-node catchment from `combined_graph.py`, not a hotspot field.

`data/hotspots.csv` and `data/events/` were not used.

## 5. Ward maps

### `wards_2015.kml` — **chosen map**

- Features: **198**. One KML layer: `BBMP Wards`. Geometry: 195 Polygon + 3 MultiPolygon. CRS EPSG:4326.
- Attribute names after pyogrio: `id`, `Name`, `description`, `timestamp`, `begin`, `end`, `altitudeMode`, `tessellate`, `extrude`, `visibility`, `drawOrder`, `icon`, `Ward_Name`, `Zone`, `Division`, `Subdivision`, `Assembly__MLA__Constituency_`, `Parliament__MP__Constituency`, `geometry`.
- **Ward-name column:** `Ward_Name` (198 unique). Placemark `Name` is `Ward 1` … `Ward 198` (non-breaking space after “Ward”); digits parse to unique ids 1–198.
- **Zone column:** `Zone`.

Raw `Zone` values (9 strings because of NBSP and one spelling split):

| raw value | count |
| --- | --- |
| East | 44 |
| West | 44 |
| South | 44 |
| Mahadevapura | 17 |
| Bommanahalli\\xa0 | 16 |
| Rajarajeswari Nagar | 12 |
| Yelahanka | 11 |
| Dasarahalli\\xa0 | 8 |
| Rajarajeshwari Nagar | 2 |

After stripping NBSP/whitespace and mapping `Rajarajeswari Nagar` → `Rajarajeshwari Nagar` this is **198 wards and the 8 BBMP zones** requested. That mapping is used everywhere.

### `wards_2022.kml` — not used

- Features: **243**. No zone column. Ward name: `WardName`. Does not match “198 wards / 8 zones”.

## 6. Flood KMLs

All three are single-layer Point files, 2D (no Z), CRS EPSG:4326.

| file | layer name | features | geometry | attributes with data |
| --- | --- | --- | --- | --- |
| flood_vulnerable.kml | flood_vulnerable_locations | **200** | Point | OBJECTID, WARD_NAME, WARDNO, LocationName, KGISFVLID, ZONE (`Name` is empty; use LocationName) |
| flood_prone.kml | flood_prone_locations | **70** | Point | OBJECTID, Name (no ward/zone fields) |
| low_lying.kml | lowlying_locations | **129** | Point | OBJECTID, Name (no ward/zone fields) |

Total **399**, as expected. `flood_prone` / `low_lying` original ward and zone attributes are empty; official ward/zone come from the spatial join.

## 7. Zone-name mapping (flood attributes vs chosen ward map)

Compare after lowercase + whitespace/NBSP strip.

Flood-vulnerable `ZONE` values: Bommanahalli, Dasarahalli, East, Mahadevapura, **RR Nagar** (29), South, West, Yelahanka.

Ward map (after NBSP strip) uses **Rajarajeswari Nagar** (12) and **Rajarajeshwari Nagar** (2), never “RR Nagar”.

Mapping applied:

| source spelling | canonical zone |
| --- | --- |
| RR Nagar | Rajarajeshwari Nagar |
| Rajarajeswari Nagar | Rajarajeshwari Nagar |
| Rajarajeshwari Nagar | Rajarajeshwari Nagar |
| Bommanahalli / Dasarahalli (+ trailing NBSP) | Bommanahalli / Dasarahalli |
| East, Mahadevapura, South, West, Yelahanka | unchanged |

Official zone on points and nodes is always the spatially joined (canonical) ward-map zone, not the KML attribute. Original KML values are kept as `ward_attr` / `zone_attr`.
