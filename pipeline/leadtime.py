"""How early could we have warned? Backtest on forecasts issued 0-3 days before each hour.

Open-Meteo's Previous Runs API keeps, for every hour, the value forecast by the model run made
1, 2, 3... days earlier (`precipitation_previous_dayN`). Lead 0 is the most recent run. Coverage starts
in February 2024, so this test uses the 2024 and 2025 wet seasons (12 flood labels on 7 dates).

Two views:
  skill    rank-based AUC / recall at 5% false alarms per lead, as in backtest.py
  alerts   what the dashboard would actually have shown: forecast peak x bias factor vs each hotspot's
           threshold (red = ratio >= 1), and the city-wide 40 mm/h rule on the same scaled rain.
           Counts hits, misses and false-alarm hotspot-days per lead.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

import config
from pipeline import backtest
from pipeline.risk import DrainModel, rule_baseline

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
LEADS = (0, 1, 2, 3)
YEARS = (2024, 2025)
CACHE = config.RAW_DIR / "rain" / "previous_runs_hourly.csv"
SKILL_METHODS = ["rain_peak", "rain_total", "graph_model"]
N_BOOT = 500


def _var(lead):
    return "precipitation" if lead == 0 else f"precipitation_previous_day{lead}"


def hourly_by_lead(hotspots):
    """Long format: time, id, lead, mm."""
    if CACHE.exists():
        return pd.read_csv(CACHE, parse_dates=["time"])
    frames = []
    for y in YEARS:
        print(f"  fetching previous runs {y}")
        params = {"latitude": ",".join(f"{v:.4f}" for v in hotspots.lat),
                  "longitude": ",".join(f"{v:.4f}" for v in hotspots.lon),
                  "start_date": f"{y}-02-01" if y == 2024 else f"{y}-01-01", "end_date": f"{y}-12-31",
                  "hourly": ",".join(_var(l) for l in LEADS), "timezone": "Asia/Kolkata"}
        r = requests.get(URL, params=params, timeout=180)
        r.raise_for_status()
        data = r.json()
        for hid, loc in zip(hotspots.id, data if isinstance(data, list) else [data]):
            t = pd.to_datetime(loc["hourly"]["time"])
            for lead in LEADS:
                frames.append(pd.DataFrame({"time": t, "id": hid, "lead": lead, "mm": loc["hourly"][_var(lead)]}))
    out = pd.concat(frames)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE, index=False)
    return out


def bias_factor():
    f = config.OUT_DIR / "backtest_rain_bias.csv"
    return float(pd.read_csv(f).ratio.median()) if f.exists() else 1.0


def run():
    model = DrainModel()
    hs = pd.read_csv(config.HOTSPOTS_CSV)
    rain = hourly_by_lead(hs)
    i_crit = model.thresholds({"default": 0.2}).set_index("id").i_crit_mm_h
    factor = bias_factor()

    tables, skill, alerts = {}, [], []
    rng = np.random.default_rng(config.RANDOM_SEED)
    for lead in LEADS:
        r = rain[rain.lead == lead].drop(columns="lead").fillna({"mm": 0.0})
        df = backtest.score_table(backtest.daily_windows(r), model, YEARS)
        tables[lead] = df
        m = backtest.metrics(df)
        days = df.date.unique()
        groups = {d: g for d, g in df.groupby("date")}
        boots = pd.DataFrame([backtest.metrics(pd.concat([groups[d] for d in rng.choice(days, len(days))]))
                              for _ in range(N_BOOT)]).quantile([0.025, 0.975])
        for meth in SKILL_METHODS:
            skill.append({"lead_days": lead, "method": meth, "auc": m[f"{meth}|auc"],
                          "auc_lo": boots.loc[0.025, f"{meth}|auc"], "auc_hi": boots.loc[0.975, f"{meth}|auc"],
                          "recall@5%FAR": m[f"{meth}|recall@5%FAR"]})

        scaled = df.rain_peak * factor
        months = df.date.dt.to_period("M").nunique()
        for name, flag in [("drain-graph red", scaled / df.id.map(i_crit) >= 1.0),
                           ("drain-graph red+amber", scaled / df.id.map(i_crit) >= 0.8),
                           ("city-wide 40 mm/h rule", rule_baseline(scaled))]:
            alerts.append({"lead_days": lead, "alert": name,
                           "hits": int((flag & (df.label == 1)).sum()), "floods": int(df.label.sum()),
                           "false_alarm_hotspot_days": int((flag & (df.label == 0)).sum()),
                           "false_alarms_per_hotspot_month": round((flag & (df.label == 0)).sum() / len(hs) / months, 2)})

    # Combined rule: red if any of the last three model runs (leads 0-2) shows red for that day.
    base = tables[0][["date", "id", "label"]].copy()
    ratio = pd.concat([tables[l].set_index(["date", "id"]).graph_model for l in (0, 1, 2)], axis=1).max(axis=1)
    flag = (ratio * factor >= 1.0).reindex(pd.MultiIndex.from_frame(base[["date", "id"]])).to_numpy()
    months = base.date.dt.to_period("M").nunique()
    alerts.append({"lead_days": 0, "alert": "drain-graph red, any of last 3 runs",
                   "hits": int((flag & (base.label == 1)).sum()), "floods": int(base.label.sum()),
                   "false_alarm_hotspot_days": int((flag & (base.label == 0)).sum()),
                   "false_alarms_per_hotspot_month": round((flag & (base.label == 0)).sum() / len(hs) / months, 2)})

    per_event = event_table(tables, i_crit, factor)
    skill, alerts = pd.DataFrame(skill), pd.DataFrame(alerts)
    skill.round(3).to_csv(config.OUT_DIR / "leadtime_skill.csv", index=False)
    alerts.to_csv(config.OUT_DIR / "leadtime_alerts.csv", index=False)
    per_event.to_csv(config.OUT_DIR / "leadtime_events.csv", index=False)
    figure(skill, alerts, config.OUT_DIR / "leadtime_overview.png")
    return skill, alerts, per_event, factor


def event_table(tables, i_crit, factor):
    """For each documented flood: scaled forecast peak at each lead, and how early it first turned red."""
    pos = tables[0][tables[0].label == 1][["date", "id"]]
    rows = []
    for p in pos.itertuples():
        row = {"date": p.date.date(), "hotspot": p.id, "i_crit_mm_h": round(i_crit[p.id], 1)}
        red = []
        for lead in LEADS:
            t = tables[lead]
            v = float(t[(t.date == p.date) & (t.id == p.id)].rain_peak.iloc[0]) * factor
            row[f"lead{lead}_mm_h"] = round(v, 1)
            red.append(v >= i_crit[p.id])
        # earliest: first time any forecast showed red (it may have been withdrawn later)
        # steady: red in every forecast from N days out up to the day itself
        row["earliest_red_days_ahead"] = max((l for l, r in zip(LEADS, red) if r), default=None)
        steady = None
        for lead, r in zip(LEADS, red):
            if not r:
                break
            steady = lead
        row["steady_red_days_ahead"] = steady
        rows.append(row)
    return pd.DataFrame(rows)


def figure(skill, alerts, out):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    names = {"rain_peak": "Rain rule (peak)", "rain_total": "Rain rule (36 h total)", "graph_model": "Drain-graph model"}
    colors = {"rain_peak": "#8c959f", "rain_total": "#57606a", "graph_model": "#0969da"}
    ax = axes[0]
    for meth, g in skill.groupby("method"):
        ax.plot(g.lead_days, g.auc, marker="o", label=names[meth], color=colors[meth])
        ax.fill_between(g.lead_days, g.auc_lo, g.auc_hi, color=colors[meth], alpha=0.12)
    ax.axhline(0.5, color="black", lw=0.8, ls="--")
    ax.set(xlabel="Forecast issued N days before", ylabel="AUC", ylim=(0.3, 1), xticks=list(LEADS),
           title="Skill vs lead time (2024-25, 95% CI)")
    ax.legend()

    ax = axes[1]
    w = 0.25
    per_lead = alerts[~alerts.alert.str.contains("any of")]
    for i, (name, g) in enumerate(per_lead.groupby("alert", sort=False)):
        x = np.array(g.lead_days) + (i - 1) * w
        ax.bar(x, g.hits, width=w, label=f"{name}: hits")
        for xi, h, fa in zip(x, g.hits, g.false_alarms_per_hotspot_month):
            ax.text(xi, h + 0.15, f"FA {fa:g}", ha="center", fontsize=7, rotation=90)
    ax.axhline(alerts.floods.iloc[0], color="black", lw=0.8, ls="--", label="documented floods")
    ax.set(xlabel="Forecast issued N days before", ylabel="Floods warned", xticks=list(LEADS),
           title="Dashboard alerts (bars) and false alarms per hotspot-month (labels)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
