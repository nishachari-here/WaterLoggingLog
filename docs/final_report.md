# Final report: Bengaluru waterlogging study

## Rain source and spatial resolution

The regenerated table uses Open-Meteo Historical Forecast API, explicitly pinned to
`ecmwf_ifs025` at the 0.25 degree grid. The API returned only two grid cells for all
12 hotspots: `(13.0, 77.5)` and `(13.0, 77.75)`. The old unpinned cache is preserved
under `data/raw/rain_cache_old_unpinned_2026-11-05/`; the pinned cache metadata records
the model, grid, fetch date, and returned coordinates.

The fetch was not a no-op. For example, the old cache gives Silk Board 13.7 mm on
2022-08-03 and the pinned cache gives 0.0 mm. Rain source choice materially changes
the headline metrics, so the old and new numbers must not be mixed.

## Labels and validation

The label table still contains 17,520 hotspot-days, 24 positive labels, and 13
documented storm dates. The labels come from the event table; changing the rain
source does not change those counts. The new LOHO results are:

| Score | AUC | AP |
|---|---:|---:|
| Rain peak | 0.591 | 0.0039 |
| Physics ratio | 0.598 | 0.0044 |
| Rain logistic | 0.646 | 0.0053 |
| Rain + physics logistic | 0.572 | 0.0074 |
| Terrain only | 0.490 | 0.0019 |

The old baseline commit had rain peak AUC 0.773, physics ratio 0.782, rain logistic
0.763, and rain + physics logistic 0.780. This is a large source sensitivity result.

The date-level spatial check gives mean physics AUC 0.552 with a 13-date bootstrap
95% interval of 0.477–0.656. Shuffling the drain thresholds within each date gives
null mean 0.455, null 95% interval 0.360–0.551, and two-sided p=0.470. This does not
support a hotspot-level skill claim. With two coarse cells, the rain input cannot
resolve ward-scale differences.

The GNN result is AUC 0.553 under LOHO and event-date holdout AUC 0.365. Its date
bootstrap interval is 0.333–0.741. It does not establish generalizable hotspot
prediction with this sample.

## Model and data checks

The rain-to-gauge correction remains based on the five existing comparison rows,
whose ratios have median about 4.8. It should be re-estimated when KSNDMC gauge data
arrive; carrying 4.8 forward is only a provisional calibration. No hotspot snap
distance exceeds 200 m; the largest are Kogilu 66.3 m, Manyata 59.7 m, and
Kadubeesanahalli 67.3 m. Kogilu's threshold remains the lead-time override value
28.4 mm/h and should be checked against field measurements.

## Presentation recommendation

Present the label table, the honest LOHO and date-held-out validation, the two-cell
rain-resolution finding, the drain-graph ranking explicitly labelled as placeholder
capacity based, and the working dashboard demo. The central conclusion should be:

> The physics and graph prototype are useful for organizing field work, but the
> current rain source has only two cells across the 12 hotspots, so hotspot-level
> prediction cannot be validated from these data.

Make the KSNDMC gauge request the next data step. A single dry-weather drain survey
can be shown as a calibration proof point, but it should not be presented as a
validated citywide threshold.
