# Backtest: 2022–2025 monsoons

`run_backtest.py` compares five methods on every hotspot-day from April to December, 2022–2025
(12 hotspots × 1,100 days = 13,200 hotspot-days), against flood days documented in the news.

## Data

- **Labels**: `data/events/flood_events.csv` has 24 hotspot-days on 13 dates. Each row is a dated news report that
  names the hotspot as waterlogged and links to the source. Traffic-only mentions are excluded.
  Each row is marked high or medium confidence.
- **Rain**: Open-Meteo historical forecast, hourly, at each hotspot (cached in `data/raw/rain/`).
  The window for day D runs from D-1 12:00 to D 23:00, so overnight storms are counted.
- **Thresholds**: drain-graph `i_crit` at 20% blockage. These are still **placeholder** capacities.

## Results

| Method | AUC (95% CI) | Recall at 5% false alarms | Spatial AUC on flood days |
|---|---|---|---|
| Rain rule, peak hour | 0.82 (0.70–0.91) | 0.29 | 0.45 |
| Rain rule, 36 h total | 0.83 (0.72–0.91) | 0.46 | 0.34 |
| Terrain only (static map) | 0.49 (0.31–0.63) | 0.00 | 0.42 |
| Terrain × rain | 0.82 (0.68–0.90) | 0.21 | 0.38 |
| **Drain-graph model** | **0.84 (0.71–0.92)** | 0.33 | **0.52** |

The confidence intervals come from resampling whole days, because hotspots on the same day share rain.
Using only high-confidence labels raises every AUC by 0.01–0.06. The drain-graph model stays on top
(0.86), and the three rain-based baselines stay within 0.01 of each other (`backtest_metrics.csv`).

## What it means

1. **Rain decides *which day*.** Every rain-based method scores about 0.82 AUC. Most of the skill is knowing
   that it rained hard, which matches what the evaluators said.
2. **Terrain alone is useless for *when*.** A static map gives the same answer every day (AUC 0.49).
3. **The drain-graph model is slightly ahead but not significantly.** Its CI overlaps the rain rule's. On
   documented flood days it is the only method above chance at picking *which hotspots* flood (0.52), but
   that is 13 days of evidence. With placeholder capacities, this is the expected result. The claim to
   test after the field visits is whether measured capacities lift the spatial AUC clearly above 0.5.
4. **Gridded rain is about 5× too weak** (`backtest_rain_bias.csv`). Reported gauge totals were 4–13×
   Open-Meteo's (median 4.8). That is why a fixed "40 mm/h" rule never fires on this data, and why the
   dashboard now scales the live forecast by the median ratio. Gauge data from KSNDMC would remove most of
   this error, so it is worth requesting.
5. **Recall at 5% false alarms is low (0.3–0.46).** Many floods happen under storms the model rain
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
