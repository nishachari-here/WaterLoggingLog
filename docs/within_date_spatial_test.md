# Within-date spatial skill check

Run with `.venv\Scripts\python within_date_test.py`. The script resamples the 13
documented flood dates as blocks (2,000 bootstrap replicates) and permutes the 12
hotspot thresholds independently within each date (2,000 permutations). It scores
only dates with both positive and negative hotspot labels. The threshold permutation
preserves each date's rainfall and labels while removing the assignment of drain
thresholds to locations.

Results from the current label table:

| Score | Mean date AUC | 95% date bootstrap CI |
|---|---:|---:|
| Rain peak / drain threshold (`physics_ratio`) | 0.517 | 0.370–0.656 |
| Saved OOF `logit_rain_physics` | 0.480 | 0.293–0.677 |

For the physics score, the within-date threshold shuffle has null mean 0.460 and
95% null interval 0.361–0.557. The two-sided permutation p-value against AUC 0.5
is 0.800. These data do not support a hotspot-level skill claim for the threshold
assignment. Only 13 dates contribute, so the intervals are broad.

The earlier `outputs/within_date_spatial_test.csv` reported 0.598 for
`logit_rain_physics`; that value does not reproduce from the current saved OOF
predictions under the date-level spatial AUC calculation (which gives 0.480), or
from pooled AUC on the event dates (0.544). Treat 0.598 as unreconciled until its
input predictions and aggregation code are recovered. A threshold permutation
applies directly to `physics_ratio`; the logistic score is a fitted model output,
not a threshold score, so its shuffle would require refitting each leave-one-hotspot
fold under every permuted threshold assignment.

## Rain input resolution

`run_labels.py` calls the Open-Meteo Historical Forecast API and does not pass a
`models` parameter, so it previously used Open-Meteo's default `best_match`.
Historical label and backtest fetches now pin `ecmwf_ifs025` (ECMWF IFS 0.25°,
about 25 km). The old ignored cache cannot be attributed to a model, so regenerate
it before rerunning metrics; the current label table still reflects the old fetch.
This grid cannot establish ward-scale rainfall differences by itself. See the
[Historical Forecast API documentation](https://open-meteo.com/en/docs/historical-forecast-api).

KSNDMC describes telemetry gauges at Gram Panchayat scale (about 25 km² statewide),
with rainfall recorded every 15 minutes. Public references also describe Bengaluru
Taluk/Hobli datasets, but this audit did not establish open ward-level historical
measurements for the 2022–2025 event dates. Confirm station locations, access and
coverage before using KSNDMC as a replacement. Sources: [KSNDMC network overview](https://ksndmc.org/Rainfall_Info.aspx/About/Introduction),
[Bengaluru rainfall dataset listing](https://www.data.opencity.in/dataset/?_organization_limit=0&groups=bengaluru&organization=ksndmc).
