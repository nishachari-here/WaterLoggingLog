"""Build the hotspot-day label table and compare physics, rain and terrain models.

    .venv\\Scripts\\python run_labels.py

The table is the shared input for the GNN branch: one row per hotspot per day with
rain features, the terrain features of the nearest GNN graph node, the risk.py
threshold, the physics ratio (peak rain / threshold) and the 0/1 flood label.

Validation is leave-one-hotspot-out, so a hotspot is never in both train and test.
Every tuning decision (regularisation C, and the false-alarm threshold used for the
deployment-style recall) is made inside the training folds.

Outputs in outputs/:
  label_table.csv                  the feature table
  hotspot_graph_nodes.csv          hotspot -> nearest graph node + snap distance
  hotspot_thresholds.csv           risk.py i_crit and where it came from
  label_table_metrics.csv          LOHO comparison (AUC, AP, recall at 5%/1% FAR)
  label_table_alignment.csv        rain-window / label-timing comparison
  label_table_label_shift.csv      label date +/- days sensitivity
  label_table_rules.csv            fixed-threshold alert rules
  label_table_oof_predictions.csv  out-of-fold scores, one column per model
"""
import json
import pickle

import numpy as np
import pandas as pd
import requests
import truststore
from pyproj import Transformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config
from pipeline.risk import BACKWATER_M, EXPONENT, I_REF
from pipeline.rain_cache import read_cache, write_cache

truststore.inject_into_ssl()

EVENTS = config.ROOT / "data" / "events" / "flood_events.csv"
NODES = config.ROOT / "data" / "graphs" / "gnn_graph_nodes.csv"
GRAPH = config.ROOT / "data" / "graphs" / "gnn_graph.pkl"
DRAIN_EDGES = config.OUT_DIR / "drain_graph_edges.geojson"
TERRAIN_FEATURES = config.OUT_DIR / "hotspot_terrain_features.csv"
URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
RAIN_MODEL = "ecmwf_ifs025"

YEARS = range(2022, 2026)
WET_MONTHS = range(4, 13)          # Apr-Dec, same as pipeline/backtest.py
FAR_LEVELS = (0.05, 0.01)
BLOCKAGE = 0.2                     # same default as DrainModel.thresholds()
BIAS_FALLBACK = 4.8                # median reported/modelled ratio from backtest_rain_bias.csv
N_BOOT = 1000

# Rain window per alignment: (sample hour on the report day, day shift, window hours).
# The 24 hourly values ending at `sample hour` are the window.
ALIGNMENTS = {
    "same_day": (23, 0, 24),       # D 00:00 .. D 23:00
    "report_day": (12, 0, 24),     # D-1 13:00 .. D 12:00  <- chosen
    "prev_day": (23, -1, 24),      # D-1 00:00 .. D-1 23:00
    "backtest_36h": (23, 0, 36),   # D-1 12:00 .. D 23:00, the old backtest window
}
CHOSEN_ALIGNMENT = "report_day"

# Feature sets for the LOHO logistic regressions. Log transforms are fixed a priori
# because rain intensity and upstream area are strongly right-skewed.
TERRAIN_COLS = ["hand_m", "depression_m", "upstream_km2_log", "twi", "tpi300_m", "tpi1000_m"]
LOGIT_SETS = {
    "logit_rain": ["rain_peak_1h_log", "rain_3h_log", "rain_24h_log"],
    "logit_terrain": TERRAIN_COLS,
    "logit_rain_terrain": ["rain_peak_1h_log", "rain_3h_log", "rain_24h_log"] + TERRAIN_COLS,
    "logit_rain_physics": ["rain_peak_1h_log", "rain_3h_log", "rain_24h_log", "physics_ratio"],
    "logit_all": ["rain_peak_1h_log", "rain_3h_log", "rain_24h_log"] + TERRAIN_COLS + ["physics_ratio"],
}
BASELINES = {
    "rain_peak_1h": "rain_peak_1h",                 # rainfall-threshold rule score
    "terrain_only": "terrain_score",                # static terrain susceptibility
    "terrain_x_rain": "terrain_rain_score",         # old terrain x rain baseline
    "physics_ratio": "physics_ratio",               # the new physics feature alone
}
C_GRID = (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)


# ---------------------------------------------------------------- rain
def hourly_rain(hotspots):
    """Hourly precipitation per hotspot, 2022-2025, long format: time, id, mm."""
    cached = read_cache(config.RAW_DIR, RAIN_MODEL)
    if cached is not None:
        return cached
    frames = []
    grid_locations = []
    for year in YEARS:
        print(f"  fetching rain {year}")
        params = {"latitude": ",".join(f"{v:.4f}" for v in hotspots.lat),
                  "longitude": ",".join(f"{v:.4f}" for v in hotspots.lon),
                  "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
                  "hourly": "precipitation", "timezone": "Asia/Kolkata", "models": RAIN_MODEL}
        r = requests.get(URL, params=params, timeout=180)
        r.raise_for_status()
        data = r.json()
        for hid, loc in zip(hotspots.id, data if isinstance(data, list) else [data]):
            grid_locations.append({"id": hid, "latitude": loc.get("latitude"), "longitude": loc.get("longitude")})
            frames.append(pd.DataFrame({"time": pd.to_datetime(loc["hourly"]["time"]),
                                        "id": hid, "mm": loc["hourly"]["precipitation"]}))
    rain = pd.concat(frames).fillna({"mm": 0.0})
    write_cache(config.RAW_DIR, RAIN_MODEL, rain, grid_locations)
    return rain


def daily_features(rain, alignment):
    """Peak 1 h, max 3 h total and window total for every (date, hotspot)."""
    hour, shift, window_h = ALIGNMENTS[alignment]
    wide = rain.pivot(index="time", columns="id", values="mm").sort_index()
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="h")).fillna(0.0)

    # rolling(W).max() = highest hourly value in the W-hour window; the 3 h feature is
    # the highest 3 h total inside the window, not just the last three hours.
    peak = wide.rolling(window_h).max()
    three = wide.rolling(3).sum().rolling(window_h).max()
    total = wide.rolling(window_h).sum()

    def sample(frame, name):
        s = frame[frame.index.hour == hour].copy()
        s.index = s.index.normalize() + pd.Timedelta(days=shift)
        s.index.name = "date"
        return s.stack().rename(name).reset_index()

    df = sample(peak, "rain_peak_1h")
    df = df.merge(sample(three, "rain_3h"), on=["date", "id"])
    df = df.merge(sample(total, "rain_total_window"), on=["date", "id"])
    df["window_hours"] = window_h
    # the first day has an incomplete rolling window; drop it rather than keep NaN
    return df.dropna(subset=["rain_peak_1h", "rain_3h", "rain_total_window"]).reset_index(drop=True)


# ---------------------------------------------------------------- graph mapping
def snap_hotspots(hotspots, nodes):
    """Nearest GNN graph node per hotspot, with the snap distance in metres."""
    to_utm = Transformer.from_crs("EPSG:4326", config.CRS_METRIC, always_xy=True)
    hx, hy = to_utm.transform(hotspots.lon.values, hotspots.lat.values)
    rows = []
    for h, x, y in zip(hotspots.itertuples(), hx, hy):
        d = np.hypot(nodes.x.to_numpy() - x, nodes.y.to_numpy() - y)
        i = int(np.argmin(d))
        n = nodes.iloc[i]
        rows.append({"id": h.id, "name": h.name, "kind": h.kind,
                     "hotspot_lat": h.lat, "hotspot_lon": h.lon,
                     "node_id": n.node_id, "node_type": n.node_type,
                     "node_lat": n.lat, "node_lon": n.lon,
                     "snap_dist_m": round(float(d[i]), 1),
                     "hand_m": n.hand_m, "depression_m": n.depression_m,
                     "upstream_km2": n.upstream_km2, "twi": n.twi,
                     "tpi300_m": n.tpi300_m, "tpi1000_m": n.tpi1000_m,
                     "elev_m": n.elev_m, "slope_deg": n.slope_deg})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- thresholds
def _lake_edges():
    if not DRAIN_EDGES.exists():
        return {}
    data = json.loads(DRAIN_EDGES.read_text())
    return {(f["properties"]["u"], f["properties"]["v"]): f["properties"]["in_lake"]
            for f in data["features"]}


def _downstream(g, node, lake_edges):
    """Edges a hotspot's water passes through before backwater stops mattering."""
    out, dist = [], 0.0
    while dist < BACKWATER_M:
        successors = list(g.successors(node))
        if not successors:
            break
        nxt = successors[0]
        edge = next(iter(g.get_edge_data(node, nxt).values()))
        u = int(str(node).split(":")[1])
        v = int(str(nxt).split(":")[1])
        if lake_edges.get((u, v), False):   # lakes are storage: stop the walk
            break
        out.append(edge)
        dist += edge["length_m"]
        node = nxt
    return out


def threshold_table(hotspots):
    """risk.py critical intensity per hotspot, plus the bottleneck area and source.

    Six values are copied from the existing risk.py backtest output (leadtime_events.csv).
    The other six are recomputed with the same formula on the GNN drain graph because the
    original data/processed/drain_graph.pkl is not committed. The recomputation reproduces
    five of the six known values within rounding; Kogilu is the exception, so the known value is used.
    """
    known = {}
    leadtime = config.OUT_DIR / "leadtime_events.csv"
    if leadtime.exists():
        known = pd.read_csv(leadtime).groupby("hotspot").i_crit_mm_h.first().to_dict()

    g = pickle.load(open(GRAPH, "rb"))
    lake_edges = _lake_edges()
    drain_nodes = [(n, d) for n, d in g.nodes(data=True) if d.get("node_type") == "drain"]

    rows = []
    for h in hotspots.itertuples():
        best = None
        for n, d in drain_nodes:
            dist = float(np.hypot(d["x"] - h.x, d["y"] - h.y))
            if best is None or dist < best[0]:
                best = (dist, n)
        drain_node, drain_dist = best[1], best[0]
        edges = _downstream(g, drain_node, lake_edges)
        vals = [(I_REF * e["area_km2"] ** EXPONENT * (1 - BLOCKAGE) / e["area_km2"],
                 e["area_km2"]) for e in edges]
        i_crit_recon, bottleneck_area = min(vals) if vals else (float("inf"), np.nan)
        i_crit = known.get(h.id, i_crit_recon)
        source = "risk.py (leadtime_events.csv)" if h.id in known else "risk.py formula on GNN drain graph"
        rows.append({"id": h.id, "i_crit_mm_h": i_crit,
                     "i_crit_reconstructed_mm_h": i_crit_recon,
                     "threshold_source": source,
                     "drain_node": drain_node, "drain_snap_m": round(drain_dist, 1),
                     "bottleneck_area_km2": bottleneck_area})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- table
def build_table(hotspots, mapping, thresholds, rain, bias):
    feats = daily_features(rain, CHOSEN_ALIGNMENT)
    feats = feats.rename(columns={"rain_total_window": "rain_24h"})
    df = feats.merge(mapping, on="id").merge(thresholds, on="id")

    events = pd.read_csv(EVENTS, parse_dates=["date"])
    events = events.drop_duplicates(["date", "hotspot_id"], keep="first")
    key = {(d.date(), h): (c, e, s) for d, h, c, e, s in
           zip(events.date, events.hotspot_id, events.confidence, events.evidence, events.source)}
    df["label"] = [int((d.date(), h) in key) for d, h in zip(df.date, df.id)]
    df["label_confidence"] = [key.get((d.date(), h), ("", "", ""))[0] for d, h in zip(df.date, df.id)]
    df["evidence"] = [key.get((d.date(), h), ("", "", ""))[1] for d, h in zip(df.date, df.id)]
    df["source"] = [key.get((d.date(), h), ("", "", ""))[2] for d, h in zip(df.date, df.id)]

    terrain = pd.read_csv(TERRAIN_FEATURES)[["id", "terrain_score"]]
    df = df.merge(terrain, on="id", how="left")
    df["wet_season"] = df.date.dt.month.isin(WET_MONTHS)

    df["rain_peak_1h_corrected"] = df.rain_peak_1h * bias
    df["rain_3h_corrected"] = df.rain_3h * bias
    df["rain_24h_corrected"] = df.rain_24h * bias
    df["physics_ratio"] = df.rain_peak_1h / df.i_crit_mm_h
    df["physics_ratio_corrected"] = df.physics_ratio * bias
    df["terrain_rain_score"] = df.rain_peak_1h * df.terrain_score / 100.0
    for col in ["rain_peak_1h", "rain_3h", "rain_24h", "upstream_km2"]:
        df[f"{col}_log"] = np.log1p(df[col].clip(lower=0))

    df = df.sort_values(["id", "date"]).reset_index(drop=True)
    num_cols = [c for c in df.select_dtypes("number").columns if c != "label"]
    df[num_cols] = df[num_cols].round(4)
    cols = ["date", "id", "name", "kind", "hotspot_lat", "hotspot_lon",
            "node_id", "node_type", "node_lat", "node_lon", "snap_dist_m",
            "rain_peak_1h", "rain_3h", "rain_24h",
            "rain_peak_1h_corrected", "rain_3h_corrected", "rain_24h_corrected",
            "rain_peak_1h_log", "rain_3h_log", "rain_24h_log",
            "hand_m", "depression_m", "upstream_km2", "upstream_km2_log",
            "twi", "tpi300_m", "tpi1000_m", "elev_m", "slope_deg", "terrain_score",
            "i_crit_mm_h", "threshold_source", "physics_ratio", "physics_ratio_corrected",
            "terrain_rain_score", "label", "label_confidence", "evidence", "source",
            "wet_season"]
    return df[cols]


# ---------------------------------------------------------------- validation
def _pipeline(C):
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=C, class_weight="balanced",
                                            max_iter=5000, solver="lbfgs"))


def _inner_splits(X, y, groups):
    n = min(4, len(np.unique(groups)))
    if n < 2:
        return []
    return list(StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=42).split(X, y, groups))


def _tune_C(X, y, groups):
    """Pick C on inner folds of the training hotspots only."""
    best_c, best_score = 1.0, -np.inf
    for C in C_GRID:
        scores = []
        for tr, va in _inner_splits(X, y, groups):
            if len(np.unique(y[tr])) < 2 or len(np.unique(y[va])) < 2:
                continue
            model = _pipeline(C).fit(X[tr], y[tr])
            scores.append(roc_auc_score(y[va], model.predict_proba(X[va])[:, 1]))
        if scores and np.mean(scores) > best_score:
            best_c, best_score = C, np.mean(scores)
    return best_c


def _inner_oof(X, y, groups, C):
    """Out-of-fold predictions on the training hotspots, for the FAR threshold."""
    pred = np.full(len(y), np.nan)
    for tr, va in _inner_splits(X, y, groups):
        if len(np.unique(y[tr])) < 2:
            continue
        model = _pipeline(C).fit(X[tr], y[tr])
        pred[va] = model.predict_proba(X[va])[:, 1]
    return pred


def loho_logit(df, cols):
    """Leave-one-hotspot-out predictions, C and FAR thresholds chosen inside train folds."""
    X, y, groups = df[cols].to_numpy(), df.label.to_numpy(), df.id.to_numpy()
    oof = np.full(len(y), np.nan)
    flags = {f: np.zeros(len(y), dtype=bool) for f in FAR_LEVELS}
    chosen = []
    for tr, te in LeaveOneGroupOut().split(X, y, groups):
        if len(np.unique(y[tr])) < 2:      # cannot fit a classifier; keep the fold neutral
            oof[te] = 0.0
            chosen.append(np.nan)
            continue
        C = _tune_C(X[tr], y[tr], groups[tr])
        chosen.append(C)
        model = _pipeline(C).fit(X[tr], y[tr])
        oof[te] = model.predict_proba(X[te])[:, 1]
        train_oof = _inner_oof(X[tr], y[tr], groups[tr], C)
        for far in FAR_LEVELS:
            neg = train_oof[(y[tr] == 0) & ~np.isnan(train_oof)]
            thr = np.quantile(neg, 1 - far) if len(neg) else 0.5
            flags[far][te] = oof[te] > thr
    return oof, flags, chosen


def loho_score_flags(y, score, groups):
    """For a fixed score (baseline): choose the FAR threshold on the training hotspots."""
    flags = {f: np.zeros(len(y), dtype=bool) for f in FAR_LEVELS}
    for tr, te in LeaveOneGroupOut().split(score.reshape(-1, 1), y, groups):
        for far in FAR_LEVELS:
            neg = score[tr][y[tr] == 0]
            thr = np.quantile(neg, 1 - far) if len(neg) else 0.5
            flags[far][te] = score[te] > thr
    return flags


def recall_at_far(y, score, far):
    y, score = np.asarray(y), np.asarray(score)
    neg = score[y == 0]
    if len(neg) == 0 or (y == 1).sum() == 0:
        return np.nan
    return float(np.mean(score[y == 1] > np.quantile(neg, 1 - far)))


def metric_row(name, kind, features, y, score, flags):
    row = {"model": name, "kind": kind, "features": features,
           "n_pos": int((y == 1).sum()), "n_neg": int((y == 0).sum())}
    row["auc"] = roc_auc_score(y, score)
    row["ap"] = average_precision_score(y, score)
    for far in FAR_LEVELS:
        tag = f"{int(far * 100)}%"
        row[f"recall@{tag}FAR"] = recall_at_far(y, score, far)
        flag = flags[far]
        row[f"recall@{tag}FAR_train_thr"] = float(flag[y == 1].mean()) if (y == 1).any() else np.nan
        row[f"far@{tag}_train_thr"] = float(flag[y == 0].mean()) if (y == 0).any() else np.nan
    return row


def bootstrap_ci(y, score, days, flags, rng, n_boot=N_BOOT):
    """95% CI by resampling whole days; hotspots on a day share the same rain."""
    day_codes = pd.factorize(days)[0]
    by_day = [np.flatnonzero(day_codes == d) for d in range(day_codes.max() + 1)]
    rows = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(by_day), len(by_day))
        idx = np.concatenate([by_day[i] for i in pick])
        yy, ss = y[idx], score[idx]
        if yy.sum() == 0 or (yy == 0).sum() == 0:
            continue
        row = {"auc": roc_auc_score(yy, ss), "ap": average_precision_score(yy, ss)}
        for far in FAR_LEVELS:
            tag = f"{int(far * 100)}%"
            row[f"recall@{tag}FAR"] = recall_at_far(yy, ss, far)
            row[f"recall@{tag}FAR_train_thr"] = float(flags[far][idx][yy == 1].mean())
        rows.append(row)
    if not rows:
        return {}
    q = pd.DataFrame(rows).quantile([0.025, 0.975])
    return {col: (q.loc[0.025, col], q.loc[0.975, col]) for col in q.columns}


def evaluate(df, rng):
    y, groups, days = df.label.to_numpy(), df.id.to_numpy(), df.date.to_numpy()
    rows, preds, c_by_model = [], {"date": df.date.to_numpy(), "id": df.id.to_numpy(),
                                   "label": y}, {}

    for name, col in BASELINES.items():
        score = df[col].to_numpy()
        flags = loho_score_flags(y, score, groups)
        row = metric_row(name, "baseline", col, y, score, flags)
        ci = bootstrap_ci(y, score, days, flags, rng)
        for key, (lo, hi) in ci.items():
            row[f"{key}_lo"], row[f"{key}_hi"] = lo, hi
        rows.append(row)
        preds[name] = score

    for name, cols in LOGIT_SETS.items():
        score, flags, chosen = loho_logit(df, cols)
        row = metric_row(name, "logit_loho", ", ".join(cols), y, score, flags)
        row["chosen_C"] = ", ".join(f"{c:g}" for c in sorted(set(chosen)))
        ci = bootstrap_ci(y, score, days, flags, rng)
        for key, (lo, hi) in ci.items():
            row[f"{key}_lo"], row[f"{key}_hi"] = lo, hi
        rows.append(row)
        preds[name] = score
        c_by_model[name] = chosen

    return pd.DataFrame(rows), pd.DataFrame(preds), c_by_model


# ---------------------------------------------------------------- timing checks
def alignment_table(rain):
    events = pd.read_csv(EVENTS, parse_dates=["date"])
    pos = set(zip(events.date.dt.date, events.hotspot_id))
    thresholds = pd.read_csv(config.OUT_DIR / "hotspot_thresholds.csv").set_index("id").i_crit_mm_h
    rows = []
    for name in ALIGNMENTS:
        df = daily_features(rain, name)
        df = df[df.date.dt.month.isin(WET_MONTHS)].copy()
        df["label"] = [int((d.date(), h) in pos) for d, h in zip(df.date, df.id)]
        df["physics_ratio"] = df.rain_peak_1h / df.id.map(thresholds)
        y = df.label.to_numpy()
        rows.append({"alignment": name, "window_hours": df.window_hours.iloc[0],
                     "n_pos": int(y.sum()),
                     "auc_peak": roc_auc_score(y, df.rain_peak_1h),
                     "auc_total": roc_auc_score(y, df.rain_total_window),
                     "auc_physics": roc_auc_score(y, df.physics_ratio),
                     "recall@5%FAR_peak": recall_at_far(y, df.rain_peak_1h, 0.05),
                     "recall@5%FAR_total": recall_at_far(y, df.rain_total_window, 0.05),
                     "recall@5%FAR_physics": recall_at_far(y, df.physics_ratio, 0.05)})
    return pd.DataFrame(rows)


def label_shift_table(table):
    """Shift every news date by N days and see which alignment matches best."""
    events = pd.read_csv(EVENTS, parse_dates=["date"])
    rows = []
    for shift in (-2, -1, 0, 1, 2):
        e = events.copy()
        e["date"] = e.date + pd.Timedelta(days=shift)
        pos = set(zip(e.date.dt.date, e.hotspot_id))
        y = np.array([int((d.date(), h) in pos) for d, h in zip(table.date, table.id)])
        rows.append({"label_shift_days": shift, "n_pos": int(y.sum()),
                     "auc_peak": roc_auc_score(y, table.rain_peak_1h),
                     "auc_physics": roc_auc_score(y, table.physics_ratio),
                     "recall@5%FAR_physics": recall_at_far(y, table.physics_ratio, 0.05)})
    return pd.DataFrame(rows)


def rule_table(df):
    y = df.label.to_numpy()
    rules = {
        "40 mm/h (raw)": df.rain_peak_1h >= 40,
        "40 mm/h (bias-corrected)": df.rain_peak_1h_corrected >= 40,
        "physics threshold (raw)": df.physics_ratio >= 1.0,
        "physics threshold (bias-corrected)": df.physics_ratio_corrected >= 1.0,
    }
    rows = []
    for name, flag in rules.items():
        flag = flag.to_numpy()
        rows.append({"rule": name, "hits": int((flag & (y == 1)).sum()), "floods": int((y == 1).sum()),
                     "recall": float((flag & (y == 1)).sum() / (y == 1).sum()),
                     "false_alarm_hotspot_days": int((flag & (y == 0)).sum()),
                     "false_alarm_rate": float((flag & (y == 0)).sum() / (y == 0).sum())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- main
def main():
    config.OUT_DIR.mkdir(exist_ok=True)
    hotspots = pd.read_csv(config.HOTSPOTS_CSV)
    to_utm = Transformer.from_crs("EPSG:4326", config.CRS_METRIC, always_xy=True)
    hotspots["x"], hotspots["y"] = to_utm.transform(hotspots.lon.values, hotspots.lat.values)
    nodes = pd.read_csv(NODES)

    print("[1/4] mapping hotspots to GNN graph nodes")
    mapping = snap_hotspots(hotspots, nodes)
    mapping.to_csv(config.OUT_DIR / "hotspot_graph_nodes.csv", index=False)
    print(mapping[["id", "node_id", "node_type", "snap_dist_m"]].to_string(index=False))

    print("[2/4] rain and risk.py thresholds")
    rain = hourly_rain(hotspots)
    thresholds = threshold_table(hotspots)
    thresholds.to_csv(config.OUT_DIR / "hotspot_thresholds.csv", index=False)
    bias_file = config.OUT_DIR / "backtest_rain_bias.csv"
    bias = float(pd.read_csv(bias_file).ratio.median()) if bias_file.exists() else BIAS_FALLBACK
    print(thresholds[["id", "i_crit_mm_h", "threshold_source"]].to_string(index=False))

    print("[3/4] building the hotspot-day table")
    table = build_table(hotspots, mapping, thresholds, rain, bias)
    table.to_csv(config.OUT_DIR / "label_table.csv", index=False)
    print(f"  {len(table):,} hotspot-days, {int(table.label.sum())} positive, "
          f"{int(table[table.wet_season].label.sum())} positive in Apr-Dec")

    print("[4/4] leave-one-hotspot-out comparison")
    eval_df = table[table.wet_season].copy()
    rng = np.random.default_rng(config.RANDOM_SEED)
    metrics, preds, _ = evaluate(eval_df, rng)
    metrics.round(4).to_csv(config.OUT_DIR / "label_table_metrics.csv", index=False)
    pred_cols = [c for c in preds.columns if c not in ("date", "id", "label")]
    preds[pred_cols] = preds[pred_cols].round(4)
    preds.to_csv(config.OUT_DIR / "label_table_oof_predictions.csv", index=False)
    alignment_table(rain).round(4).to_csv(config.OUT_DIR / "label_table_alignment.csv", index=False)
    label_shift_table(eval_df).round(4).to_csv(config.OUT_DIR / "label_table_label_shift.csv", index=False)
    rule_table(eval_df).round(4).to_csv(config.OUT_DIR / "label_table_rules.csv", index=False)

    cols = ["model", "auc", "ap", "recall@5%FAR", "recall@5%FAR_train_thr", "recall@1%FAR"]
    print(metrics[cols].round(3).to_string(index=False))
    print(f"done -> {config.OUT_DIR}")


if __name__ == "__main__":
    main()
