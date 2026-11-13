# Final plan to submission

*Written 11 November 2026, updated 12 November 2026. This replaces the GNN advice in
[ml_recommendation.md](ml_recommendation.md): we now have real labels, so a GNN can be trained and compared.*

## Bottom line

Real labelled flood data for Bengaluru exists and is in this repo (`data/opencity`). We do not need
pseudo-labels or AI-generated data.

1. **Train on two real datasets** (BBMP and KSRSAC records, via the OpenCity portal, public domain):
   399 official flood points, and 8,274 dated "water stagnation" complaints across 198 wards
   (February 2020 to June 2025).
2. **Do not train on a risk formula.** A model trained to copy our own formula cannot be shown to predict
   real floods. Keep the physics formula as an input feature and as a baseline to beat.
3. **Two-stage model.** Stage 1 learns *where* (which places look like the official flood points).
   Stage 2 learns *when* (which ward reports flooding on which day, given rain). Together they give each
   hotspot a Low, Medium or High risk level.
4. **Compare a GNN with simpler models and report the winner honestly.**
5. **Finish the phone demo:** live GPS, risk levels, rerouting, and a replay of the 19 May 2025 storm.

## What is already in the repo

| Piece | Where | Status |
| --- | --- | --- |
| Raw label data, drain maps, ward maps | `data/opencity/` (see its README for sources) | Done |
| Rain and soil moisture, hourly, 2020 to mid-2025 | `data/rain/rain_hourly.csv` | Done |
| Label loading and ward-name matching (all 198 wards) | `pipeline/labels.py` | Done |
| Rain features | `pipeline/rain_history.py` | Done |
| Stage 1 baseline (logistic, Random Forest, boosting) | `pipeline/stage1.py`, `run_stage1.py` | Done |
| Stage 2 baseline (rain rule, logistic, boosting) | `pipeline/stage2.py`, `run_stage2.py` | Done |
| Combined road + drain graph for the GNN | `pipeline/combined_graph.py`, `run_gnn_graph.py` | Done |
| Shared hotspot-day label table | `pipeline/labels.py`, `run_labels.py`, `outputs/label_table.csv` | Done |
| Terrain, drain graph, physics model, routing, dashboard | `pipeline/`, `server.py`, `frontend/DDRM/` | Done |
| First GNN experiment (GCN on a hotspot graph) | `run_gnn_experiment.py` | Done — AUC 0.55, does not beat baselines |
| GraphSAGE GNN for Stage 1 | not started | **To do** |
| GNN on the ward graph for Stage 2 | not started | **To do** |
| Risk levels in the app, replay mode, phone GPS | `server.py`, `frontend/DDRM/` | Done (GPS needs HTTPS on a phone) |

As of 12 November 2026, the app-side items (risk levels, storm replay, GPS start point) are done. The
backtest now uses the forecast cache for all 18 hotspots; remaining work includes the full terrain-derived
drain graph, the two GNNs, and HTTPS for phone GPS.

## Baseline results (from the scripts in this repo)

These are first models with terrain features and coarse rain. They show the data works. They are the
numbers the GNN and the extra features must beat.

**Stage 1**, 372 flood points vs 4,000 background points, one zone held out at a time
(`outputs/stage1_metrics.csv`):

| Model | Mean AUC across 8 zones | Flood points inside the top 20% of area |
| --- | --- | --- |
| Logistic regression | 0.68 | 46% |
| Random Forest | 0.68 | 45% |
| Gradient boosting | 0.67 | 47% |

A public project on the same labels ([pkjx29/bengaluru-flood-risk](https://github.com/pkjx29/bengaluru-flood-risk))
reaches 0.775 with 23 features under spatial cross-validation, so drain and built-up features should help.

**Stage 2**, 198 wards, 387,882 ward-days, 6,029 with a flood complaint. Trained on 2020–2023, tested on
2024 to June 2025 (`outputs/stage2_metrics.csv`):

| Model | AUC | Recall at 5% false alarms | Within-day AUC |
| --- | --- | --- | --- |
| Rule: two-day rain total | 0.73 | 0.26 | 0.46 |
| Rain only, logistic regression | 0.73 | 0.23 | 0.48 |
| Rain only, gradient boosting | 0.71 | 0.19 | 0.48 |
| Rain + soil moisture | 0.72 | 0.22 | 0.49 |
| Rain + ward terrain + BBMP flood points | 0.80 | 0.32 | 0.70 |
| The above + drain complaints (last 30 days) | 0.80 | 0.33 | 0.72 |
| The above + soil moisture + month | 0.81 | 0.34 | 0.72 |

Within-day AUC is scored across wards on the 53 test days when 10 or more wards reported flooding. It
asks whether the model picks the right wards. Rain alone cannot (0.46 to 0.49, where 0.5 is chance)
because the rain data is nearly the same across the city. Ward features lift it to about 0.72. That is
the evidence that the model adds something a rainfall rule cannot. Soil moisture adds 0.01 or less.

## Why not the "physics pseudo-label" GNN

The idea was to compute a risk score from a formula (rain, soil moisture, HAND, slope) and train a GNN
to predict it. The target would be calculated from the same inputs the model receives, so the best the
GNN can do is reproduce our formula. Its accuracy would measure how well it copied us, not how well it
predicts flooding, and there would be no ground truth to show. A GNN "surrogate" is legitimate when the
teacher is a slow physical simulator (Bentivoglio et al., 2023); we do not have one.

What we keep from the idea: output a risk level instead of yes/no, and use the physics as a feature.

## What to build next

| | Stage 1: where | Stage 2: when |
| --- | --- | --- |
| One sample | A node of the combined road + drain graph | One ward on one day |
| Label | 1 if within 150 m of an official flood point | 1 if the ward has a flood complaint that day |
| Add features | Distance to an official drain (`swd_*.kml`), drain density, distance to a lake, road class, building density | Rain per ward centroid; the physics model's rain ÷ threshold; Stage 1 score averaged per ward |
| Add models | GraphSAGE (PyTorch Geometric) on `gnn_graph.pkl` | GNN on the ward graph: wards as nodes, shared borders as edges |
| Validation | The same 8 zone folds as `stage1.py` | Train 2020–2022, tune on 2023, test once on 2024–25 |

**Is this enough data for a GNN?** Stage 1 is semi-supervised node classification. The original GCN
paper (Kipf and Welling) trained on Cora with 140 labelled nodes out of 2,708. We have 372 labelled
places. Stage 2 has about 388,000 samples.

**From ward risk to hotspot risk.** The hotspot list becomes the official BBMP points plus our
hand-listed ones. Each day a hotspot takes its ward's risk level from Stage 2, moved one step up or down
by its Stage 1 score. Test those levels against the 24 news-sourced events in
`data/events/flood_events.csv`, which neither model is trained on.

**Rules that keep the results honest**

- Split by time and by zone, never at random.
- Compare every model with the rain rule and with the existing physics model.
- Unlabelled is not the same as safe: report average precision next to AUC.
- If the GNN does not beat gradient boosting, report that. It is a valid finding.

## Backtest rain source and graph status

The reported 0.84 and 0.56 drain-graph AUCs came from different rain sources, so they are not a
valid before/after comparison and do not identify a drain-graph regression. With the 0.1° archive
(`data/rain/rain_hourly.csv`), the rain-peak baseline and drain-graph model score 0.861 and 0.841
on 12 hotspots, and 0.863 and 0.859 on all 18. With the 0.25° forecast cache, the official
all-18-hotspot scores are rain-peak AUC 0.606 and drain-graph AUC 0.631. These are the official
forecast-source metrics now recorded in `outputs/backtest_metrics.csv`. `backtest.run()` also obtains
`rain_bias()` from the network, so the bias comparison is not fully reproducible offline and should be
reported separately from the cached-rain metrics.

The app and backtest currently use a reduced fallback drain graph when the processed terrain and
network artifacts are absent. Rebuild `data/processed/` with `run_terrain.py` and `run_network.py`
before treating drain-graph results as final. The reported metrics use the fallback graph.

For now the app's risk levels come from the physics model (`rain ÷ i_crit`); the dashboard is careful to
say so, and three hotspots with no modelled drain path
show "no modelled drain path" instead of a threshold.

**First GNN result.** `run_gnn_experiment.py` trains a GCN on a spatial hotspot graph over the shared
label table, under leave-one-hotspot-out and leave-one-date-out folds. It reaches AUC 0.55
(`outputs/gnn_experiment_metrics.csv`), below Stage 1 (0.68) and Stage 2 (0.81). This is a real finding to
report: a small hotspot graph with these features is not enough for the GNN to win. The GraphSAGE and
ward-graph GNNs remain the experiments that could change that.

## Schedule (five days, five roles)

| Day | Data (A) | Models (B: Stage 1, C: Stage 2) | App (D) | Report (E) |
| --- | --- | --- | --- | --- |
| 1 | Check the ward matching and label counts. Request KSNDMC gauge data (optional) | B: choose and document the backtest rain source; rebuild artifacts and regenerate metrics. C: rerun `run_stage2.py`, add the 2023 tuning split | Show the BBMP flood points on the map | Rewrite the methodology slide: two stages, real labels |
| 2 | Add drain, lake and building features | B: attach labels to the combined graph, add features. C: add physics and Stage 1 features | Server reads model output: Low, Medium, High per hotspot | Literature table, data section |
| 3 | Freeze dataset v1, write the data card | B: GraphSAGE. C: ward-graph GNN. Same splits as the baselines | Phone access over HTTPS, GPS start point | Results section |
| 4 | Ablations with C | Final comparison table, hotspot-level test on the 24 news events, calibration plot | Replay mode for 19 May 2025; test on a real phone | Slides, limits slide, viva answers |
| 5 | Buffer | Re-run everything from a clean clone | Rehearse the demo; record a backup video | Rehearse; check every number against the outputs |

If only three days remain: keep Day 1, the Stage 1 GraphSAGE, the Stage 2 boosting model, risk levels
in the app and replay mode. Drop the ward-graph GNN and the extra features beyond drain distance.

## Demo on result day

1. Show the data source: every label is a BBMP or KSRSAC record.
2. Replay 19 May 2025: hotspots turn amber and red as the storm arrives; compare with what was reported.
3. Pick a trip on the phone: the app names the High-risk hotspots on the usual route and draws another.
4. Switch to today's forecast: if dry, everything is green.
5. One slide with the comparison table.

Record the in-car version as a video beforehand. Do the rest live in the room.

## What to say to evaluators

| Question | Answer |
| --- | --- |
| What is your ground truth? | 399 mapped flood points and 8,274 dated flood complaints, BBMP and KSRSAC records accessed via OpenCity. Plus 24 news-reported floods kept as an independent test |
| Is any data synthetic? | No. We rejected the simulated datasets we found |
| A complaint is not a flood | It is a proxy, and we tested it: the busiest complaint days are 19 May 2025, 22 Oct 2024 and 5 Sep 2022, all major floods. New York studies use 311 flooding complaints the same way |
| Do active wards just complain more? | Reporting is uneven. We state it as a limit and also test on news events that do not depend on complaints |
| Is that enough data for a GNN? | Semi-supervised node classification works with few labels: 140 of 2,708 in the original GCN paper. We have 372, and about 388,000 ward-days for Stage 2 |
| What do you add over a rain rule? | Rain tells you the day, not the place. On flood days the rain rule ranks wards at chance (0.46); our baseline reaches 0.72 |
| How do you avoid inflated accuracy? | Whole zones and whole years are held out |
| Limits? | Rain data is coarse and smooths bursts. Complaints are ward-level and stop in June 2025. The 30 m elevation model cannot see underpass dips |

## Limits of the label data

- A complaint is a report of standing water, not a measured flood, and names a ward, not a street.
- The export's time of day is unreliable (hours 1 to 12, no AM/PM); only the date is used.
- The flood points are recorded locations, not a complete flood history.
- OpenCity is a third-party host of government records. Cite it as "BBMP and KSRSAC records, accessed
  via OpenCity (data.opencity.in), public domain, downloaded 11 November 2026".

## References

- Kipf and Welling, Semi-Supervised Classification with Graph Convolutional Networks: https://arxiv.org/abs/1609.02907
- Bentivoglio et al. (2023), Rapid spatio-temporal flood modelling via hydraulics-based graph neural networks: https://hess.copernicus.org/articles/27/4227/2023/
- Agonafir et al. (2022), Understanding New York City street flooding through 311 complaints: https://www.sciencedirect.com/science/article/abs/pii/S0022169421013500
- Balachandar et al. (2025), Urban Incident Prediction with Graph Neural Networks: https://arxiv.org/abs/2506.08740
- pkjx29/bengaluru-flood-risk: https://github.com/pkjx29/bengaluru-flood-risk

Read the full papers before citing details; the last three were read as abstracts or summaries only.
