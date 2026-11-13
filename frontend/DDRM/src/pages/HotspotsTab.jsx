import { useState, useMemo } from "react";

export default function HotspotsTab({ hotspots = [], selectedId, onSelectHotspot }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all"); // 'all' | 'red' | 'amber' | 'green' | 'watch'

  const filtered = useMemo(() => {
    return hotspots.filter((h) => {
      if (filter === "red" && h.status !== "red") return false;
      if (filter === "amber" && h.status !== "amber") return false;
      if (filter === "green" && h.status !== "green") return false;
      if (filter === "watch" && (!h.watch || h.watch.length === 0)) return false;

      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesName = h.name.toLowerCase().includes(q);
        const matchesBottleneck = (h.bottleneck || "").toLowerCase().includes(q);
        const matchesKind = (h.kind || "").toLowerCase().includes(q);
        return matchesName || matchesBottleneck || matchesKind;
      }
      return true;
    });
  }, [hotspots, filter, search]);

  const counts = useMemo(() => {
    return {
      all: hotspots.length,
      red: hotspots.filter((h) => h.status === "red").length,
      amber: hotspots.filter((h) => h.status === "amber").length,
      green: hotspots.filter((h) => h.status === "green").length,
      watch: hotspots.filter((h) => h.watch && h.watch.length > 0).length,
    };
  }, [hotspots]);

  return (
    <div className="tab">
      <input
        type="search"
        className="search-input"
        placeholder="Filter hotspots by name, bottleneck..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <div className="hs-filters">
        <button
          type="button"
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          All ({counts.all})
        </button>
        <button
          type="button"
          className={filter === "red" ? "active" : ""}
          onClick={() => setFilter("red")}
        >
          Red ({counts.red})
        </button>
        <button
          type="button"
          className={filter === "amber" ? "active" : ""}
          onClick={() => setFilter("amber")}
        >
          Amber ({counts.amber})
        </button>
        <button
          type="button"
          className={filter === "green" ? "active" : ""}
          onClick={() => setFilter("green")}
        >
          Clear ({counts.green})
        </button>
        <button
          type="button"
          className={filter === "watch" ? "active" : ""}
          onClick={() => setFilter("watch")}
        >
          Watch ({counts.watch})
        </button>
      </div>

      <p className="list-note">
        Ranked by load ratio (Rain / I<sub>crit</sub>). Click to center map:
      </p>

      <div style={{ maxHeight: "calc(100vh - 310px)", overflowY: "auto" }}>
        {filtered.map((h) => {
          const isSelected = h.id === selectedId;
          const hasWatch = h.watch && h.watch.length > 0;
          return (
            <div
              key={h.id}
              className={`hs ${h.status} ${isSelected ? "active" : ""}`}
              onClick={() => onSelectHotspot(h.id)}
            >
              <div className="dot"></div>
              <div className="name">{h.name}</div>
              <div className="ratio">{h.ratio.toFixed(2)}×</div>
              <div className="detail">
                Rain <b>{h.rain}</b> mm/h · Crit{" "}
                <b>{h.threshold ?? "–"}</b>
                {h.threshold == null ? " (no drain path)" : " mm/h"}
                {h.bottleneck ? ` · Choke: ${h.bottleneck}` : ""}
                {hasWatch && (
                  <span style={{ color: "var(--watch)", marginLeft: "6px", fontWeight: 600 }}>
                    ⚠️ Watch (in {h.watch.join(", ")}d)
                  </span>
                )}
              </div>
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div className="muted" style={{ padding: "16px 8px" }}>
            No hotspots matching the selected filter.
          </div>
        )}
      </div>
    </div>
  );
}

