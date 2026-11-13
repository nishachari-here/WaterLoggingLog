"""Methodology step 4 (physics part): rain -> runoff vs drain capacity on the drain graph.

For every drain segment, runoff is the rational method Q = 0.278*C*i*A (A from the DEM). Capacity
comes from the field log where a hotspot has been measured (Manning), otherwise from a placeholder
design rule: a segment draining 1 km2 copes with I_REF mm/h, and capacity grows as A^0.85 (big
channels are relatively undersized, the usual hydraulic-geometry pattern). Blockage scales capacity
down by (1 - b).

A hotspot floods when any segment within BACKWATER_M downstream of it overflows, because a
choked culvert backs water up to the street. Lakes act as storage, so the walk stops at a lake.
On this D8 tree each hotspot has exactly one path to its outlet, so the min-cut between the hotspot
and the outlet is simply the lowest-capacity segment on that path: the "bottleneck".

Each hotspot ends up with a critical intensity i_crit (mm/h): the rain at which its bottleneck overflows.
"""
import pandas as pd

import config
from pipeline import capacity, drain_graph

C = capacity.RUNOFF_C["dense_urban"]
I_REF = 50.0          # mm/h a 1 km2 drain copes with (placeholder until field data)
EXPONENT = 0.85
BACKWATER_M = 800
DEFAULT_LOCAL_KM2 = 0.5
FIELD_LOG = config.ROOT / "data" / "field" / "field_log.csv"
GENERIC_ROADS = {"Service Road", "primary", "secondary", "tertiary", "trunk", "motorway",
                 "primary_link", "secondary_link", "tertiary_link", "trunk_link", "motorway_link"}


def design_capacity(area_km2):
    return 0.278 * C * I_REF * area_km2 ** EXPONENT


def downstream_path(g, node):
    """Segments a hotspot's water passes through before backwater stops mattering."""
    path, dist, cur = [], 0.0, node
    while dist < BACKWATER_M and g.out_degree(cur):
        nxt = next(iter(g.successors(cur)))
        if g.edges[cur, nxt]["in_lake"]:
            break
        path.append((cur, nxt))
        dist += g.edges[cur, nxt]["length_m"]
        cur = nxt
    return path


def field_capacities(g, hot_nodes):
    """Measured capacity (m3/s) and local area for the first segment below each measured hotspot."""
    if not FIELD_LOG.exists():
        return {}
    log = pd.read_csv(FIELD_LOG).dropna(subset=["drain_width_m", "drain_depth_m"])
    out = {}
    for hid, rows in log.groupby("hotspot_id"):
        if hid not in hot_nodes:
            continue
        r = rows.iloc[-1]  # latest visit
        lining = "silted" if r.get("garbage_score_0to3", 0) >= 2 else (r.get("lining") or "concrete")
        slope = r["bed_slope_pct"] / 100 if pd.notna(r.get("bed_slope_pct")) else 0.002
        q = capacity.manning_capacity(r.drain_width_m, r.drain_depth_m, r.get("silt_depth_m", 0) or 0,
                                      slope=slope, lining=lining if lining in capacity.ROUGHNESS else "concrete")
        node = hot_nodes[hid]
        local = r.get("local_catchment_km2")
        area = local if pd.notna(local) else min(g.nodes[node]["area_km2"], DEFAULT_LOCAL_KM2)
        out[hid] = (q, area)
    return out


def segment_label(g, u, v, near=None):
    roads = [r for r in g.edges[u, v]["culverts"] if r not in GENERIC_ROADS]
    what = f"Culvert under {', '.join(roads[:2])}" if roads else (
        "Culvert under arterial road" if g.edges[u, v]["culverts"] else "Open drain segment")
    return f"{what} (below {near})" if near else what


class DrainModel:
    def __init__(self):
        self.g = drain_graph.load()
        self.hot_nodes = drain_graph.hotspot_nodes(self.g)
        hs = pd.read_csv(config.HOTSPOTS_CSV).set_index("id")
        self.names = hs["name"].to_dict()
        self.paths = {h: downstream_path(self.g, n) for h, n in self.hot_nodes.items()}
        self.field = field_capacities(self.g, self.hot_nodes)

    def i_crit_segment(self, hid, idx, u, v, blockage):
        d = self.g.edges[u, v]
        if idx == 0 and hid in self.field:
            q, area = self.field[hid]  # measured drain: silt is already in Manning, no extra blockage
            return q / (0.278 * C * area)
        cap = design_capacity(d["area_km2"]) * (1 - blockage.get((u, v), blockage["default"]))
        return cap / (0.278 * C * d["area_km2"])

    def thresholds(self, blockage):
        """Per hotspot: critical intensity and the bottleneck segment that sets it."""
        rows = []
        for hid, path in self.paths.items():
            vals = [(self.i_crit_segment(hid, i, u, v, blockage), (u, v)) for i, (u, v) in enumerate(path)]
            i_crit, (u, v) = min(vals) if vals else (float("inf"), (None, None))
            rows.append({"id": hid, "name": self.names[hid], "i_crit_mm_h": i_crit, "bottleneck": (u, v),
                         "bottleneck_label": segment_label(self.g, u, v) if u is not None else "-",
                         "capacity_source": "field (Manning)" if hid in self.field else "placeholder rule"})
        return pd.DataFrame(rows)

    def assess(self, rain, blockage):
        """rain: mm/h, either one number or {hotspot_id: mm/h}. Returns status per hotspot."""
        t = self.thresholds(blockage)
        t["rain_mm_h"] = [rain.get(h, 0.0) if isinstance(rain, dict) else rain for h in t.id]
        t["load_ratio"] = t.rain_mm_h / t.i_crit_mm_h
        t["status"] = pd.cut(t.load_ratio, [-1, 0.8, 1.0, float("inf")], labels=["green", "amber", "red"])
        hs = pd.read_csv(config.HOTSPOTS_CSV)[["id", "lat", "lon", "kind"]]
        return t.merge(hs, on="id")

    def watch_days(self, outlook, blockage):
        """outlook: {days_ahead: rain}. Returns {hotspot_id: [days on which it would be red]}."""
        watch = {h: [] for h in self.hot_nodes}
        for day, r in sorted(outlook.items()):
            later = self.assess(r, blockage)
            for h in later[later.status == "red"].id:
                watch[h].append(day)
        return watch

    def clear_first(self, blockage, top=10):
        """Rank segments on hotspot paths by how much clearing them raises hotspot thresholds."""
        base = self.thresholds(blockage).set_index("id").i_crit_mm_h
        candidates = {}
        for hid, path in self.paths.items():
            for e in path:
                candidates.setdefault(e, []).append(hid)
        rows = []
        for e, hids in candidates.items():
            cleared = {**blockage, e: 0.0}
            after = self.thresholds(cleared).set_index("id").i_crit_mm_h
            gain = (after - base)[hids].clip(lower=0)
            if gain.sum() > 0.05:
                rows.append({"segment": e, "label": segment_label(self.g, *e, near=self.names[hids[0]]),
                             "hotspots_helped": ", ".join(self.names[h] for h in hids if gain[h] > 0.05),
                             "threshold_gain_mm_h": round(gain.sum(), 1),
                             "upstream_km2": round(self.g.edges[e]["area_km2"], 2)})
        out = pd.DataFrame(rows)
        return out.sort_values("threshold_gain_mm_h", ascending=False).head(top) if len(out) else out

    def culvert_options(self):
        """Road-crossing segments on hotspot paths, for the 'what if this culvert is blocked' picker."""
        opts = {}
        for hid, path in self.paths.items():
            for e in path:
                if self.g.edges[e]["culverts"] and e not in opts:
                    opts[e] = segment_label(self.g, *e, near=self.names[hid])
        return opts

    def segment_lonlat(self, e):
        a, b = self.g.nodes[e[0]], self.g.nodes[e[1]]
        return [(a["lat"], a["lon"]), (b["lat"], b["lon"])]


def rule_baseline(rain, threshold=40.0):
    """The rainfall-threshold baseline: one city-wide number, same answer for every hotspot."""
    return rain >= threshold
