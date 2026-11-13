"""Web dashboard: JSON API over the pipeline plus the static frontend in web/.

    .venv\\Scripts\\python server.py      -> http://localhost:8000
"""
import os
import tempfile
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())

import json
import math
import time
from typing import Optional

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from pipeline import rain as rainfeed
from pipeline.rain_history import cell_of
from pipeline.risk import DrainModel, rule_baseline
from pipeline.routing import PLACES, Router

DIST = config.ROOT / "frontend" / "DDRM" / "dist"
WEB = DIST if DIST.exists() else (config.ROOT / "web")
OUTLOOK_DAYS = (1, 2, 3)
FORECAST_TTL_S = 1800

model = DrainModel()
router = Router()
culverts = {f"{u}-{v}": (u, v, label) for (u, v), label in model.culvert_options().items()}
_forecast = {"at": 0.0, "data": None}

app = FastAPI(title="Bengaluru Waterlogging Early-Warning")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def number(v, nd=1):
    """Round for JSON output; None when the model has no finite value (e.g. no drain path)."""
    v = float(v)
    return round(v, nd) if math.isfinite(v) else None


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


class ReplayQuery(Query):
    date: str = "2025-05-19"


RAIN_ARCHIVE = config.ROOT / "data" / "rain" / "rain_hourly.csv"
_archive = {"df": None}


def archive_table():
    """Hourly archived rain, one row per (time, 0.1-degree cell)."""
    if _archive["df"] is None:
        df = pd.read_csv(RAIN_ARCHIVE, parse_dates=["time"])
        df["date"] = df.time.dt.normalize()
        df["hour"] = df.time.dt.hour
        _archive["df"] = df
    return _archive["df"]


def hotspot_rows(a, watch=None):
    return [{
        "id": h.id, "name": h.name, "lat": h.lat, "lon": h.lon, "kind": h.kind, "status": str(h.status),
        "rain": number(h.rain_mm_h), "threshold": number(h.i_crit_mm_h), "ratio": number(h.load_ratio, 2),
        "bottleneck": h.bottleneck_label, "capacity_source": h.capacity_source,
        "watch": (watch or {}).get(h.id, []),
    } for h in a.itertuples()]


def status_counts(rows):
    return {s: sum(r["status"] == s for r in rows) for s in ("red", "amber", "green")}


def route_json(r):
    return None if r is None else {"latlon": r["latlon"], "km": round(r["km"], 1),
                                   "min": round(r["min"]), "crosses": r["crosses"]}


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


@app.get("/health")
def health():
    return {"status": "ok", "hotspots": len(model.names), "places": len(PLACES)}


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

    hotspots = hotspot_rows(a, watch)

    zones = json.loads(res["zones"].to_crs("EPSG:4326").to_json()) if res["zones"] is not None else None
    return {
        "hotspots": sorted(hotspots, key=lambda h: -h["ratio"]),
        "counts": status_counts(hotspots),
        "watch_count": sum(bool(h["watch"]) for h in hotspots),
        "rule_alerts": int(sum(rule_baseline(h["rain"]) for h in hotspots)),
        "route": {"usual": route_json(res["usual"]), "safe": route_json(res["safe"])},
        "zones": zones,
        "blocked_segment": blocked,
        "clear_first": [] if cf.empty else cf.drop(columns="segment").to_dict("records"),
        "forecast": forecast_info,
    }


@app.post("/api/replay")
def replay(q: ReplayQuery):
    """Hour-by-hour re-assessment of a past date from the archived hourly rain."""
    if q.origin not in PLACES or q.dest not in PLACES:
        raise HTTPException(400, "unknown place")
    day = pd.Timestamp(q.date).normalize()
    df = archive_table()
    sub = df[df.date == day]
    if sub.empty:
        raise HTTPException(404, f"no archived rain for {q.date}")

    hs = pd.read_csv(config.HOTSPOTS_CSV)
    cells = {r.id: cell_of(r.lat, r.lon) for r in hs.itertuples()}
    wide = sub.pivot_table(index="hour", columns="cell", values="mm", aggfunc="first").fillna(0.0)
    factor = bias_factor() if q.correct_bias else 1.0

    blockage = {"default": q.blockage}
    blocked = None
    if q.culvert:
        if q.culvert not in culverts:
            raise HTTPException(400, "unknown culvert")
        u, v, _ = culverts[q.culvert]
        blockage[(u, v)] = q.culvert_blockage
        blocked = model.segment_lonlat((u, v))

    frames, peak_a, peak_total, peak_hour = [], None, -1.0, "00:00"
    for hour, row in wide.iterrows():
        rain = {hid: float(row.get(cell, 0.0)) * factor for hid, cell in cells.items()}
        a = model.assess(rain, blockage)
        rows = hotspot_rows(a)
        frames.append({
            "time": f"{int(hour):02d}:00",
            "mm_max": round(float(row.max()) * factor, 1),
            "counts": status_counts(rows),
            "rule_alerts": int(sum(rule_baseline(r["rain"]) for r in rows)),
            "hotspots": sorted(rows, key=lambda h: -h["ratio"]),
        })
        total = sum(rain.values())
        if total > peak_total:
            peak_total, peak_a, peak_hour = total, a, f"{int(hour):02d}:00"

    res = router.route(PLACES[q.origin], PLACES[q.dest], peak_a)
    cf = model.clear_first(blockage, top=6)
    zones = json.loads(res["zones"].to_crs("EPSG:4326").to_json()) if res["zones"] is not None else None
    return {
        "date": str(day.date()),
        "rain_source": "Open-Meteo archive",
        "factor": factor,
        "peak_hour": peak_hour,
        "frames": frames,
        "route": {"usual": route_json(res["usual"]), "safe": route_json(res["safe"])},
        "zones": zones,
        "blocked_segment": blocked,
        "clear_first": [] if cf.empty else cf.drop(columns="segment").to_dict("records"),
    }


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")

if __name__ == "__main__":
    certfile = os.getenv("SSL_CERTFILE")
    keyfile = os.getenv("SSL_KEYFILE")
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
    )
