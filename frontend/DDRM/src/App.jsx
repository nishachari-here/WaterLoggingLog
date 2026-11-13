/**
 * MIT License
 * Copyright (c) 2026 Adithya Parameswaran / RVCE Waterlogging Early-Warning System
 */

import { useState, useEffect, useRef, useCallback } from "react";
import MapView from "./components/MapView";
import ScenarioPanel from "./components/ScenarioPanel";
import StatusBar from "./components/StatusBar";
import RouteTab from "./pages/RouteTab";
import HotspotsTab from "./pages/HotspotsTab";
import DrainsTab from "./pages/DrainsTab";
import "leaflet/dist/leaflet.css";

export default function App() {
  const [meta, setMeta] = useState({
    places: [],
    culverts: [],
    bias_factor: 1.7,
  });

  const [query, setQuery] = useState({
    mode: "scenario",
    date: "2025-05-19",
    rain_today: 30,
    rain_later: 0,
    later_day: 2,
    correct_bias: true,
    blockage: 0.2,
    culvert: null,
    culvert_blockage: 0.9,
    origin: "Koramangala (Forum)",
    dest: "Marathahalli",
  });

  const [assessment, setAssessment] = useState(null);
  const [replay, setReplay] = useState(null);
  const [replayIdx, setReplayIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [activeTab, setActiveTab] = useState("route");
  const [loading, setLoading] = useState(false);
  const [toastMsg, setToastMsg] = useState("");
  const [fitPending, setFitPending] = useState(true);

  const [layerVisibility, setLayerVisibility] = useState({
    drains: false,
    zones: true,
    routes: true,
    hotspots: true,
  });

  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("theme") || "light";
    } catch {
      return "light";
    }
  });

  // Sync theme
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* localStorage may be unavailable in private mode */
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const showToast = useCallback((msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(""), 4000);
  }, []);

  // Fetch meta on mount
  useEffect(() => {
    let active = true;
    fetch("/api/meta")
      .then((res) => {
        if (!res.ok) throw new Error("Could not load system metadata");
        return res.json();
      })
      .then((data) => {
        if (!active) return;
        setMeta(data);
        setQuery((q) => {
          const originExists = data.places?.some((p) => p.name === q.origin);
          const destExists = data.places?.some((p) => p.name === q.dest);
          return {
            ...q,
            origin: originExists ? q.origin : data.places?.[0]?.name || q.origin,
            dest: destExists ? q.dest : data.places?.[1]?.name || q.dest,
          };
        });
      })
      .catch((err) => {
        console.error("Meta fetch error:", err);
        showToast("Backend connection failed. Ensure server.py is running.");
      });

    return () => {
      active = false;
    };
  }, [showToast]);

  // Debounced assessment
  const abortControllerRef = useRef(null);
  const debounceTimerRef = useRef(null);

  const fetchAssessment = useCallback((currentQuery) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentQuery),
      signal: abortControllerRef.current.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Assessment failed: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        setAssessment(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          console.error("Assessment error:", err);
          showToast(err.message || "Failed to assess risk.");
          setLoading(false);
        }
      });
  }, [showToast]);

  const fetchReplay = useCallback((currentQuery) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    fetch("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentQuery),
      signal: abortControllerRef.current.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Replay failed: ${res.statusText}`);
        return res.json();
      })
      .then((data) => {
        setReplay(data);
        setReplayIdx(0);
        setPlaying(false);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          console.error("Replay error:", err);
          showToast(err.message || "Failed to load storm replay.");
          setLoading(false);
        }
      });
  }, [showToast]);

  // Trigger assessment whenever query changes
  useEffect(() => {
    if (!meta.places || meta.places.length === 0) return;

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      if (query.mode === "replay") {
        fetchReplay(query);
      } else {
        fetchAssessment(query);
      }
    }, 120);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query, meta, fetchAssessment, fetchReplay]);

  // Advance the replay timeline while playing
  useEffect(() => {
    if (!playing || query.mode !== "replay" || !replay) return;
    const timer = setInterval(() => {
      setReplayIdx((i) => (i + 1) % replay.frames.length);
    }, 700);
    return () => clearInterval(timer);
  }, [playing, query.mode, replay]);

  const frame = query.mode === "replay" && replay ? replay.frames[replayIdx] : null;
  const shown = frame
    ? {
        hotspots: frame.hotspots,
        counts: frame.counts,
        rule_alerts: frame.rule_alerts,
        watch_count: 0,
        route: replay.route,
        zones: replay.zones,
        blocked_segment: replay.blocked_segment,
        clear_first: replay.clear_first,
      }
    : assessment;

  const handleQueryChange = (partial) => {
    if (partial.origin !== undefined || partial.dest !== undefined) {
      setFitPending(true);
    }
    setQuery((prev) => ({ ...prev, ...partial }));
  };

  const handleToggleLayer = (layerName, value) => {
    setLayerVisibility((prev) => ({ ...prev, [layerName]: value }));
  };

  const handleSelectHotspot = (id) => {
    setSelectedId(id);
    setActiveTab("hotspots");
  };

  return (
    <div className="app-container" style={{ height: "100%", width: "100%", position: "relative" }}>
      {/* Top progress bar */}
      <div className={`progress ${loading ? "on" : "done"}`} />

      {/* Floating Status Bar */}
      <StatusBar
        counts={shown?.counts}
        watchCount={shown?.watch_count}
        ruleAlerts={shown?.rule_alerts}
        totalHotspots={shown?.hotspots?.length}
      />

      {/* Main interactive map */}
      <MapView
        hotspots={shown?.hotspots}
        zones={shown?.zones}
        route={shown?.route}
        blockedSegment={shown?.blocked_segment}
        places={meta.places}
        originName={query.origin}
        destName={query.dest}
        selectedId={selectedId}
        onSelectHotspot={handleSelectHotspot}
        layerVisibility={layerVisibility}
        fitPending={fitPending}
        onFitted={() => setFitPending(false)}
      />

      {/* Left panel: Scenario & Control Parameters */}
      <ScenarioPanel
        query={query}
        onChange={handleQueryChange}
        places={meta.places}
        culverts={meta.culverts}
        biasFactor={meta.bias_factor}
        forecast={assessment?.forecast}
        replay={replay}
        replayIdx={replayIdx}
        playing={playing}
        onReplayIndex={(i) => setReplayIdx(i)}
        onReplayToggle={() => setPlaying((p) => !p)}
        layerVisibility={layerVisibility}
        onToggleLayer={handleToggleLayer}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Right panel: Route, Hotspots, and Drain Clearance Inspector */}
      <aside className="panel right card" aria-label="Inspector">
        <nav className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "route"}
            onClick={() => setActiveTab("route")}
          >
            Route Detour
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "hotspots"}
            onClick={() => setActiveTab("hotspots")}
          >
            Hotspots ({shown?.hotspots?.length ?? "–"})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "priorities"}
            onClick={() => setActiveTab("priorities")}
          >
            Clear Drains
          </button>
        </nav>

        <div className="scroll">
          {activeTab === "route" && (
            <RouteTab
              route={shown?.route}
              originName={query.origin}
              destName={query.dest}
            />
          )}
          {activeTab === "hotspots" && (
            <HotspotsTab
              hotspots={shown?.hotspots}
              selectedId={selectedId}
              onSelectHotspot={handleSelectHotspot}
            />
          )}
          {activeTab === "priorities" && (
            <DrainsTab clearFirst={shown?.clear_first} />
          )}
        </div>
      </aside>

      {/* Toast popup */}
      {toastMsg && <div className="toast">{toastMsg}</div>}
    </div>
  );
}
