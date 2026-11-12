# Stage 2 data prep (when does a ward report flooding?)

One sample is one of the 198 BBMP wards on one day, from 8 February 2020
through 19 June 2025. **Training is not run here.**

`y = 1` if that ward has at least one complaint whose sub-category is
`water stagnation` on that date. The grievance hour is ignored: the export
uses hours 1–12 with no AM/PM.

## Inputs (already on disk; do not regenerate)

- `data/processed/nodes_labelled_v2.csv`, `wards.csv`, `wards.geojson`,
  `flood_points.csv` from Stage 1.
- `data/rain/rain_hourly.csv` (Open-Meteo archive, already downloaded).
- `data/opencity/griev_2020.csv` … `griev_2025.csv`.

Ward-name matching reuses `pipeline/labels.py` (`MANUAL_WARDS` and the
one-to-one check). This folder does not rebuild the graph or the DEM.

## Setup

From the repo root, with the existing virtualenv:

```bash
bash stage2/run_all.sh
```

Each script saves its own file under `data/processed/stage2/` before the next
script starts. `data/processed/` is gitignored.

## Scripts

| script | output |
| --- | --- |
| `aggregate_ward_terrain.py` | `ward_terrain.csv` |
| `clean_complaints.py` | `complaints_clean.csv`, `complaint_daily.csv` |
| `build_rain_features.py` | `rain_daily.csv` |
| `build_ward_days.py` | `ward_days.csv` |
| `make_temporal_splits.py` | `ward_days_split.csv`, `split_summary.csv` |

## Features

Ward terrain is the mean of Stage 1 node features inside the ward
(`elev_m`, `slope_deg`, `depression_m`, `upstream_km2`, `twi`, `hand_m`,
`tpi300_m`, `tpi1000_m`, `dist_to_official_drain_m`, `drain_density_500m`),
plus `hand_lt2_frac`, official flood-point counts, and
`positive_node_frac` (share of nodes with Stage 1 `label = 1`).

`positive_node_frac` is label density, not a trained Stage 1 score.
No model is fit in this folder.

Rain features follow `pipeline/rain_history.py`: same-day `rain` and `peak`,
`rain_lag1`, `rain_2d` (today + yesterday), `rain_3d` (includes today),
`rain_ante7` (previous 7 days, not today), `peak_2d`, and `sm_prev`
(yesterday's mean soil moisture). Wards share a 0.1-degree `rain_cell`
from the ward centroid.

`drain_30d` is the sum of drain-complaint counts over the previous 30 days
(`shift(1)`), so the predicted day does not leak into that feature.

`n_other` excludes both water-stagnation and drain sub-categories.
`pipeline/labels.py` counts drain rows inside `n_other` as well; this
prep keeps those counts separate. `y` still depends only on water stagnation.

## Splits

| split | dates |
| --- | --- |
| train | 2020-02-08 through 2022-12-31 |
| tune | all of 2023 |
| test | 2024-01-01 through 2025-06-19 |

Do not reshuffle rows. Touch the test split once, after tuning on 2023.
