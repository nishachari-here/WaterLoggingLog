## Waterlogging Early-Warning for Bengaluru Flood Hotspots

Predicting which hotspots flood for a given rainfall, and guiding commuters

around them in real time.

SDG 9: Industry, Innovation and Infrastructure

Bengaluru's stormwater drains (blue) and the 388 flood-vulnerable locations recorded by BBMP (orange). Drawn from the project data.

GUIDE

Team member

USN

DEPARTMENT

INSTITUTION

RV College of Engineering, Bengaluru

SEMESTER AND DATE

5th Semester · November 2026


## Introduction

Bengaluru does not flood at random. The same underpasses, junctions and low-lying layouts go under water

every monsoon, and the city already knows where most of them are. What it cannot yet say is which of them will flood for today's rain, and how a commuter should avoid them.

Waterlogging in the city comes from three things acting together. Terrain decides where water collects. Drains decide

how fast it leaves, and many are silted, blocked by garbage, undersized or encroached. Rainfall arrives in short, intense bursts that overwhelm the network within an hour. The result is stalled traffic, damaged property, and in the worst cases loss of life, as in the KR Circle underpass in May 2023.

The scale of the problem is visible in public records. The civic body and the state remote-sensing centre have mapped

hundreds of flood-vulnerable locations, and residents file thousands of complaints about standing water. Figure 1 shows both. The recorded flood points cluster along the valleys that carry the city's primary drains, while the complaints concentrate in the fast-growing outer wards such as Bellandur and Horamavu.

## (b) Where residents report it

## (a) Where BBMP says it floods

*Figure 1. Study area: the 198 wards of Bengaluru. (a) Flood-vulnerable locations and primary stormwater drains recorded by BBMP and KSRSAC. (b) "Water stagnation" complaints per ward, February 2020 to June 2025. Source: OpenCity portal; maps drawn by the team.*

388

*8,274*

*339*

198

official flood-vulnerable locations mapped across the city

*dated flood complaints from*

*flood complaints on a single day, 19 May 2025*

wards covered by the study

*residents, 2020 to mid-2025*

## What this project builds

We are building a low-cost early-warning system that needs no new sensors. It combines open elevation data, the

drain and road networks, rainfall forecasts and real flood records to estimate a Low, Medium or High risk level for each hotspot. A phone-friendly map then warns the user when a hotspot on their route is at risk and suggests an alternative route.

## Relevance to SDG 9

Drains, culverts and underpasses are infrastructure. Target 9.1 asks for reliable and resilient infrastructure, and this

project shows where the existing network fails under rain and which drains matter most, without proposing new construction. It also supports target 9.5 by using open data and open-source software, and contributes to SDG 11 (sustainable cities) and SDG 13 (climate action).


## Problem Definition

Problem statement. Given the observed or forecast rainfall, estimate which flood hotspots in Bengaluru are

likely to waterlog, with enough lead time to warn people, and suggest a route that avoids them.

People who know the city can often guess where water collects. That does not help a newcomer, a delivery rider or an

ambulance driver, and it does not answer the harder questions: will it flood for this much rain, when, and what should I do about it? Figure 2 shows why prediction is possible: flood reports arrive in sharp spikes on a few days, and those days follow heavy rain.

*Figure 2. Flood complaints per day across Bengaluru. The three largest spikes match the major floods of September 2022, October 2024 and May 2025. Source: BBMP grievance records via OpenCity.*

## Why existing approaches fall short

| Existing approach Limitation How this project responds City-wide rainfall alerts One threshold for the whole city. They say a wet A risk level for each hotspot day is coming but not which places will flood. Static flood-prone maps They show where water collects, but give the Risk that changes with the forecast same answer every day, whatever the rain. Hydrodynamic simulators They need pipe sizes and cross-sections for every A light model built on open data drain, which Bengaluru does not publish. |
| --- |
| Water-level sensors Accurate, but they react after water has risen and Forecast-based, no new hardware cover few points. Navigation apps They react to traffic that has already built up. Rerouting before the user arrives |

## Objectives

Main objective. To build and test an early-warning system that predicts the waterlogging risk of Bengaluru's flood

hotspots for a given rainfall and guides road users around them.

- 1. Map terrain vulnerability from a digital elevation model: flow paths, depressions and height above the nearest drain.

- 2. Model the drain network as a graph, find the bottleneck below each hotspot, and test blocked-culvert scenarios.

- 3. Train a prediction model on real flood records: where from official flood points, when from dated complaints and rainfall, comparing a graph neural network with simpler models.

- 4. Validate honestly on years and zones the model has not seen, against a rainfall-only rule.

- 5. Deliver a usable tool: a map app that shows each hotspot's risk level, raises alerts from the live forecast and suggests a flood-aware route.


## Methodology

The method has two learning stages built on one physical base. Stage 1 learns where the city floods. Stage 2

learns when. Their outputs combine into a risk level per hotspot, which drives the alerts and the routing.

*Figure 3. Overall method. Four data sources feed two models. Their combined output is one risk level per hotspot, which the app uses for*

*alerts and rerouting. News-reported floods are kept out of training and used only for testing.*

## 4.1 Data collection

All data is open and free. Flood labels come from government records published on the OpenCity urban data portal;

nothing is simulated or generated.

| Dataset | Source Size Used for |   |
| --- | --- | --- |
| Flood-vulnerable locations | BBMP, KSRSAC (via 388 points in 3 layers Stage 1 labels OpenCity) |   |
| Citizen grievances | BBMP (via OpenCity) 766,646 complaints, of Stage 2 labels; drain complaints as which 8,274 are "water a blockage indicator stagnation" |   |
| Stormwater drain maps | BBMP, 2022 767 km of primary and Drain features |   |
| Elevation model | secondary drains Copernicus GLO-30 30 m grid over the city Terrain features, flow paths |   |
| Roads, lakes, waterways | OpenStreetMap 9,372 junctions on arterial Routing and network graph |   |
| Rainfall, soil moisture | roads Open-Meteo Hourly, 2020 to present, Model input and live alerts |   |
| News-reported floods | plus forecast Compiled by the team 24 hotspot-days with Independent test set article links |   |

Checks made on the data. Every file was opened and counted before use. The complaints name wards by spellings

that differ from the ward map, so all 198 names were matched one to one, 71 of them through checked spelling variants. Complaints carry a date and a ward but no street address, and their time of day is unreliable, so only the date is used. Flood points recorded twice at the same place were merged.


## 4.2 Terrain and drain network (physical base)

The elevation model is cleaned by filling pits and depressions. Water is then routed downhill cell by cell (the D8

method) to give, for every 30 m cell, the area that drains through it. From this we derive the features that describe how flood-prone the ground is: depression depth, slope, topographic wetness index, height above the nearest drainage line, and how low a spot sits relative to its surroundings.

Cells with a large upstream area form drainage lines. These are joined into a directed graph of about 3,000 segments,

and each segment is tagged with the mapped drains, lakes and road crossings (culverts) along it. This graph gives each hotspot a path to its outlet, the bottleneck segment on that path, and a way to simulate a blocked culvert. A physics estimate compares runoff from the rational method (Q = C·i·A) with drain capacity to give each hotspot a rain threshold. In the learning stages this estimate serves as an input feature and as a baseline.

## 4.3 Stage 1: where it floods

- Sample: a location in the city (a node of the combined road and drain graph).

- Label: 1 if it lies at an official flood point. Other locations are unlabelled, not proven safe.

- Features: the terrain measures above, distance to a mapped drain, drain density, distance to lakes, road class.

- Models: logistic regression, Random Forest, and a GraphSAGE graph neural network that also uses each node's neighbours.

Why a graph neural network can be trained here. Stage 1 is semi-supervised node classification: a few labelled

nodes, many unlabelled ones, and a graph linking them. The method is known to work with few labels; the original graph convolutional network paper trained on 140 labelled nodes out of 2,708. We have several hundred labelled locations. We do not train on a hand-written risk formula, because a model can only learn to copy such a formula and could not then be checked against real floods.

## 4.4 Stage 2: when it floods

- Sample: one ward on one day (387,882 ward-days).

- Label: 1 if the ward has a flood complaint that day (6,029 cases).

- Features: rain today and over the previous 1, 3 and 7 days, the peak hour, ward terrain, number of official flood points, and drain complaints in the last 30 days.

- Models: a rainfall rule, logistic regression, gradient boosting, and a GNN with wards as nodes.

## 4.5 Risk level, alerts and routing

Each day, a hotspot takes its ward's probability from Stage 2 and is moved up or down by its own Stage 1 score. The

result is banded into Low, Medium and High. High-risk hotspots become no-go zones on the road network and Medium ones are penalised. A shortest-path search (Dijkstra's algorithm) then returns the usual route and a flood- aware route. The service repeats this whenever a new forecast arrives, and raises a "watch" when a hotspot is expected to reach High within three days.

## 4.6 Validation design

Stage 2 is split by time: the model is always tested on a later period it has never seen.

Stage 1 is split by place: each of the 8 BBMP zones is held out in turn and predicted by a model

trained on the other 7. The test period is used once, after all choices are fixed on the tuning year.

Figure 4. How data is split. Random splits are avoided because neighbouring places and adjacent days resemble each other and would inflate

the scores.

Every model is compared with the rainfall-only rule and with the physics estimate on the same split, using the

measures listed in Section 6. The baseline results in Section 7 were produced before the tuning year was separated, so they use 2020 to 2023 for training.


## Project Execution

The project is executed in six phases. Four are complete, one is in progress and one is planned. All code and

data are kept in a shared Git repository so that every result can be reproduced.

*Field visits to selected hotspots run alongside phases 5 and 6 to supply drain measurements for a case study.*

*Figure 5. Project phases and current status.*

| # Phase |   | Work carried out or planned | Output | Status |
| --- | --- | --- | --- | --- |
| 1 | Problem study | Literature review, SDG mapping, shortlisting of | Phase-I presentation, hotspot | Complete |
|   |   | recurring hotspots, review feedback from | list |   |
|   |   | evaluators (add route guidance, justify the |   |   |
|   |   | model). |   |   |
| 2 | Terrain and drain | Downloaded and processed the elevation model; | Terrain layers, drain graph, | Complete |
|   | network | computed flow paths and terrain features; built | maps |   |
|   |   | the directed drain graph with culverts and lakes. |   |   |
| 3 | Physics model, | Per-hotspot rain thresholds, blocked-culvert | Working web application | Complete |
|   | routing, dashboard | scenarios, flood-aware routing on the road |   |   |
|   |   | graph, web dashboard with live forecast and a |   |   |
|   |   | "watch" level. |   |   |
| 4 | Real flood data, | Located and verified government flood records; | Label datasets, baseline | Complete |
|   | baselines | matched all 198 ward names; built the label | results (Section 7) |   |
|   |   | tables and rain history; trained baseline models |   |   |
|   |   | for both stages. |   |   |
| 5 GNN models and |   | Attach labels to the combined road and drain | Model comparison table, | In progress |
|   | comparison | graph; add drain and built-up features; train | chosen model |   |
|   |   | GraphSAGE (Stage 1) and the ward-graph GNN |   |   |
|   |   | (Stage 2); compare with baselines on identical |   |   |
|   |   | splits. |   |   |
| 6 | Phone demo and final | Show risk levels in the app; phone access with | Demonstration, final report | Planned |
|   | validation | GPS; replay of the 19 May 2025 storm; hotspot- |   |   |
|   |   | level test on news-reported floods; final report. |   |   |

## Team organisation

## Experiential learning cycle

The work follows Kolb's cycle. Experience: observing how

and where the city floods, through records and site visits. Reflection: the first review showed that naming hotspots was not enough, and the first model plan had no ground truth. Conceptualisation: a two-stage design trained on real records. Application: testing on unseen years and demonstrating on a real storm.

| Role | Responsibility |
| --- | --- |
| Data | Source files, ward matching, rain history, |
|   | label tables |
| Stage 1 model | Where-it-floods model and GraphSAGE |
| Stage 2 model | Ward-day model, baselines, validation |
|   | figures |
| Application | Risk levels, routing, phone demo, replay |
|   | mode |
| Report and review | Documentation, slides, checking every |
|   | reported number |


## Tools and Techniques Used

The system is written in Python and uses only open-source libraries and open data. It runs on an ordinary

laptop, which keeps the cost close to zero.

## Processing and models

Terrain layers

Drain and road graphs Label and rain tables Stage 1 and Stage 2

Backtests

Python pipeline

## User's phone

Map of hotspots Low / Medium / High Alerts and watch Suggested route GPS position

Leaflet web app

*Figure 6. System architecture. Data flows left to right; the phone only displays results, so it needs no heavy computation.*

## Software tools

## Techniques

| Technique | What it does in this project |
| --- | --- |
| D8 flow routing and flow | Finds where water travels and how much |
| accumulation | land drains to each point |
| Height above nearest | Scores how easily a spot collects water |
| drainage, wetness index |   |
| Rational method, | Estimates runoff and the capacity of a |
| Manning's equation | measured drain |
| Graph traversal, | Traces each hotspot's drain path, finds |
| bottleneck search, | the limiting segment, and computes |
| Dijkstra's shortest path | routes |
| Logistic regression, | Baseline and tabular prediction models |
| Random Forest, gradient |   |
| boosting |   |
| Graph neural network | Learns from each node and its |
| (GraphSAGE) | neighbours in the network |
| Spatial and temporal | Gives honest accuracy figures with |
| hold-out, bootstrap | uncertainty ranges |

| Purpose | Tools |
| --- | --- |
| Language | Python 3.13 |
| Raster and | rasterio, pysheds, NumPy, SciPy |
| terrain |   |
| Maps and | GeoPandas, Shapely, pyproj |
| geometry |   |
| Networks | OSMnx, NetworkX |
| Machine | scikit-learn; PyTorch Geometric |
| learning | for the GNN (phase 5) |
| Data handling | pandas |
| Web service | FastAPI, Uvicorn |
| Map interface | Leaflet, OpenStreetMap tiles |
| Charts | Matplotlib, Folium |
| Collaboration | Git and GitHub |

## Evaluation measures

| Measure Meaning Why we report it AUC The chance that a flooded case is ranked above a non- Overall ranking skill flooded one. 0.5 is guessing, 1.0 is perfect. Recall at 5% false alarms The share of real flood cases caught when only 5% of What a user would experience quiet cases are allowed to raise an alert. |
| --- |
| Within-day AUC AUC computed across wards on days when ten or more Whether the right places are picked, wards reported flooding. not just the right day Average precision Precision averaged over all alert thresholds. Honest when floods are rare |

Field instruments (case-study visits). A measuring tape and marked pole for drain width, depth and silt, a phone

GPS, a level for slope, and a fixed set of questions for residents. The measurements feed Manning's equation to give a drain's true capacity.


## Partial Results

Phases 1 to 4 are complete. The results below come from the code in the project repository. They are

baseline results: the graph neural network and the additional features of phase 5 will be measured against them.

## 7.1 The flood records are real and track actual floods

Before training on complaints, we checked that they reflect flooding. They do. The three busiest days in five years of

records are 19 May 2025 (339 complaints), 22 October 2024 (236) and 5 September 2022 (221). All three are major floods that newspapers reported independently and that were already in our news-based event list. Daily complaint counts also rise steadily with rainfall from a separate source (rank correlation 0.57 with two-day rain).

## 7.2 Stage 1 baseline: where it floods

Using terrain features only, three models were trained to

separate 372 official flood locations (the 388 points, merged where closer than 100 m) from 4,000 random background locations. Each of the eight zones was held out in turn.

| Model | Mean | Flood points in top 20% of |
| --- | --- | --- |
|   | AUC | area |
| Logistic | 0.68 | 46% |
| regression |   |   |
| Random Forest | 0.68 | 45% |
| Gradient | 0.67 | 47% |
| boosting |   |   |

Reading the result. Terrain alone carries real signal:

*Figure 7. Terrain susceptibility computed from the elevation model (darker is more flood-prone), with official flood points. Grey lines are zone boundaries.*

nearly half of all official flood points fall inside the fifth of the city the model ranks most susceptible. Skill varies by zone, from 0.53 in Dasarahalli to 0.77 in Yelahanka (Random Forest). It is also clearly incomplete. A 30 m elevation model cannot see an underpass or a blocked drain, and the dark bands in Figure 7 follow natural valleys while many flood points lie away from them.

This is the gap phase 5 addresses, by adding mapped-

drain and built-up features and by letting the graph neural network use each location's neighbours. A published open project on the same labels reports 0.775 with a richer feature set, which indicates the headroom available.

## 7.3 Drain network and terrain layers

~3,000

drain segments in the

directed graph built from flow paths

The drain paths traced from the elevation model agree with the city's known drainage. Water from Silk Board and

Madiwala is routed to Agara Lake, Koramangala drains into the K-100 valley channel, and Hebbal drains to Nagawara Lake. This agreement gives confidence in the terrain base on which both learning stages rely.

767 km

9,372

198 / 198

of mapped primary and

road junctions in the routing

ward names matched

secondary drains added from BBMP

network

between complaints and the ward map


## 7.4 Stage 2 baseline: when it floods

Models were trained on 2020 to 2023 and tested on 2024 to June 2025: 106,128 ward-days that the models never

saw, of which 2,223 had a flood complaint.

*Figure 8. Stage 2 on the unseen test period. Grey bars use rainfall only; blue bars add ward features. The right panel is scored only on the 53*

*days when ten or more wards reported flooding.*

| Model | AUC | Recall at 5% false | Within-day |
| --- | --- | --- | --- |
|   |   | alarms | AUC |
| Rule: two-day rain total | 0.73 | 0.26 | 0.46 |
| Rain only, logistic regression 0.73 |   | 0.23 | 0.48 |
| Rain + soil moisture | 0.72 | 0.22 | 0.49 |
| Rain + ward terrain + flood | 0.80 | 0.32 | 0.70 |
| points |   |   |   |
| + drain complaints (30 | 0.80 | 0.33 | 0.72 |
| days) |   |   |   |

Main finding so far. Rainfall tells us

the day but not the place. On flood days a rain-only model ranks wards no better than chance (0.46). Adding ward features raises this to 0.72. This is what the project adds over a rainfall alert.

Two further observations. Soil moisture, suggested as an extra input, adds almost nothing here. And recall is still

modest: at a 5% false-alarm rate the best baseline catches about one flood report in three, partly because the available rainfall data is coarse and smooths out short bursts.

## 7.5 Working application with flood-aware routing

The application works end to end

with the physics-based thresholds; the learned risk levels will replace them in phase 6.

In the scenario shown, the usual

route is 13.3 km and 14 minutes and passes Silk Board, Madiwala and Bellandur. The suggested route is 13.5 km and 18 minutes and avoids all three.

The app also reads the live Open-

Meteo forecast, shows a "watch" for hotspots expected to be at risk within three days, lets the user test a blocked culvert, and lists the drains whose clearing would help most.

*Figure 9. The web application in a 30 mm/h scenario. The usual route from Koramangala to*

*Marathahalli (grey, dashed) crosses three red hotspots; the suggested route (green) avoids them.*

In a test on 2024–25 forecasts, same-day alerts flagged 7 of 12 news-reported floods, where a city-wide 40 mm/h rule

flagged none. Drain capacities in that test are assumed, so the figure is indicative.


## 8 Conclusion

Bengaluru's waterlogging is repeated, located and largely predictable. This project turns that observation

into a working, low-cost tool: it estimates the flood risk of each hotspot from the rainfall forecast and guides a road user around the hotspots at risk.

The work so far establishes three things. First, the physical base is sound: flow paths derived from open elevation data

reproduce the city's known drainage. Second, the system rests on real evidence. We located and verified government records with 388 mapped flood locations and 8,274 dated flood complaints, and showed that the complaints follow actual floods. Third, learning from these records adds something a rainfall alert cannot. On unseen data from 2024– 25, a rain-only model could not tell which wards would flood on a flood day, while a model with ward features could (within-day AUC 0.46 against 0.72).

The remaining work is defined and under way: training the graph neural networks and comparing them with the

baselines on identical tests, converting model output into Low, Medium and High levels in the app, and demonstrating the system on a phone with a replay of the 19 May 2025 storm. Whichever model performs best will be used, and the comparison will be reported as it stands.

## Limitations we state openly

- A complaint is a report of standing water, not a measured flood. It names a ward, not a street, and active wards report more.

- The official flood points are recorded locations, not a complete history. Unlabelled places are not proven safe.

- Rainfall data is coarse (about 10 km) and underestimates short bursts. Gauge data from KSNDMC would improve it.

- The 30 m elevation model cannot resolve underpass dips or kerb heights.

- Drain capacities are assumed until field measurements replace them.

- Roads are blocked by distance to a hotspot, not by simulated water spread.

In one line. The city already knows where it floods. This project estimates which hotspots will flood for today's

rain, and shows the way around them.

## Expected outcomes

- A tested model that gives a risk level for each hotspot for a given rainfall forecast.

- A comparison of a graph neural network with simpler models on real Bengaluru data, validated by place and by time.

- A phone-ready map with alerts and flood-aware routing.

- A ranked list of drains whose clearing would reduce flooding most, useful to the civic body.

- A cleaned, documented dataset of flood labels for the city that others can reuse.

## Future scope

Street-level labels from traffic-police advisories and citizen

photos; rain-gauge and radar input; a higher-resolution elevation model; and push notifications for regular commuters.

## References

- 1. OpenCity Urban Data Portal, Flooding Locations in Bengaluru Urban; BBMP Grievances Data; Bengaluru Stormwater Drains Maps; BBMP Ward Information. data.opencity.in (records of BBMP and KSRSAC; accessed 11 November 2026).

- 2. J. F. O'Callaghan and D. M. Mark, "The extraction of drainage networks from digital elevation data," Computer Vision, Graphics, and Image Processing, 28(3), 1984.

- 3. A. D. Nobre et al., "Height Above the Nearest Drainage: a hydrologically relevant new terrain model," Journal of Hydrology, 404, 2011.

- 4. G. Boeing, "OSMnx: New methods for acquiring, constructing, analyzing, and visualizing complex street networks," Computers, Environment and Urban Systems, 65, 2017.

- 5. T. N. Kipf and M. Welling, "Semi-supervised classification with graph convolutional networks," ICLR, 2017.

- 6. R. Bentivoglio et al., "Rapid spatio-temporal flood modelling via hydraulics-based graph neural networks," Hydrology and Earth System Sciences, 27, 2023.

- 7. C. Agonafir et al., "Understanding New York City street flooding through 311 complaints," Journal of Hydrology, 2022.

- 8. D. R. Roberts et al., "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure," Ecography, 40(8), 2017.

- 9. Copernicus DEM GLO-30 (European Space Agency); OpenStreetMap contributors; Open-Meteo weather API.
