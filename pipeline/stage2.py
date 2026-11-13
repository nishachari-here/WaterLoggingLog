"""Stage 2 (when): which wards report flooding on which day, given the rain?

One sample is a ward on a day. The label is 1 when the ward has at least one "water stagnation"
complaint that day. Models are trained on 2020-2023 and tested on 2024 to June 2025, which they never see.

Feature groups are added one at a time so the table shows what each adds over a plain rain rule.
"Within-day AUC" is scored only across wards on days when 10 or more wards reported flooding: it
measures whether the model picks the right wards, which rain alone cannot do.

Before final results: tune on 2023 only (train 2020-2022) and touch the 2024-25 test set once.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config
from pipeline import labels, rain_history

TEST_FROM = "2024-01-01"
TABLE = config.PROCESSED_DIR / "ward_days.pkl"
RAIN = ["rain", "rain_lag1", "rain_3d", "rain_ante7", "peak", "peak_2d"]
STATIC = ["n_flood_pts", "flood_pts_per_km2", "hand_mean", "hand_lt2_frac", "twi_mean", "depression_depth_mean",
          "terrain_score_mean", "area_km2"]
FEATURE_SETS = {
    "rain only (logistic)": (RAIN, "lr"),
    "rain only (boosting)": (RAIN, "gb"),
    "rain + soil moisture": (RAIN + ["sm_prev"], "gb"),
    "rain + ward terrain + BBMP flood points": (RAIN + STATIC, "gb"),
    "+ drain complaints, last 30 days": (RAIN + STATIC + ["drain_30d"], "gb"),
    "+ soil moisture + month": (RAIN + STATIC + ["drain_30d", "sm_prev", "month"], "gb"),
}


def ward_static(wards):
    """Per ward: count of official flood points and terrain averages."""
    pts = labels.flood_points(merge_m=0).to_crs("EPSG:4326")
    hits = gpd.sjoin(pts, wards[["ward", "geometry"]], predicate="within").ward.value_counts()
    out = wards[["ward", "area_km2"]].copy()
    out["n_flood_pts"] = out.ward.map(hits).fillna(0)
    out["flood_pts_per_km2"] = out.n_flood_pts / out.area_km2
    metric = wards.to_crs(config.CRS_METRIC)
    for name in ["hand", "twi", "depression_depth", "terrain_score"]:
        with rasterio.open(config.PROCESSED_DIR / f"{name}.tif") as src:
            cells = [rasterio.mask.mask(src, [g], crop=True, filled=False)[0].compressed() for g in metric.geometry]
        out[f"{name}_mean"] = [float(c.mean()) for c in cells]
        if name == "hand":
            out["hand_lt2_frac"] = [float((c < 2).mean()) for c in cells]
    return out


def build_table():
    wards = labels.wards()
    wards["cell"] = [rain_history.cell_of(a, o) for a, o in zip(wards.lat, wards.lon)]
    df = labels.ward_days()
    by_ward = df.groupby("ward", sort=False)
    # shift(1): only complaints from earlier days, so nothing from the day being predicted leaks in
    df["drain_30d"] = by_ward.n_drain.transform(lambda s: s.shift(1).rolling(30, min_periods=1).sum()).fillna(0)
    df = df.merge(wards[["ward", "zone", "cell"]], on="ward")
    df = df.merge(rain_history.daily_features(wards), on=["cell", "date"], how="left")
    df = df.merge(ward_static(wards), on="ward")
    df["month"] = df.date.dt.month
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_pickle(TABLE)
    return df


def recall_at_far(y, s, far=0.05):
    return float((s[y == 1] > np.quantile(s[y == 0], 1 - far)).mean())


def within_day_auc(test, score):
    aucs = [roc_auc_score(day.y, day.s) for _, day in test.assign(s=score).groupby("date")
            if 10 <= day.y.sum() < len(day)]
    return float(np.mean(aucs)), len(aucs)


def _model(kind):
    if kind == "lr":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    return HistGradientBoostingClassifier(max_depth=5, learning_rate=0.05, max_iter=400, l2_regularization=1.0,
                                          random_state=0)


def run():
    df = build_table()
    train, test = df[df.date < TEST_FROM], df[df.date >= TEST_FROM]
    y = test.y.to_numpy()
    scores = {"rule: 2-day rain total": (test.rain + test.rain_lag1).to_numpy()}
    for name, (cols, kind) in FEATURE_SETS.items():
        scores[name] = _model(kind).fit(train[cols], train.y).predict_proba(test[cols])[:, 1]
    rows = []
    for name, s in scores.items():
        wd, n_days = within_day_auc(test, s)
        rows.append({"model": name, "auc": roc_auc_score(y, s), "avg_precision": average_precision_score(y, s),
                     "recall_at_5pct_far": recall_at_far(y, s), "within_day_auc": wd, "flood_days": n_days})
    table = pd.DataFrame(rows).round(3)
    config.OUT_DIR.mkdir(exist_ok=True)
    table.to_csv(config.OUT_DIR / "stage2_metrics.csv", index=False)
    info = {"wards": df.ward.nunique(), "ward_days": len(df), "positives": int(df.y.sum()),
            "train": len(train), "train_pos": int(train.y.sum()), "test": len(test), "test_pos": int(y.sum())}
    return table, info
