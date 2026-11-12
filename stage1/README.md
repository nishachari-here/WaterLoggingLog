# Stage 1 data prep (where does it flood?)

Node classification on the existing road + drain graph, labelled from official
BBMP flood points. **Training is later, in Colab.** This folder only prepares
and exports data.

`label = 0` means **unlabelled** ("not known to flood"), **not** "safe".

## Inputs (do not regenerate the graph)

1. Copy `gnn_graph_nodes.csv` and `gnn_graph_edges.csv` to:

   - `data/graph/gnn_graph_nodes.csv`
   - `data/graph/gnn_graph_edges.csv`

   Do **not** run `run_gnn_graph.py`.

2. Official OpenCity files already in `data/opencity/` (see that README;
   downloaded 11 November 2026). Labels come only from
   `flood_vulnerable.kml`, `flood_prone.kml`, `low_lying.kml`.
   Do not use `data/hotspots.csv` or `data/events/`.

## Setup from a clean clone

```bash
python3 -m venv .venv
.venv/bin/pip install -r stage1/requirements.txt
# graph CSVs must already be in data/graph/ (they are gitignored; >50 MB)
bash stage1/run_all.sh
```

Every script is safe to re-run and must be started from the **repo root**.

## Scripts (order)

| script | output |
| --- | --- |
| `build_flood_points.py` | `data/processed/flood_points.csv` |
| `build_wards.py` | `data/processed/wards.csv`, `wards.geojson` |
| `label_nodes.py` | `data/processed/nodes_labelled.csv` |
| `sanity_check.py` | `stage1/label_stats.csv`, `stage1/labels_map.png` |
| `add_drain_features.py` | `data/processed/nodes_labelled_v2.csv` |
| `export_for_colab.py` | `export/nodes.csv`, `edges.csv`, `node_id_map.csv`, `feature_columns.txt`, `README.md` |

Distances use EPSG:32643. Stored lat/lon are EPSG:4326.

Validation is **leave-one-BBMP-zone-out** (8 zones). Nodes with `zone=outside`
must not be used as a test fold.

Inspection notes (column names, CRS, zone mapping): `INSPECT.md`.
