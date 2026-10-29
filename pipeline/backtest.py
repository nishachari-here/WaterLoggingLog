"""Methodology step 5: backtest on past monsoons (2022-2025) against news-documented flood days.

Labels: data/events/flood_events.csv, one row per (date, hotspot) where a dated report names the hotspot
as waterlogged, with source. Every other hotspot-day in the wet season counts as a negative, which is
noisy: a flood nobody reported looks like "no flood". Famous spots (Silk Board) also get reported more,
so label frequency partly reflects media attention, not only flooding.

Rain: Open-Meteo historical forecast (the same family of models as the live feed), hourly, per hotspot.
Window for day D: D-1 12:00 to D 23:00, so overnight storms reported on the morning of D are covered.

Methods (each gives a score per hotspot-day; higher = more likely to flood):
  rain_peak     peak hourly rain                    (baseline 1: rainfall-threshold rule)
  rain_total    36 h rain total                     (baseline 1b)
  terrain_only  terrain susceptibility score        (baseline 2: static map, same every day)
  terrain_rain  peak rain x terrain score / 100     (baseline 2 gated by rain)
  graph_model   peak rain / hotspot threshold i_crit (our drain-graph model, placeholder capacities)

All metrics are rank-based (AUC, recall at a fixed false-alarm rate), so they do not depend on the
gridded rain being far weaker than gauge rain.
"""
from datetime import timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import truststore

import config
from pipeline.risk import DrainModel

truststore.inject_into_ssl()

EVENTS = config.ROOT / "data" / "events" / "flood_events.csv"
OBSERVED = config.ROOT / "data" / "events" / "observed_rain.csv"
RAIN_CACHE = config.RAW_DIR / "rain" / "hist_forecast_hourly.csv"
URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
YEARS = range(2022, 2026)
WET_MONTHS = range(4, 13)  # April-December: pre-monsoon, SW and NE monsoon
FAR_LEVELS = (0.05, 0.01)
N_BOOT = 1000
METHODS = ["rain_peak", "rain_total", "terrain_only", "terrain_rain", "graph_model"]


def _fetch(lats, lons, start, end):
    params = {"latitude": ",".join(f"{v:.4f}" for v in lats), "longitude": ",".join(f"{v:.4f}" for v in lons),
              "start_date": start, "end_date": end, "hourly": "precipitation", "timezone": "Asia/Kolkata"}
    r = requests.get(URL, params=params, timeout=120)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else [d]


def hourly_rain(hotspots):
    """Hourly precipitation (mm) per hotspot, 2022-2025. Long format: time, id, mm."""
    if RAIN_CACHE.exists():
        return pd.read_csv(RAIN_CACHE, parse_dates=["time"])
    frames = []
    for y in YEARS:
        print(f"  fetching {y}")
        for hid, loc in zip(hotspots.id, _fetch(hotspots.lat, hotspots.lon, f"{y}-01-01", f"{y}-12-31")):
            frames.append(pd.DataFrame({"time": pd.to_datetime(loc["hourly"]["time"]), "id": hid,
                                        "mm": loc["hourly"]["precipitation"]}))
    rain = pd.concat(frames).fillna({"mm": 0.0})
    RAIN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    rain.to_csv(RAIN_CACHE, index=False)
    return rain


def daily_windows(rain):
    """Peak hourly and 36 h total for every (day, hotspot), window D-1 12:00 .. D 23:00."""
    wide = rain.pivot(index="time", columns="id", values="mm").sort_index()
    peak = wide.rolling("36h").max()
    total = wide.rolling("36h").sum()
    at = peak.index[peak.index.hour == 23]  # window ending 23:00 on day D
    out = []
    for name, frame in [("rain_peak", peak), ("rain_total", total)]:
        s = frame.loc[at].stack().rename(name)
        out.append(s)
    df = pd.concat(out, axis=1).reset_index()
    df["date"] = df["time"].dt.normalize()
    return df.drop(columns="time")


def build_table(model):
    hs = pd.read_csv(config.HOTSPOTS_CSV)
    return score_table(daily_windows(hourly_rain(hs)), model, YEARS)


def score_table(df, model, years):
    """Wet-season hotspot-days with flood labels and every method's score."""
    terrain = pd.read_csv(config.OUT_DIR / "hotspot_terrain_features.csv").set_index("id").terrain_score
    i_crit = model.thresholds({"default": 0.2}).set_index("id").i_crit_mm_h
    df = df[df.date.dt.month.isin(WET_MONTHS) & df.date.dt.year.isin(years)].copy()
    ev = pd.read_csv(EVENTS, parse_dates=["date"])
    pos = set(zip(ev.date, ev.hotspot_id))
    conf = {(d, h): c for d, h, c in zip(ev.date, ev.hotspot_id, ev.confidence)}
    df["label"] = [int((d, h) in pos) for d, h in zip(df.date, df.id)]
    df["confidence"] = [conf.get((d, h), "") for d, h in zip(df.date, df.id)]
    df["terrain_only"] = df.id.map(terrain)
    df["terrain_rain"] = df.rain_peak * df.terrain_only / 100
    df["graph_model"] = df.rain_peak / df.id.map(i_crit)
    return df


def auc(y, s):
    y, s = np.asarray(y), np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return (ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def recall_at_far(y, s, far):
    """Pick the threshold that flags `far` of negative hotspot-days; report share of positives caught."""
    y, s = np.asarray(y), np.asarray(s)
    neg = s[y == 0]
    thr = np.quantile(neg, 1 - far)
    return float(np.mean(s[y == 1] > thr)) if (y == 1).any() else np.nan


def metrics(df):
    row = {}
    for m in METHODS:
        row[f"{m}|auc"] = auc(df.label, df[m])
        for f in FAR_LEVELS:
            row[f"{m}|recall@{int(f * 100)}%FAR"] = recall_at_far(df.label, df[m], f)
    return row


def bootstrap(df, rng):
    """95% CI by resampling whole days (hotspots on the same day share rain, so they are not independent)."""
    days = df.date.unique()
    groups = {d: g for d, g in df.groupby("date")}
    rows = []
    for _ in range(N_BOOT):
        pick = rng.choice(days, size=len(days), replace=True)
        rows.append(metrics(pd.concat([groups[d] for d in pick])))
    return pd.DataFrame(rows).quantile([0.025, 0.975])


def event_day_spatial(df):
    """On documented flood days only: does the method rank the flooded hotspots above the others?"""
    out = {m: [] for m in METHODS}
    for _, g in df[df.date.isin(df[df.label == 1].date)].groupby("date"):
        for m in METHODS:
            a = auc(g.label, g[m])
            if not np.isnan(a):
                out[m].append(a)
    return {m: (np.mean(v), len(v)) for m, v in out.items()}


def day_detection(df):
    """City level: is the day a documented flood day? Score = max peak rain over hotspots."""
    d = df.groupby("date").agg(label=("label", "max"), rain_peak=("rain_peak", "max"), rain_total=("rain_total", "max"))
    return {"n_days": len(d), "n_flood_days": int(d.label.sum()),
            "auc_peak": auc(d.label, d.rain_peak), "auc_total": auc(d.label, d.rain_total),
            "recall@5%FAR_peak": recall_at_far(d.label, d.rain_peak, 0.05)}


def rain_bias():
    """Reported gauge totals vs Open-Meteo 36 h total at the same place and day."""
    obs = pd.read_csv(OBSERVED, parse_dates=["date"])
    rows = []
    for o in obs.itertuples():
        start = (o.date - timedelta(days=1)).strftime("%Y-%m-%d")
        loc = _fetch([o.lat], [o.lon], start, o.date.strftime("%Y-%m-%d"))[0]
        t = pd.to_datetime(loc["hourly"]["time"])
        mm = pd.Series(loc["hourly"]["precipitation"], index=t).fillna(0)
        win = mm[(mm.index >= o.date - timedelta(hours=12)) & (mm.index <= o.date + timedelta(hours=23))]
        rows.append({"date": o.date.date(), "place": o.place, "reported_mm": o.reported_mm,
                     "model_36h_mm": round(win.sum(), 1), "model_peak_mm_h": round(win.max(), 1),
                     "ratio": round(o.reported_mm / max(win.sum(), 0.1), 2)})
    return pd.DataFrame(rows)


def figure(df, summary, ci, out):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    labels = {"rain_peak": "Rain rule (peak)", "rain_total": "Rain rule (36 h total)",
              "terrain_only": "Terrain only", "terrain_rain": "Terrain x rain", "graph_model": "Drain-graph model"}
    for ax, metric, title in [(axes[0], "auc", "AUC (hotspot-days)"), (axes[1], "recall@5%FAR", "Recall at 5% false alarms")]:
        vals = [summary[f"{m}|{metric}"] for m in METHODS]
        lo = [summary[f"{m}|{metric}"] - ci.loc[0.025, f"{m}|{metric}"] for m in METHODS]
        hi = [ci.loc[0.975, f"{m}|{metric}"] - summary[f"{m}|{metric}"] for m in METHODS]
        colors = ["#8c959f"] * 4 + ["#0969da"]
        ax.barh([labels[m] for m in METHODS], vals, xerr=[lo, hi], color=colors, capsize=4)
        ax.set_xlim(0, 1)
        if metric == "auc":
            ax.axvline(0.5, color="black", lw=0.8, ls="--")
        ax.set_title(title)
    fig.suptitle(f"Backtest 2022-2025 (Apr-Dec): {int(df.label.sum())} flood hotspot-days, "
                 f"{int((df.label == 0).sum())} other hotspot-days. Bars: 95% CI (day bootstrap)")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def run():
    model = DrainModel()
    df = build_table(model)
    summary = metrics(df)
    ci = bootstrap(df, np.random.default_rng(config.RANDOM_SEED))
    high = metrics(df[(df.label == 0) | (df.confidence == "high")])
    spatial = event_day_spatial(df)
    days = day_detection(df)
    bias = rain_bias()

    rows = []
    for m in METHODS:
        rows.append({"method": m, "auc": summary[f"{m}|auc"],
                     "auc_ci": f"{ci.loc[0.025, f'{m}|auc']:.2f}-{ci.loc[0.975, f'{m}|auc']:.2f}",
                     "recall@5%FAR": summary[f"{m}|recall@5%FAR"],
                     "recall@5%FAR_ci": f"{ci.loc[0.025, f'{m}|recall@5%FAR']:.2f}-{ci.loc[0.975, f'{m}|recall@5%FAR']:.2f}",
                     "recall@1%FAR": summary[f"{m}|recall@1%FAR"],
                     "auc_high_conf_only": high[f"{m}|auc"],
                     "event_day_spatial_auc": spatial[m][0]})
    table = pd.DataFrame(rows).round(3)
    per_hotspot = df.groupby("id").label.sum().sort_values(ascending=False)

    config.OUT_DIR.mkdir(exist_ok=True)
    table.to_csv(config.OUT_DIR / "backtest_metrics.csv", index=False)
    bias.to_csv(config.OUT_DIR / "backtest_rain_bias.csv", index=False)
    df.to_csv(config.PROCESSED_DIR / "backtest_hotspot_days.csv", index=False)
    figure(df, summary, ci, config.OUT_DIR / "backtest_overview.png")
    return table, days, spatial, bias, per_hotspot, df
