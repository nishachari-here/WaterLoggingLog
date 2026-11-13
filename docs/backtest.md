# Backtest: 2022–2025 monsoons

`run_backtest.py` compares five methods on every hotspot-day from April to December, 2022–2025
(18 hotspots × 1,100 days = 19,800 hotspot-days), against flood days documented in the news.

## Data

- **Labels**: `data/events/flood_events.csv` has 24 hotspot-days on 13 dates. Each row is a dated news report that
  names the hotspot as waterlogged and links to the source. Traffic-only mentions are excluded.
  Each row is marked high or medium confidence.
- **Rain**: Open-Meteo historical forecast, hourly, at each hotspot (cached in `data/raw/rain/`).
  The window for day D runs from D-1 12:00 to D 23:00, so overnight storms are counted.
- **Thresholds**: drain-graph `i_crit` at 20% blockage. These are still **placeholder** capacities.

## Rain source and reproducibility (checked 12 November 2026)

The official backtest source is the **0.25° Open-Meteo historical-forecast cache**
(`data/raw/rain/`), because it is closest to the model family used by the live app. The cache now covers
all 18 hotspots. `run_backtest.py` fills missing hotspot rows incrementally and preserves existing cache
rows. The metrics below were regenerated on 12 November 2026 from this source.

The earlier headline table used the **0.1° Open-Meteo archive** (`data/rain/rain_hourly.csv`). On that
source, rain-peak and drain-graph AUC were 0.861 and 0.841 for 12 hotspots, and 0.863 and 0.859 for all
18. On the official forecast cache, they are now 0.606 and 0.631 for all 18. The earlier 0.556 figure
also came from a different source/run. These values are not a before/after comparison and do not indicate
a drain-graph regression.

## Results

| Method | AUC (95% CI) | Recall at 5% false alarms | Spatial AUC on flood days |
|---|---|---|---|
| Rain rule, peak hour | 0.606 (0.41–0.80) | 0.083 | 0.465 |
| Rain rule, 36 h total | 0.616 (0.41–0.82) | 0.375 | 0.425 |
| Terrain only (static map) | 0.590 (0.43–0.71) | 0.000 | 0.537 |
| Terrain × rain | 0.607 (0.41–0.80) | 0.250 | 0.504 |
| **Drain-graph model** | **0.631 (0.44–0.82)** | 0.208 | **0.555** |

The confidence intervals come from resampling whole days, because hotspots on the same day share rain.
Using only high-confidence labels gives AUCs of 0.576, 0.588, 0.642, 0.581, and 0.602 in table order
(`outputs/backtest_metrics.csv`). The sample is small: 24 documented flood hotspot-days across 13 dates.

## What it means

1. **Rain helps decide *which day*.** Rain-based methods score about 0.61 AUC on this forecast cache. Most of the skill is knowing
   that it rained hard, which matches what the evaluators said.
2. **Terrain alone has limited value for *when*.** A static map scores AUC 0.59.
3. **The drain-graph model is slightly ahead but not significantly.** Its CI overlaps the rain rule's. On
   documented flood days it scores 0.555 at picking *which hotspots* flood, but
   that is 13 days of evidence. With placeholder capacities, this is the expected result. The claim to
   test after the field visits is whether measured capacities lift the spatial AUC clearly above 0.5.
4. **Rain bias estimates need more observations.** The five documented gauge comparisons include three
   dates where the forecast returned zero, making the current median ratio (860) dominated by the 0.1 mm
   denominator floor. Do not use that ratio as a calibration factor. Gauge data from KSNDMC would provide
   a stronger basis for calibrating the live forecast.
5. **Recall at 5% false alarms is low (0.08–0.38).** Many floods happen under storms the model rain
   barely sees (2023-06-13: 86–93 mm reported, 7 mm modelled).

## Known biases (say these before anyone asks)

- **Unreported is not dry.** Negatives include floods nobody wrote about.
- **Media attention.** Silk Board has 5 labels and MG Road has 0. A model that ranks famous spots high gets
  rewarded partly for fame.
- **Small sample.** With 24 positives on 13 days, the confidence intervals are wide. Report them, not just
  the point estimates.
- **Lead time is tested on a smaller set.** See the next section: only 2024–2025, with 12 floods on 7 dates.

## Lead time: how early could we have warned?

`run_leadtime.py` repeats the test on forecasts issued 0, 1, 2 and 3 days before each hour (Open-Meteo
Previous Runs API, available from February 2024). The "alerts" view applies exactly what the dashboard
does: forecast peak × 4.8 bias factor against each hotspot's threshold.

**Skill holds for up to 3 days** (`leadtime_skill.csv`). AUC is 0.80–0.93 at every lead, with no clear
decline. With only 7 flood dates, the confidence intervals (about ±0.15) are too wide to tell the leads apart.

**What the dashboard would have shown** (`leadtime_alerts.csv`, 12 floods):

| Alert | Same day | 1 day ahead | 2 days ahead | 3 days ahead | False-alarm days per hotspot per month |
|---|---|---|---|---|---|
| Drain-graph red | 7 | 3 | 5 | 3 | 1.3–2.0 |
| Drain-graph red or amber | 9 | 4 | 7 | 5 | 2.2–3.3 |
| City-wide 40 mm/h rule | 0 | 3 | 5 | 0 | 0.3–0.9 |
| Red in any of the last 3 runs | **10** | – | – | – | 3.6 |

**Per flood** (`leadtime_events.csv`): 7 of 12 floods showed red in some forecast 1–3 days ahead, but only
2 stayed red in every run from then until the day: Silk Board and Madiwala on 19 May 2025, red 3 days
ahead. Forecasts flip-flop between runs. Silk Board on 12 Aug 2024 was red 2 days out and nearly dry on the day.
Two floods were never red (Hebbal 12 Aug 2024, Kogilu 16 Oct 2024).

**What to say:**
- The system gives **useful same-day warnings** (7 of 12 red, 10 of 12 with the multi-run rule) where a
  fixed 40 mm/h rule on the same data gives none.
- **False alarms are the weak point.** About 2 red days per hotspot per wet-season month is too many for
  people to trust. Field-measured capacities (higher thresholds where drains are clear) and gauge rain
  (no ×4.8 guesswork) are the two levers. Report this as the main thing Phase-II must fix.
- **1–3 days ahead is a heads-up, not a warning.** It's right sometimes, and forecasts change between runs.
  The dashboard now does this: a "watch" for 1–3 days out and a "red alert" on the day.

## Improving the labels

The field-visit interviews (how often, which months, which storms) and BBMP or traffic police archives can
add labels. Add rows to `flood_events.csv` with a source, then rerun. Everything downstream updates.
