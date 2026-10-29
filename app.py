"""Waterlogging early-warning dashboard.

    .venv\\Scripts\\streamlit run app.py
"""
import json

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import config
from pipeline import rain as rainfeed
from pipeline.risk import DrainModel, rule_baseline
from pipeline.routing import PLACES, Router

STATUS_COLOR = {"green": "#2da44e", "amber": "#d4a72c", "red": "#cf222e"}
WATCH_COLOR = "#bc4c00"
OUTLOOK_DAYS = (1, 2, 3)

st.set_page_config(page_title="Bengaluru Waterlogging Early-Warning", layout="wide")


@st.cache_resource
def load():
    return DrainModel(), Router()


@st.cache_data(ttl=1800)
def live_forecast():
    hs = pd.read_csv(config.HOTSPOTS_CSV)
    return rainfeed.forecast_outlook(hs, days=1 + len(OUTLOOK_DAYS))


@st.cache_data
def drain_lines():
    return json.loads((config.OUT_DIR / "drain_graph_edges.geojson").read_text())


model, router = load()

# ---------------- sidebar ----------------
st.sidebar.header("Rain")
source = st.sidebar.radio("Source", ["Scenario slider", "Live forecast (Open-Meteo, next 24 h)"])
# outlook: {day k: rain for that day}, scalar or {hotspot: mm/h}; feeds the watch level
outlook = {}
if source.startswith("Scenario"):
    rain = st.sidebar.slider("Rain today (mm/h)", 0, 100, 30, step=5)
    rain_label = f"{rain} mm/h everywhere"
    later = st.sidebar.slider("Rain expected later (mm/h)", 0, 100, 0, step=5)
    later_day = st.sidebar.select_slider("...in how many days", OUTLOOK_DAYS, value=2)
    outlook = {later_day: later}
else:
    bias_file = config.OUT_DIR / "backtest_rain_bias.csv"
    factor = round(float(pd.read_csv(bias_file).ratio.median()), 1) if bias_file.exists() else 1.0
    if not st.sidebar.checkbox(f"Correct model smoothing (x{factor}, from backtest)", value=factor > 1):
        factor = 1.0
    try:
        fc = live_forecast()
        rain = {h: v[0][0] * factor for h, v in fc.items()}
        outlook = {k: {h: v[k][0] * factor for h, v in fc.items()} for k in OUTLOOK_DAYS}
        peak_h = max(fc, key=lambda h: fc[h][0][0])
        if fc[peak_h][0][0] == 0:
            rain_label = "no rain forecast in the next 24 h"
        else:
            when = fc[peak_h][0][1].strftime("%a %H:%M")
            rain_label = (f"forecast peak {fc[peak_h][0][0]:.1f} mm/h at {model.names[peak_h]} ({when})"
                          + (f", scaled x{factor} to gauge intensity" if factor != 1 else ""))
    except Exception as e:  # network down on demo day: fall back to a scenario
        st.sidebar.error(f"Forecast unavailable ({e.__class__.__name__}); using 30 mm/h")
        rain, rain_label = 30, "30 mm/h (fallback)"

st.sidebar.header("Drains")
default_b = st.sidebar.slider("Typical blockage (%)", 0, 90, 20, step=5) / 100
culverts = model.culvert_options()
choice = st.sidebar.selectbox("What if this culvert is blocked?", ["None"] + list(culverts.values()))
blockage = {"default": default_b}
blocked_edge = None
if choice != "None":
    blocked_edge = next(e for e, l in culverts.items() if l == choice)
    blockage[blocked_edge] = st.sidebar.slider("Its blockage (%)", 0, 100, 90, step=10) / 100

st.sidebar.header("Route")
names = list(PLACES)
origin = st.sidebar.selectbox("From", names, index=names.index("Koramangala (Forum)"))
dest = st.sidebar.selectbox("To", names, index=names.index("Marathahalli"))

# ---------------- model ----------------
assessed = model.assess(rain, blockage)
# Watch: a later day's forecast reaches the hotspot's threshold (same red rule, 1-3 days out).
watch = model.watch_days(outlook, blockage)
assessed["outlook"] = [("watch: in " + ", ".join(map(str, watch[h])) + " day(s)") if watch[h] else "-"
                       for h in assessed.id]
res = router.route(PLACES[origin], PLACES[dest], assessed)

st.title("Bengaluru Waterlogging Early-Warning")
st.caption(f"Rain: {rain_label}. Drain capacities are placeholder design values except where a "
           "hotspot shows 'field (Manning)'. Field measurements replace them.")

counts = assessed.status.value_counts()
rule_alerts = sum(rule_baseline(r) for r in assessed.rain_mm_h)
n_watch = sum(1 for v in watch.values() if v)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Red alert today", int(counts.get("red", 0)))
c2.metric("Amber today", int(counts.get("amber", 0)))
c3.metric("Green today", int(counts.get("green", 0)))
c4.metric("Watch (next 1-3 days)", n_watch)
c5.metric("City-wide 40 mm/h rule would alert", f"{rule_alerts} of {len(assessed)}")

if n_watch:
    names_watch = [f"{model.names[h]} (in {', '.join(map(str, d))} d)" for h, d in watch.items() if d]
    st.info("**Watch:** " + "; ".join(names_watch) + ". A heads-up, not a warning: forecasts 1-3 days out "
            "change between runs. In the 2024-25 backtest they caught 3-5 of 12 floods per lead day.")

u, s = res["usual"], res["safe"]
if u is None:
    st.error("No road route between these places.")
elif not u["crosses"]:
    st.success(f"Your usual route ({u['km']:.1f} km, {u['min']:.0f} min) avoids every flagged hotspot.")
elif s is None:
    st.error(f"Usual route crosses {', '.join(u['crosses'])}, and no dry route exists. Delay the trip.")
else:
    st.warning(f"Usual route ({u['km']:.1f} km, {u['min']:.0f} min) crosses **{', '.join(u['crosses'])}**. "
               f"Suggested route: {s['km']:.1f} km, {s['min']:.0f} min "
               f"(+{s['min'] - u['min']:.0f} min), clear of red zones.")

# ---------------- map ----------------
m = folium.Map(location=[12.96, 77.62], zoom_start=12, tiles="OpenStreetMap", control_scale=True)
drains = folium.FeatureGroup(name="Drain graph (DEM + OSM)", show=False)
folium.GeoJson(drain_lines(), style_function=lambda f: {
    "color": "#0969da", "weight": 1 + min(f["properties"]["area_km2"], 60) / 12, "opacity": 0.6},
    tooltip=folium.GeoJsonTooltip(["area_km2", "culverts"], aliases=["Upstream km²", "Road crossings"]),
).add_to(drains)
drains.add_to(m)

if res["zones"] is not None:
    zl = folium.FeatureGroup(name="Flood zones")
    folium.GeoJson(res["zones"].to_crs("EPSG:4326"), style_function=lambda f: {
        "color": STATUS_COLOR[f["properties"]["status"]], "fillOpacity": 0.25, "weight": 1}).add_to(zl)
    zl.add_to(m)

if u:
    folium.PolyLine(u["latlon"], color="#57606a", weight=5, opacity=0.7, dash_array="8",
                    tooltip=f"Usual route {u['km']:.1f} km").add_to(m)
if s and u and u["crosses"]:
    folium.PolyLine(s["latlon"], color="#1a7f37", weight=6, opacity=0.9,
                    tooltip=f"Flood-aware route {s['km']:.1f} km").add_to(m)
for label, key in [("From", origin), ("To", dest)]:
    folium.Marker(PLACES[key], tooltip=f"{label}: {key}",
                  icon=folium.Icon(color="blue" if label == "From" else "darkblue")).add_to(m)

for h in assessed.itertuples():
    if watch[h.id]:
        folium.CircleMarker([h.lat, h.lon], radius=15, color=WATCH_COLOR, weight=3, dash_array="4",
                            fill=False, tooltip=f"{h.name}: {h.outlook}").add_to(m)
    folium.CircleMarker(
        [h.lat, h.lon], radius=9, color="white", weight=2, fill=True,
        fill_color=STATUS_COLOR[h.status], fill_opacity=0.95,
        tooltip=f"{h.name}: {h.status}",
        popup=folium.Popup(f"<b>{h.name}</b><br>rain {h.rain_mm_h:.1f} mm/h vs threshold "
                           f"{h.i_crit_mm_h:.0f} mm/h<br>bottleneck: {h.bottleneck_label}<br>"
                           f"capacity: {h.capacity_source}<br>outlook: {h.outlook}", max_width=300),
    ).add_to(m)
if blocked_edge:
    folium.PolyLine(model.segment_lonlat(blocked_edge), color="black", weight=8,
                    tooltip=f"Blocked: {choice}").add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, height=560, use_container_width=True, returned_objects=[])

# ---------------- tables ----------------
t1, t2 = st.tabs(["Hotspot thresholds", "Clear these first"])
with t1:
    show = assessed[["name", "status", "outlook", "rain_mm_h", "i_crit_mm_h", "load_ratio", "bottleneck_label",
                     "capacity_source"]]
    st.dataframe(show.sort_values("load_ratio", ascending=False).round(2), hide_index=True, width="stretch")
with t2:
    st.caption("Drain segments where clearing the blockage raises hotspot thresholds the most.")
    cf = model.clear_first(blockage)
    st.dataframe(cf.drop(columns="segment") if len(cf) else cf, hide_index=True, width="stretch")
