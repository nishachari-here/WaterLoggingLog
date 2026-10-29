"""Web dashboard: JSON API over the pipeline plus the static frontend in web/.

    .venv\\Scripts\\python server.py      -> http://localhost:8000
"""
import json
import time
from typing import Optional

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from pipeline import rain as rainfeed
from pipeline.risk import DrainModel, rule_baseline
from pipeline.routing import PLACES, Router

WEB = config.ROOT / "web"
OUTLOOK_DAYS = (1, 2, 3)
FORECAST_TTL_S = 1800

model = DrainModel()
router = Router()
culverts = {f"{u}-{v}": (u, v, label) for (u, v), label in model.culvert_options().items()}
_forecast = {"at": 0.0, "data": None}

app = FastAPI(title="Bengaluru Waterlogging Early-Warning")


def bias_factor():
    f = config.OUT_DIR / "backtest_rain_bias.csv"
    return round(float(pd.read_csv(f).ratio.median()), 1) if f.exists() else 1.0


def live_forecast():
    if _forecast["data"] is None or time.time() - _forecast["at"] > FORECAST_TTL_S:
        _forecast["data"] = rainfeed.forecast_outlook(pd.read_csv(config.HOTSPOTS_CSV), days=1 + len(OUTLOOK_DAYS))
        _forecast["at"] = time.time()
    return _forecast["data"], _forecast["at"]


class Query(BaseModel):
    mode: str = "scenario"            # "scenario" | "live"
    rain_today: float = 30
    rain_later: float = 0
    later_day: int = 2
    correct_bias: bool = True
    blockage: float = 0.2
    culvert: Optional[str] = None
    culvert_blockage: float = 0.9
    origin: str = "Koramangala (Forum)"
    dest: str = "Marathahalli"


@app.get("/api/meta")
def meta():
    hs = pd.read_csv(config.HOTSPOTS_CSV)
    return {
        "hotspots": hs[["id", "name", "lat", "lon", "kind"]].to_dict("records"),
        "places": [{"name": k, "lat": v[0], "lon": v[1]} for k, v in PLACES.items()],
        "culverts": [{"id": k, "label": v[2]} for k, v in culverts.items()],
        "bias_factor": bias_factor(),
    }


@app.get("/api/drains")
def drains():
    return json.loads((config.OUT_DIR / "drain_graph_edges.geojson").read_text())


@app.post("/api/assess")
def assess(q: Query):
    if q.origin not in PLACES or q.dest not in PLACES:
        raise HTTPException(400, "unknown place")
    blockage = {"default": q.blockage}
    blocked = None
    if q.culvert:
        if q.culvert not in culverts:
            raise HTTPException(400, "unknown culvert")
        u, v, _ = culverts[q.culvert]
        blockage[(u, v)] = q.culvert_blockage
        blocked = model.segment_lonlat((u, v))

    forecast_info = None
    if q.mode == "live":
        factor = bias_factor() if q.correct_bias else 1.0
        try:
            fc, fetched = live_forecast()
        except Exception as e:  # keep the demo alive without network
            raise HTTPException(503, f"forecast unavailable: {e.__class__.__name__}")
        rain = {h: v[0][0] * factor for h, v in fc.items()}
        outlook = {k: {h: v[k][0] * factor for h, v in fc.items()} for k in OUTLOOK_DAYS}
        peak = max(fc, key=lambda h: fc[h][0][0])
        forecast_info = {
            "factor": factor, "fetched_at": time.strftime("%H:%M", time.localtime(fetched)),
            "peak_raw_mm_h": fc[peak][0][0], "peak_hotspot": model.names[peak],
            "peak_time": fc[peak][0][1].strftime("%a %H:%M") if fc[peak][0][0] > 0 else None,
            "daily_peaks": [{"day": k, "max_mm_h": round(max(v[k][0] for v in fc.values()) * factor, 1)}
                            for k in range(1 + len(OUTLOOK_DAYS))],
        }
    else:
        rain = q.rain_today
        outlook = {q.later_day: q.rain_later} if q.rain_later > 0 else {}

    a = model.assess(rain, blockage)
    watch = model.watch_days(outlook, blockage)
    res = router.route(PLACES[q.origin], PLACES[q.dest], a)
    cf = model.clear_first(blockage, top=6)

    hotspots = [{
        "id": h.id, "name": h.name, "lat": h.lat, "lon": h.lon, "kind": h.kind, "status": str(h.status),
        "rain": round(h.rain_mm_h, 1), "threshold": round(h.i_crit_mm_h, 1), "ratio": round(h.load_ratio, 2),
        "bottleneck": h.bottleneck_label, "capacity_source": h.capacity_source, "watch": watch[h.id],
    } for h in a.itertuples()]

    def route_json(r):
        return None if r is None else {"latlon": r["latlon"], "km": round(r["km"], 1),
                                       "min": round(r["min"]), "crosses": r["crosses"]}

    zones = json.loads(res["zones"].to_crs("EPSG:4326").to_json()) if res["zones"] is not None else None
    return {
        "hotspots": sorted(hotspots, key=lambda h: -h["ratio"]),
        "counts": {s: sum(h["status"] == s for h in hotspots) for s in ("red", "amber", "green")},
        "watch_count": sum(bool(h["watch"]) for h in hotspots),
        "rule_alerts": int(sum(rule_baseline(h["rain"]) for h in hotspots)),
        "route": {"usual": route_json(res["usual"]), "safe": route_json(res["safe"])},
        "zones": zones,
        "blocked_segment": blocked,
        "clear_first": [] if cf.empty else cf.drop(columns="segment").to_dict("records"),
        "forecast": forecast_info,
    }


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
