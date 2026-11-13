"""Rain forecast per hotspot from Open-Meteo (free, no key, hourly precipitation in mm = mm/h).

Model forecasts smooth out short convective bursts, so treat the hourly peak as a lower bound
on what a 15-minute gauge would record (the dashboard scales it by the backtest bias factor).
"""
from datetime import datetime, timedelta

import requests
import truststore

truststore.inject_into_ssl()

URL = "https://api.open-meteo.com/v1/forecast"


def forecast_outlook(hotspots, days=4):
    """{hotspot_id: [(peak mm/h, local time of peak) for each 24 h window from now]}.
    Window 0 is the next 24 h (today's alert), windows 1..days-1 feed the watch level."""
    params = {
        "latitude": ",".join(f"{v:.4f}" for v in hotspots.lat),
        "longitude": ",".join(f"{v:.4f}" for v in hotspots.lon),
        "hourly": "precipitation", "forecast_days": days + 1, "timezone": "Asia/Kolkata",
    }
    r = requests.get(URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    data = data if isinstance(data, list) else [data]
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    out = {}
    for hid, loc in zip(hotspots.id, data):
        series = [(p or 0.0, datetime.fromisoformat(t)) for p, t in zip(loc["hourly"]["precipitation"], loc["hourly"]["time"])]
        out[hid] = []
        for k in range(days):
            lo, hi = now + timedelta(hours=24 * k), now + timedelta(hours=24 * (k + 1))
            window = [(p, t) for p, t in series if lo <= t < hi]
            out[hid].append(max(window) if window else (0.0, None))
    return out
