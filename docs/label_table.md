# Label table: hotspot-days, 2022–2025

`run_labels.py` builds the shared hotspot-day table for the physics model, the logistic
baselines and the GNN branch. Everything is saved in `outputs/` so the GNN experiment
uses exactly the same rows, labels and rain windows.

## What is in the table

`outputs/label_table.csv` has **17,520 rows**: 12 hotspots × 1,460 days. It covers
2022-01-01 to 2025-12-31; 2022-01-01 is dropped because its 24 h rain window is
incomplete. Evaluation uses the wet season (April–December), the same window as
`pipeline/backtest.py`, giving 13,200 hotspot-days and **24 positive labels on 13 dates**.

| Group | Columns |
|---|---|
| Identity | `date`, `id`, `name`, `kind`, `hotspot_lat`, `hotspot_lon` |
| Graph node | `node_id`, `node_type`, `node_lat`, `node_lon`, `snap_dist_m` |
| Rain | `rain_peak_1h`, `rain_3h`, `rain_24h` (plus `*_corrected` and `*_log`) |
| Terrain (from the node) | `hand_m`, `depression_m`, `upstream_km2`, `twi`, `tpi300_m`, `tpi1000_m`, `elev_m`, `slope_deg` |
| Terrain baseline | `terrain_score` (static susceptibility from `outputs/hotspot_terrain_features.csv`) |
| Physics | `i_crit_mm_h`, `threshold_source`, `physics_ratio`, `physics_ratio_corrected` |
| Label | `label` (0/1), `label_confidence`, `evidence`, `source` |
| Split helper | `wet_season` |

`physics_ratio = rain_peak_1h / i_crit_mm_h` and is kept separate so it can be tested
alone. `*_corrected` multiplies by the median reported/modelled rain ratio (4.8) from
`outputs/backtest_rain_bias.csv`; this is a constant, so it does not change any rank-based
metric, but it is what the dashboard uses for threshold alerts.

## Hotspot to graph-node snap

The nearest node in `data/graphs/gnn_graph_nodes.csv` is used, measured in UTM 43N
(the graph's `x`, `y`). All 12 nearest nodes are road nodes, and all snaps are tight:

| Hotspot | Node | Snap (m) |
|---|---|---:|
| Silk Board | road:10855370147 | 6.2 |
| Hebbal | road:2460383180 | 7.0 |
| Kadubeesanahalli | road:2113348452 | 67.3 |
| HAL–Marathahalli | road:343334152 | 18.7 |
| KR Circle | road:10978687879 | 10.0 |
| Bellandur | road:9788419608 | 17.3 |
| Madiwala | road:6518859291 | 31.8 |
| Koramangala | road:443224603 | 49.2 |
| Sai Layout | road:11385292962 | 18.4 |
| Manyata | road:13304639726 | 59.7 |
| Kogilu | road:4950456088 | 66.3 |
| MG Road | road:246397923 | 13.4 |

The ~210 m limit in the README is the **DEM terrain snap** (`snap_dist_m` in
`hotspot_terrain_features.csv`), not this graph snap. The graph snap is much tighter
because the road network is dense. For the physics threshold, the nearest **drain**
node is used separately; those distances are larger (66–804 m), and the drain node is
recorded in `outputs/hotspot_thresholds.csv`.

## Rain window and label timing

**Choice: the 24 hourly values ending at 12:00 local time on the report date D**
(D-1 13:00 through D 12:00). In D vs D-1 terms, the trigger is the **previous
evening/night (D-1)**, with the window ending at noon on D so an overnight flood
reported the next morning is included.

Why: most of the labels describe overnight rain reported the next day.

- 2022-10-20: "Waterlogging reported **night of 19 Oct**"
- 2023-06-13: "rain **night of 12 Jun**"
- 2024-08-12: "**overnight rains** cause widespread waterlogging"
- 2025-05-19: "torrential **overnight rain**"

The alternatives were scored on the same 24 labels (`outputs/label_table_alignment.csv`):

| Alignment | Window | AUC peak | AUC total | AUC physics | Recall@5% FAR (physics) |
|---|---|---:|---:|---:|---:|
| Same day | D 00:00–D 23:00 | 0.797 | 0.793 | 0.809 | 0.292 |
| **Report day (chosen)** | **D-1 13:00–D 12:00** | **0.772** | **0.800** | **0.782** | **0.458** |
| Previous day | D-1 00:00–D-1 23:00 | 0.779 | 0.783 | 0.792 | 0.292 |
| Old backtest 36 h | D-1 12:00–D 23:00 | 0.824 | 0.826 | 0.835 | 0.333 |

The old 36 h window has a slightly higher AUC, but it includes the evening **after** a
morning report. The chosen 24 h report-day window has the best recall at 5% false
alarms for the physics feature and does not use post-report rain. The differences are
within the noise of 24 positives; the choice is made on the evidence, not by tuning.

A label-shift check (`outputs/label_table_label_shift.csv`) confirms the date is not
systematically one day off:

| Label shift | AUC physics | Recall@5% FAR (physics) |
|---|---:|---:|
| −2 days | 0.716 | 0.000 |
| −1 day | 0.731 | 0.250 |
| **0 days** | **0.782** | **0.458** |
| +1 day | 0.816 | 0.208 |
| +2 days | 0.778 | 0.250 |

Shift 0 has the best recall. Shift +1 has a higher AUC but catches fewer floods at the
same false-alarm budget, so the news dates are kept as reported.

## Thresholds

`outputs/hotspot_thresholds.csv` gives the critical intensity at 20% blockage. Six
values are copied from the existing risk.py backtest output (`outputs/leadtime_events.csv`).
The other six are recomputed with the same risk.py formula on the GNN drain graph
because the original `data/processed/drain_graph.pkl` is not committed. The
recomputation reproduces five of the six known values within rounding (Silk Board,
Madiwala, Manyata, Sai Layout, Hebbal). Kogilu is the exception: the GNN graph breaks the
downstream path at a different segment (21.0 vs 28.4 mm/h), so the known value is used.

| Hotspot | `i_crit_mm_h` | Source |
|---|---:|---|
| Silk Board | 22.4 | risk.py output |
| Hebbal | 30.7 | risk.py output |
| Kadubeesanahalli | 41.1 | GNN drain graph |
| HAL–Marathahalli | 24.4 | GNN drain graph |
| KR Circle | 38.6 | GNN drain graph |
| Bellandur | 24.5 | GNN drain graph |
| Madiwala | 22.4 | risk.py output |
| Koramangala | 42.8 | GNN drain graph |
| Sai Layout | 31.8 | risk.py output |
| Manyata | 19.0 | risk.py output |
| Kogilu | 28.4 | risk.py output |
| MG Road | 38.6 | GNN drain graph |

## Validation protocol

- **Leave-one-hotspot-out (LOHO).** Each fold holds out one hotspot; the model never
  sees that hotspot's rows in training. This prevents the same place leaking into both
  sides.
- **Class weights.** `LogisticRegression(class_weight="balanced")` because only 24 of
  13,200 rows are positive.
- **Tuning inside the training folds.** The regularisation strength `C` is chosen by
  `StratifiedGroupKFold(4)` on the training hotspots only, scored by ROC AUC. The
  grid is 0.0003 to 10.
- **False-alarm threshold inside the training folds.** The deployment-style recall
  threshold is chosen from inner out-of-fold predictions on training negatives at 5%
  and 1% false alarms, then applied to the held-out hotspot. The pooled ranking
  `recall@FAR` (threshold on the evaluation negatives) is also reported for comparison.
- **No accuracy.** Floods are 0.18% of rows, so accuracy is meaningless here.
- **Confidence intervals.** 95% CIs resample whole days, because hotspots on the same
  day share the same rain.

## Results

`outputs/label_table_metrics.csv` (13,200 wet-season hotspot-days, 24 positives):

| Model | AUC (95% CI) | AP | Recall@5% FAR | Recall@1% FAR |
|---|---:|---:|---:|---:|
| Rain rule (peak 1 h) | 0.772 (0.633–0.883) | 0.009 | 0.375 | 0.000 |
| Terrain only (static score) | 0.490 (0.305–0.614) | 0.002 | 0.000 | 0.000 |
| Terrain × rain | 0.770 (0.627–0.880) | 0.008 | 0.333 | 0.042 |
| **Physics ratio alone** | **0.782 (0.632–0.894)** | **0.012** | **0.458** | 0.042 |
| Logit: rain | 0.763 (0.594–0.895) | 0.010 | 0.458 | 0.042 |
| Logit: terrain | 0.521 (0.404–0.652) | 0.002 | 0.000 | 0.000 |
| Logit: rain + terrain | 0.750 (0.593–0.886) | 0.010 | 0.375 | 0.083 |
| **Logit: rain + physics** | **0.780 (0.620–0.898)** | **0.014** | **0.458** | 0.083 |
| Logit: all | 0.751 (0.567–0.893) | 0.011 | 0.375 | 0.042 |

The deployment-style recall (threshold chosen in training folds) equals the pooled
recall for the physics ratio and the rain+physics logistic model, so the result is not
an artefact of choosing a threshold on the test set.

## What it means

1. **The physics ratio is the best single feature.** Peak rain divided by the hotspot's
   drain threshold gives AUC 0.782 and catches 11 of 24 floods at 5% false alarms. The
   city-wide rain-peak rule gives 0.772 and catches 9 of 24. The confidence intervals
   overlap, so this is a small improvement, not a proven one.
2. **Terrain alone cannot tell you when.** The static terrain score is at chance (0.490)
   and catches no floods at 5% FAR. A logistic model on the node's terrain features is
   barely better (0.521). This is the same conclusion as the existing backtest.
3. **Adding terrain to the logistic model hurts.** Rain+physics is 0.780; rain+terrain
   drops to 0.750; all features drop to 0.751. With 12 hotspots and 24 labels, the
   terrain features add variance, not signal.
4. **The logistic model does not beat the physics ratio.** It ties it on recall and is
   0.002 lower on AUC. The honest reading is that with 24 positives there is not enough
   label information to learn more than the physics already encodes. The logistic model
   is still useful for calibrated probabilities, not for ranking.
5. **Raw thresholds never fire on gridded rain.** Open-Meteo's maximum hourly value in
   this sample is 17.9 mm/h, below every hotspot threshold. With the dashboard's ×4.8
   bias correction, the physics threshold fires on 11/24 floods with 4.6% false alarms;
   the city-wide 40 mm/h rule fires on 4/24 with 1.9% false alarms
   (`outputs/label_table_rules.csv`). The ranking comparison above is the fair one
   because it is threshold-free.

## Caveats

- **24 positives on 13 dates.** The confidence intervals are wide; do not report the
  point estimates as significant.
- **Unreported is not dry.** A flood nobody wrote about is a negative in this table.
- **Media attention.** Silk Board has 5 labels; MG Road has 0. A model that ranks famous
  spots high gets some credit for fame.
- **Placeholder capacities.** Six thresholds come from the placeholder drain rule; the
  field visits will change them and this table should be rebuilt afterwards.
- **Gridded rain is weak.** The bias factor is a median correction, not a gauge. KSNDMC
  gauge data would remove most of this error.

## Files

| File | What it is |
|---|---|
| `outputs/label_table.csv` | The shared feature table |
| `outputs/hotspot_graph_nodes.csv` | Hotspot → nearest graph node and snap distance |
| `outputs/hotspot_thresholds.csv` | risk.py threshold, bottleneck area and source |
| `outputs/label_table_metrics.csv` | LOHO model comparison |
| `outputs/label_table_oof_predictions.csv` | Out-of-fold scores for every model |
| `outputs/label_table_alignment.csv` | Rain-window comparison |
| `outputs/label_table_label_shift.csv` | Label-date ±2 days sensitivity |
| `outputs/label_table_rules.csv` | Fixed-threshold alert rules |

## Rerun

```bash
.venv\Scripts\python run_labels.py
```

The first run downloads 2022–2025 hourly rain from Open-Meteo and caches it at
`data/raw/rain/hist_forecast_hourly.csv` (gitignored). Later runs reuse the cache.
The GNN branch should read `outputs/label_table.csv` and keep the same `date`/`id`
rows and `label` column; re-snapping hotspots or recomputing the rain windows would
break comparability.
