"""Real flood labels from the OpenCity copies in data/opencity (BBMP and KSRSAC records, public domain).

Two label sets:
  flood_points()  399 official flood-vulnerable / flood-prone / low-lying points -> Stage 1 (where)
  ward_days()     one row per ward per day, y = 1 if the ward has a "water stagnation" complaint
                  that day -> Stage 2 (when)

The complaints name wards from the 198-ward scheme, spelled differently from the ward map, so
ward_name_map() matches them: exact, then a few manual fixes, then fuzzy.
"""
import difflib
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config

OPENCITY = config.ROOT / "data" / "opencity"
FLOOD_LAYERS = ["flood_vulnerable", "flood_prone", "low_lying"]
FLOOD_SUBCAT = "water stagnation"
# Complaints about the drains themselves: a real, dated proxy for blockage.
DRAIN_SUBCATS = ["road side drains", "garbage thrown in storm water drain", "maintenance of swd",
                 "sewerage water left in swd"]
FIRST_DAY, LAST_DAY = "2020-02-08", "2025-06-19"
NO_WARD = "NON Ward"  # placeholder on complaints that were never assigned to a ward

# Complaint ward name -> ward map name, where fuzzy matching fails or picks the wrong ward.
# The last two are matched by elimination (ward 3 is "Atturu" in the 2015 map and "Someshwara" in
# the 2022 one; Subedarapalya is the only name left for Kadu Malleshwar), so treat them as less certain.
MANUAL_WARDS = {
    "H.M.T": "HMT Ward",
    "Hoodi": "Hudi",
    "Rajamahal": "Rajamahal Guttahalli",
    "Moodalapalya": "Mudalapalya",
    "Someshwara": "Atturu",
    "Subedarapalya": "Kadu Malleshwar Ward",
}


def _norm(s):
    return re.sub(r"[^a-z]", "", str(s).lower())


def wards():
    """198 BBMP wards (2015 map) with cleaned zone name, area and centroid."""
    w = gpd.read_file(OPENCITY / "wards_2015.kml")[["Ward_Name", "Zone", "geometry"]]
    w = w.rename(columns={"Ward_Name": "ward", "Zone": "zone"})
    w["zone"] = (w.zone.str.replace(r"[^A-Za-z ]", "", regex=True).str.strip()
                 .replace({"Rajarajeswari Nagar": "Rajarajeshwari Nagar"}))
    metric = w.to_crs(config.CRS_METRIC)
    w["area_km2"] = metric.area / 1e6
    c = metric.centroid.to_crs("EPSG:4326")
    w["lon"], w["lat"] = c.x, c.y
    return w


def flood_points(merge_m=100):
    """Official flood points in metric CRS, inside the BBMP boundary, merged when closer than merge_m."""
    pts = pd.concat([gpd.read_file(OPENCITY / f"{f}.kml")[["geometry"]].assign(layer=f) for f in FLOOD_LAYERS],
                    ignore_index=True)
    pts = gpd.GeoDataFrame(pts, crs="EPSG:4326").to_crs(config.CRS_METRIC)
    city = wards().to_crs(config.CRS_METRIC).union_all()
    pts = pts[pts.within(city)].reset_index(drop=True)
    xy = np.c_[pts.geometry.x, pts.geometry.y]
    keep = np.ones(len(xy), bool)
    for i, j in sorted(cKDTree(xy).query_pairs(merge_m)):
        if keep[i]:
            keep[j] = False
    return pts[keep].reset_index(drop=True)


def ward_name_map(complaint_names, map_names):
    """{complaint ward name: ward map name}. Raises if two complaint names land on one ward."""
    by_norm = {_norm(n): n for n in map_names}
    out = {}
    for name in complaint_names:
        if name in MANUAL_WARDS:
            out[name] = MANUAL_WARDS[name]
        elif _norm(name) in by_norm:
            out[name] = by_norm[_norm(name)]
        else:
            m = difflib.get_close_matches(_norm(name), list(by_norm), n=1, cutoff=0.75)
            out[name] = by_norm[m[0]] if m else None
    hits = pd.Series([v for v in out.values() if v]).value_counts()
    if (hits > 1).any() or None in out.values():
        raise ValueError(f"ward matching is not one-to-one: {hits[hits > 1].to_dict()}, "
                         f"unmatched {[k for k, v in out.items() if v is None]}")
    return out


def grievances():
    """All complaints 2020-2025 with ward (ward map spelling), date and lower-cased sub-category."""
    g = pd.concat([pd.read_csv(f, usecols=["Complaint ID", "Sub Category", "Grievance Date", "Ward Name"],
                               low_memory=False) for f in sorted(OPENCITY.glob("griev_*.csv"))], ignore_index=True)
    g = g.dropna(subset=["Ward Name"])
    g = g[g["Ward Name"] != NO_WARD]
    mapping = ward_name_map(sorted(g["Ward Name"].unique()), wards().ward)
    # The export's hour runs 1-12 with no AM/PM, so only the date is used.
    return pd.DataFrame({"id": g["Complaint ID"], "ward": g["Ward Name"].map(mapping),
                         "date": pd.to_datetime(g["Grievance Date"]).dt.normalize(),
                         "sub": g["Sub Category"].astype(str).str.strip().str.lower()})


def ward_days():
    """Ward x day table: n_flood, n_drain, n_other complaint counts and the label y."""
    g = grievances()
    idx = pd.MultiIndex.from_product([wards().ward, pd.date_range(FIRST_DAY, LAST_DAY)], names=["ward", "date"])

    def daily(mask):
        return g[mask].groupby(["ward", "date"]).size().reindex(idx, fill_value=0)

    df = pd.DataFrame({"n_flood": daily(g["sub"].eq(FLOOD_SUBCAT)), "n_drain": daily(g["sub"].isin(DRAIN_SUBCATS)),
                       "n_other": daily(~g["sub"].eq(FLOOD_SUBCAT))}).reset_index()
    df["y"] = (df.n_flood > 0).astype(int)
    return df
