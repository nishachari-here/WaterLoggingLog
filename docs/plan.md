# Project plan: answers to the open questions

## 1. "It's common sense, locals already know where it floods"

The evaluators are right that *where* is known. Even our own deck lists the hotspots. So stop
selling "where". Sell the three things a local can't do:

1. **When and how much.** Each hotspot gets its own critical rain intensity (for example "Silk Board
   floods above ~35 mm/h, KR Circle above ~50 mm/h"), set from measured drain capacity and the
   DEM catchment. A local knows "it floods when it rains a lot". They don't know whether today's
   forecast of 28 mm/h is enough.
2. **What to do about it.** Rerouting (section 2) turns the warning into an action. That helps newcomers,
   cab drivers, delivery riders and ambulances, who don't have local knowledge.
3. **Which drain to clear first.** The blockage what-if analysis gives BBMP a maintenance priority list.
   No local has this.

One-line answer for the next review: *"Locals know where. We tell you whether it will flood today,
how to avoid it, and which drain fixes it."*

## 2. Alternative-route suggestion (no Google Maps needed)

Google is not the right tool anyway. The Routes API cannot be told to "avoid this polygon", which
is exactly what we need. Open-source routing on OpenStreetMap data does support it, for free.

**Pipeline**

```
Open-Meteo hourly rain forecast (free, no key)
  -> per-hotspot critical intensity  -> flooded hotspots now / next 6 h
  -> flood polygons (hotspot buffer, sized from field-measured extent)
  -> router with those polygons blocked -> safe route + "your usual route crosses X"
  -> Leaflet map on OSM tiles
```

**Router options, simplest first**

| Option | Cost | Effort | Use for |
|---|---|---|---|
| OSMnx + NetworkX in Python | free, offline | low | **Phase-I demo.** Download Bengaluru drive network once, set each edge's weight to length × penalty (∞ inside a flooded polygon), run shortest path. Full control, works without internet. |
| openrouteservice API | free key, ~2,000 routes/day | very low | Hosted option. `options.avoid_polygons` takes a GeoJSON polygon directly. |
| Self-hosted GraphHopper or Valhalla | free | medium (Docker) | Fast, production-like. Both support blocked areas per request. |

Recommendation: build the demo with OSMnx/NetworkX (it's already in our tool list), and mention ORS or
GraphHopper as the deployment path. The demo then shows the forecast slider pushing hotspots red,
the red zones blocking roads, and the route redrawing around them. A good demo trip is Koramangala to
Marathahalli, which has to pass Silk Board, Bellandur or Kadubeesanahalli.

Honest limit to state: a road segment is blocked by proximity to a predicted hotspot, not by
simulated water spreading along the street.

## 3. Site visit: what to measure and how it is used

Visit 5–10 hotspots. Mix valley-floor spots (Silk Board, Madiwala) with underpasses (HAL, Kadubeesanahalli,
KR Circle), because the DEM handles the first group but misses the second. Measure from the kerb only,
never inside water. Use `data/field/field_log_template.csv`, one row per drain or inlet.

| Measure | How (cheap kit) | Goes into |
|---|---|---|
| GPS location of the actual low point | phone (GPS Map Camera / Google Maps) | replaces approx coords in `hotspots.csv`; fixes DEM snapping |
| Drain width, depth, **silt depth** | 5 m tape and a marked pole poked to the silt surface | Manning capacity → **critical rain intensity** (`pipeline/capacity.py`) |
| Lining (concrete / earthen) and garbage level | photo and 0–3 score | Manning roughness `n` |
| Drain bed slope | levels at two points 10–20 m apart (water-tube level or phone clinometer) | `S` in Manning |
| Inlets total vs blocked, grating condition | count and photos | blockage factor on the drain graph (step 3 what-ifs) |
| **Underpass dip depth and length** | laser distance meter or tape from the railing; measure the drop from road to lowest point | ponding volume. **This fixes the 30 m DEM blind spot.** |
| Kerb height | tape | depth at which water reaches footpaths and shops |
| High-water marks on walls and shutters | tape | observed past flood depth (a label) |
| Short interviews with shopkeepers, security guards and autos | 5 fixed questions: how often, how deep, how long to clear, after how much rain, worst year | labels and first-guess thresholds for validation |
| After a real rain: standing depth, extent, time to drain | tape, photos with timestamps; match with KSNDMC or GPM rain for that hour | **validation test set**: was our prediction right? |
| Where the drain goes (lake, rajakaluve, culvert) | follow it 50–100 m, check OSM | edges of the drain graph |

**How it feeds the model**

1. Capacity: width, depth, silt, slope and roughness go into Manning to give `Q_cap`.
2. Threshold: `i_crit = Q_cap / (0.278 · C · A)`, where `A` is the local catchment from the DEM. The example
   in `capacity.py` shows 0.4 m of silt cutting the threshold from 39 to 9 mm/h. That single number is
   the strongest slide for "why drain condition matters".
3. Blockage factor: blocked inlets and silt fraction become a 0–1 capacity multiplier on each graph node.
   That gives the "clear these first" ranking.
4. Underpass dip volume: `time to danger depth ≈ dip volume / (inflow − drain capacity)` gives
   lead time for the alert.
5. Validation: interviews, high-water marks and post-rain observations give an independent test set
   that the model never trained on.

Kit cost is under ₹1,500: tape, a marked bamboo pole, a water-tube level, a cheap laser meter (optional),
a phone and a printed log sheet.

## 4. Build order (revised)

| # | Piece | Status |
|---|---|---|
| 1 | Terrain layer: DEM, flow, HAND, TWI, TPI, catchments, terrain-only baseline | **done** (`run_terrain.py`) |
| 2 | Field log template and Manning/rational bridge | **done** (template plus `capacity.py`) |
| 3 | Fetch OSM roads, drains and lakes; drain graph; blockage what-ifs; "clear these first" | **done** (`run_network.py`) |
| 4 | Rain feed: Open-Meteo live forecast, plus a 2022–2025 backtest against news-documented floods | **done** (`run_backtest.py`, `run_leadtime.py`, [backtest.md](backtest.md)). Main open issue: about 2 false-alarm days per hotspot per month. |
| 5 | Rerouting (OSMnx/NetworkX) and Streamlit dashboard | **done** (`app.py`) |
| 6 | Replace placeholder capacities with field logs | after site visits |
| 7 | Labelled flood events (news, field), rainfall-threshold baseline, then ML model with spatial CV | after 4 and 6 |

Suggested change from the deck: drop ST-GNNs from the Phase-I scope. With about 12 labelled hotspots there is
nothing for a graph neural network to learn from. Keep it as future work, and spend the time on rerouting,
which the evaluators actually asked for.
