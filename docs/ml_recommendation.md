# Do we need ML or a GNN? Our recommendation

*29 October 2026*

Drop the ST-GNN from the plan, keep our physics-based model with light statistical calibration, and spend
our effort on the site visits and the phone-in-the-car demo.

## Why a GNN doesn't fit

We have 24 recorded floods. A graph neural network learns patterns from many examples, so with 24 it would
just memorise them. The GNN papers in our deck train on thousands of simulated floods or dense sensor
networks, which Bengaluru doesn't have. If we keep it, an evaluator will ask "how many training samples?"
and we have no good answer.

The real bottleneck is not site visits. Site visits give us **features** (facts about a place). What we are
short of is **labels** (records of floods).

| | What it is | Where it comes from | How many we have |
| --- | --- | --- | --- |
| Features | Facts about a place: drain size, silt, catchment area, rain | DEM, OpenStreetMap, site visits, forecasts | Plenty |
| Labels | "Did this hotspot flood on this day?" | News, residents, BBMP and traffic police records | 24, the bottleneck |

Even 10 inspected hotspots over 1,100 days give 11,000 samples, but only about 24 are floods. With hard
work collecting records we might reach a few hundred. That is enough for a simple model, never for a GNN.

## What we use instead

Our model is physics-based, so it needs very few labels. Each hotspot gets a flood threshold from
rain × catchment area (from the DEM) against drain capacity (from site visits). The physics does the
heavy lifting.

The labels are used only for **calibration**: tuning 2–3 numbers such as the rain correction factor and
the typical drain blockage. A one- or two-variable logistic regression then turns "rain ÷ threshold" into a
flood probability, for example "70% chance Silk Board floods tonight". That is still ML, it is defensible
with 24–100 labels, and it is standard practice in data-scarce flood work.

One line for the slides: *"Bengaluru doesn't have the data for deep learning, so we use physics plus field
measurements with light statistical calibration, and we validate it honestly."*

## Where ML can honestly help

If evaluators want ML, we put it where data actually exists. Text mining is the best fit because it grows
the labels we are missing.

| Use | What it does | Why it fits |
| --- | --- | --- |
| Text mining of flood reports (recommended) | A language model scans thousands of tweets and news posts and extracts "place + date + flooded" | ML creates the labels we lack |
| Photo-based flood detection | A pretrained image model classifies citizen photos as waterlogged or not | Fits the citizen report form |
| Rain bias correction | Learns the forecast-to-gauge correction | Needs KSNDMC gauge data |

## Next steps

- [ ] Drop ST-GNN from the slides and replace it with "physics-informed thresholds + logistic
      calibration", with the one-line reason (24 labels)
- [ ] Decide whether to add text mining of flood reports as our honest ML component
- [ ] Pick the 6–10 hotspots we will inspect, mixing underpasses and low-lying junctions
- [ ] Do the site visits: drain size, silt, underpass dip depth, GPS of the low point, resident interviews
      (each dated flood a resident recalls is a new label)
- [ ] Plan and rehearse the phone-in-the-car demo on a route past 2–3 of our hotspots
