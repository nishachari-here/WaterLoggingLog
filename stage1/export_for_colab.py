#!/usr/bin/env python3
"""Write a Colab-ready node/edge package with contiguous ids."""
from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    DRAIN_FEATURES,
    EDGES_GRAPH,
    EXPORT,
    PROCESSED,
    TERRAIN_FEATURES,
    ensure_dirs,
)


def choose_nodes_path() -> Path:
    v2 = PROCESSED / "nodes_labelled_v2.csv"
    v1 = PROCESSED / "nodes_labelled.csv"
    if v2.exists():
        print(f"using {v2}")
        return v2
    print(f"using {v1} (no v2)")
    return v1


def main():
    ensure_dirs()
    print("STEP 6  Colab export")
    nodes = pd.read_csv(choose_nodes_path())
    edges = pd.read_csv(EDGES_GRAPH)

    feature_cols = list(TERRAIN_FEATURES)
    for col in DRAIN_FEATURES:
        if col in nodes.columns:
            feature_cols.append(col)
        else:
            print(f"NOTE: {col} not present; omitting from feature_columns.txt")

    leaky = [
        c for c in nodes.columns
        if any(tok in c.lower() for tok in ("hotspot", "risk", "event_count", "is_flood"))
    ]
    if leaky:
        print(f"WARNING: excluding possible leak columns from features: {leaky}")
        feature_cols = [c for c in feature_cols if c not in leaky]

    orig_id = nodes["node_id"]
    if orig_id.duplicated().any():
        raise SystemExit("STOP: duplicate orig_id in nodes")
    node_idx = pd.RangeIndex(len(nodes))
    id_map = pd.DataFrame({"orig_id": orig_id.to_numpy(), "node_idx": node_idx})
    lookup = dict(zip(id_map["orig_id"], id_map["node_idx"]))

    nan_report = []
    for col in feature_cols:
        numeric = pd.to_numeric(nodes[col], errors="coerce")
        n_nan = int(numeric.isna().sum())
        n_inf = int(np.isinf(numeric.to_numpy(dtype=float)).sum())
        if n_nan or n_inf:
            nan_report.append((col, n_nan, n_inf))
    if nan_report:
        print("NaN/inf in feature columns (inf -> NaN, then fill with column median):")
        for col, n_nan, n_inf in nan_report:
            print(f"  {col}: NaN={n_nan} inf={n_inf}")
            series = pd.to_numeric(nodes[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
            median = series.median()
            nodes[col] = series.fillna(median)
            print(f"    filled with median={median}")
    else:
        print("feature columns: no NaN/inf")

    export_nodes = pd.DataFrame({
        "node_idx": id_map["node_idx"].to_numpy(),
        "orig_id": id_map["orig_id"].to_numpy(),
        **{col: nodes[col].to_numpy() for col in feature_cols},
        "label": nodes["label"].to_numpy(),
        "labelled_status": nodes["labelled_status"].to_numpy(),
        "ward_id": nodes["ward_id"].to_numpy(),
        "zone": nodes["zone"].to_numpy(),
        "lat": nodes["lat"].to_numpy(),
        "lon": nodes["lon"].to_numpy(),
    })

    n_src_miss = int((~edges["source"].isin(lookup)).sum())
    n_tgt_miss = int((~edges["target"].isin(lookup)).sum())
    keep = edges["source"].isin(lookup) & edges["target"].isin(lookup)
    dropped = int((~keep).sum())
    print(f"edges dropped (missing endpoint): {dropped} (src missing rows={n_src_miss}, tgt missing rows={n_tgt_miss})")
    edges_ok = edges.loc[keep].copy()
    export_edges = pd.DataFrame({
        "src": edges_ok["source"].map(lookup).astype(int).to_numpy(),
        "dst": edges_ok["target"].map(lookup).astype(int).to_numpy(),
    })
    for col in edges_ok.columns:
        if col in ("source", "target"):
            continue
        export_edges[col] = edges_ok[col].to_numpy()

    assert export_nodes["node_idx"].is_unique
    assert export_nodes["node_idx"].min() == 0
    assert export_nodes["node_idx"].max() == len(export_nodes) - 1
    used = set(export_edges["src"]).union(set(export_edges["dst"]))
    known = set(export_nodes["node_idx"])
    extra = used - known
    if extra:
        raise SystemExit(f"STOP: edge ids not in nodes: {list(extra)[:10]}")
    for col in feature_cols:
        if np.isnan(export_nodes[col].to_numpy(dtype=float)).any():
            raise SystemExit(f"STOP: NaN remain in {col}")

    EXPORT.mkdir(parents=True, exist_ok=True)
    export_nodes.to_csv(EXPORT / "nodes.csv", index=False)
    export_edges.to_csv(EXPORT / "edges.csv", index=False)
    id_map.to_csv(EXPORT / "node_id_map.csv", index=False)
    (EXPORT / "feature_columns.txt").write_text("\n".join(feature_cols) + "\n")
    (EXPORT / "README.md").write_text(export_readme(feature_cols, export_nodes, export_edges, dropped))
    print(f"wrote {EXPORT / 'nodes.csv'} ({len(export_nodes)} rows)")
    print(f"wrote {EXPORT / 'edges.csv'} ({len(export_edges)} rows)")
    print(f"wrote {EXPORT / 'node_id_map.csv'}")
    print(f"wrote {EXPORT / 'feature_columns.txt'}: {feature_cols}")
    print(f"wrote {EXPORT / 'README.md'}")


def export_readme(feature_cols, nodes, edges, dropped_edges) -> str:
    today = date.today().isoformat()
    cols = "\n".join(f"- `{c}`" for c in feature_cols)
    zone_counts = nodes.groupby("zone").size().to_string()
    pos = int(nodes["label"].sum())
    return f"""# Stage 1 Colab export

Prepared {today} from the WaterLoggingLog repo. Training is **not** run here.

## Label definition

A node has `label = 1` if it is within **150 m** (EPSG:32643) of an official BBMP
flood point. Flood points come only from:

- `data/opencity/flood_vulnerable.kml` (200 points)
- `data/opencity/flood_prone.kml` (70 points)
- `data/opencity/low_lying.kml` (129 points)

Downloaded from OpenCity on **11 November 2026** (BBMP / KSRSAC, public domain).
Points outside the 2015 BBMP ward boundary were dropped, then points within
**100 m** of each other were merged (one representative per cluster; layer names
joined with `|`).

`labelled_status` is `positive` when `label = 1`, else `unlabelled`.

**`label = 0` means unlabelled ("not known to flood"), NOT safe.** Do not treat
zeros as a negative class without a sampling scheme.

`data/hotspots.csv` and `data/events/` were not used for labels or features.

## Hold-out key

`zone` is the validation fold key. Use the 8 BBMP zones; **do not use `outside`
as a test fold** (those nodes sit outside every 2015 ward polygon).

{zone_counts}

## Graph source

`data/graph/gnn_graph_nodes.csv` and `data/graph/gnn_graph_edges.csv` (copied from
the files attached on 12 November 2026; originally produced by `run_gnn_graph.py`
/ `pipeline/combined_graph.py`). Not regenerated in this pipeline.

- nodes: {len(nodes)}
- positives: {pos}
- edges kept: {len(edges)} (dropped {dropped_edges} with a missing endpoint)

`node_idx` is contiguous `0 .. N-1`. `orig_id` is the original string id
(`road:…` / `drain:…`). Edges `src`/`dst` use `node_idx`. Edge direction is
unchanged from the input graph.

## Feature columns (`feature_columns.txt`)

Eight DEM terrain features, plus official-drain features if Step 5 ran:

{cols}

Excluded: ids, lat/lon, label, labelled_status, ward_id, zone, `node_type`,
`candidate`, `road_class`, `area_km2`, and anything derived from distance to
flood points or hotspots.

## Other files

- `nodes.csv` — `node_idx`, `orig_id`, features, `label`, `labelled_status`, `ward_id`, `zone`, `lat`, `lon`
- `edges.csv` — `src`, `dst`, plus input edge features (`edge_key`, `edge_type`, `length_m`, …)
- `node_id_map.csv` — `orig_id` → `node_idx`
- Wards: 2015 map, 198 wards, 8 zones (`data/opencity/wards_2015.kml`, OpenCity 11 November 2026)
- Official drains: `swd_primary.kml`, `swd_secondary.kml` (OpenCity / BBMP 2022 dump, copied 11 November 2026)
"""


if __name__ == "__main__":
    main()
