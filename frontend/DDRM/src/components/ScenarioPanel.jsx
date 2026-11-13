import { useState } from "react";

const EARTH_KM = 6371;
const toRad = (d) => (d * Math.PI) / 180;

function distanceKm(aLat, aLon, bLat, bLon) {
  const dLat = toRad(bLat - aLat);
  const dLon = toRad(bLon - aLon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(h));
}

export default function ScenarioPanel({
  query,
  onChange,
  places = [],
  culverts = [],
  biasFactor = 1.0,
  forecast = null,
  replay = null,
  replayIdx = 0,
  playing = false,
  onReplayIndex,
  onReplayToggle,
  layerVisibility,
  onToggleLayer,
  theme,
  onToggleTheme,
}) {
  const getIntensity = (mm) => {
    if (mm === 0) return { label: "No rain", bg: "var(--surface-2)", color: "var(--muted)" };
    if (mm < 10) return { label: "Moderate", bg: "color-mix(in srgb, var(--green) 15%, var(--surface))", color: "var(--green)" };
    if (mm < 30) return { label: "Heavy", bg: "color-mix(in srgb, var(--amber) 18%, var(--surface))", color: "var(--amber)" };
    if (mm < 50) return { label: "Very heavy", bg: "color-mix(in srgb, var(--red) 15%, var(--surface))", color: "var(--red)" };
    return { label: "Extreme", bg: "var(--red)", color: "#fff" };
  };

  const intensity = getIntensity(query.rain_today);

  const [locating, setLocating] = useState(false);
  const [geoMsg, setGeoMsg] = useState("");

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setGeoMsg("This browser does not support geolocation.");
      return;
    }
    setLocating(true);
    setGeoMsg("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        let best = null;
        let bestKm = Infinity;
        for (const p of places) {
          const km = distanceKm(latitude, longitude, p.lat, p.lon);
          if (km < bestKm) {
            bestKm = km;
            best = p;
          }
        }
        setLocating(false);
        if (best) {
          onChange({ origin: best.name });
          setGeoMsg(`Start set to ${best.name} (${bestKm.toFixed(1)} km from you).`);
        }
      },
      (err) => {
        setLocating(false);
        setGeoMsg(
          err.code === 1
            ? "Location permission denied. Allow it in the browser to use GPS."
            : "Could not get your location. Try again."
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  const handleSwap = () => {
    onChange({
      origin: query.dest,
      dest: query.origin,
    });
  };

  return (
    <aside className="panel left card" aria-label="Controls">
      <div className="brand">
        <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 3c4.6 6 9 11.4 9 16.2A9 9 0 0 1 7 19.2C7 14.4 11.4 9 16 3z" fill="currentColor" />
          <path d="M11.5 20.5c1.6 1.6 3.4 1.6 5 0s3.4-1.6 5 0" stroke="#fff" stroke-width="1.8" fill="none" strokeLinecap="round" />
        </svg>
        <div className="brand-text">
          <h1>Early-Warning</h1>
          <p>Bengaluru flood hotspots</p>
        </div>
        <button
          className="icon-btn"
          aria-label="Toggle theme"
          title="Toggle light / dark mode"
          onClick={onToggleTheme}
        >
          {theme === "dark" ? (
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58c-.39-.39-1.03-.39-1.41 0s-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37c-.39-.39-1.03-.39-1.41 0s-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41l-1.06-1.06zm1.06-10.96c.39-.39.39-1.03 0-1.41s-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36c.39-.39.39-1.03 0-1.41s-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z"/>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          )}
        </button>
      </div>

      <div className="scroll">
        <section>
          <h2>Rain</h2>
          <div className="segmented" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={query.mode === "scenario"}
              onClick={() => onChange({ mode: "scenario" })}
            >
              Scenario
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={query.mode === "live"}
              onClick={() => onChange({ mode: "live" })}
            >
              Live forecast
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={query.mode === "replay"}
              onClick={() => onChange({ mode: "replay" })}
            >
              Storm replay
            </button>
          </div>

          {query.mode === "scenario" ? (
            <div>
              <label className="field">
                <span className="field-head">
                  Rain today <output>{query.rain_today} mm/h</output>
                </span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={query.rain_today}
                  style={{ "--fill": `${(query.rain_today / 100) * 100}%` }}
                  onChange={(e) => onChange({ rain_today: Number(e.target.value) })}
                />
                <span
                  className="intensity"
                  style={{ background: intensity.bg, color: intensity.color }}
                >
                  {intensity.label}
                </span>
              </label>

              <label className="field">
                <span className="field-head">
                  Rain expected later{" "}
                  <output>{query.rain_later ? `${query.rain_later} mm/h` : "none"}</output>
                </span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={query.rain_later}
                  style={{ "--fill": `${(query.rain_later / 100) * 100}%` }}
                  onChange={(e) => onChange({ rain_later: Number(e.target.value) })}
                />
              </label>

              <div className="field">
                <span className="field-head">Later storm timing</span>
                <div className="chips" role="group">
                  {[1, 2, 3].map((d) => (
                    <button
                      key={d}
                      type="button"
                      aria-checked={query.later_day === d}
                      onClick={() => onChange({ later_day: d })}
                    >
                      Day {d}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : query.mode === "replay" ? (
            <div>
              <label className="field">
                <span className="field-head">Storm date</span>
                <input
                  type="date"
                  min="2020-01-01"
                  max="2025-06-30"
                  value={query.date}
                  onChange={(e) => onChange({ date: e.target.value })}
                />
              </label>

              {replay ? (
                <>
                  <div className="forecast">
                    <div className="forecast-head">
                      <span>
                        {playing ? "Playing" : "Paused"} · {replay.frames[replayIdx]?.time}
                      </span>
                      <span className="muted">peak {replay.peak_hour}</span>
                    </div>
                    <div className="bars hours" role="group" aria-label="Hourly rain timeline">
                      {replay.frames.map((f, i) => (
                        <div
                          key={f.time}
                          className={`bar ${i === replayIdx ? "active" : ""}`}
                          title={`${f.time} · ${f.mm_max} mm/h · ${f.counts.red} red, ${f.counts.amber} amber`}
                          onClick={() => onReplayIndex(i)}
                        >
                          <i style={{ height: `${Math.min(100, (f.mm_max / 60) * 100)}%` }}></i>
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: "8px", fontSize: "13px" }}>
                      <b>{replay.frames[replayIdx]?.mm_max} mm/h</b> ·{" "}
                      <b>{replay.frames[replayIdx]?.counts.red}</b> red ·{" "}
                      <b>{replay.frames[replayIdx]?.counts.amber}</b> amber
                    </div>
                  </div>

                  <label className="field">
                    <span className="field-head">
                      Hour <output>{replay.frames[replayIdx]?.time}</output>
                    </span>
                    <input
                      type="range"
                      min="0"
                      max={replay.frames.length - 1}
                      step="1"
                      value={replayIdx}
                      style={{ "--fill": `${(replayIdx / Math.max(1, replay.frames.length - 1)) * 100}%` }}
                      onChange={(e) => onReplayIndex(Number(e.target.value))}
                    />
                  </label>

                  <button type="button" className="btn" onClick={onReplayToggle}>
                    {playing ? "Pause storm" : "Play 24 h storm"}
                  </button>

                  <p className="hint">
                    Archived Open-Meteo hourly rain × {replay.factor} bias, re-scored every hour by the
                    current drain model.
                  </p>
                </>
              ) : (
                <p className="hint">Loading archived rain…</p>
              )}
            </div>
          ) : (
            <div>
              <div className="forecast">
                <div className="forecast-head">
                  <span>Open-Meteo live feed</span>
                  <span className="muted">{forecast?.fetched_at ? `Fetched ${forecast.fetched_at}` : "Live"}</span>
                </div>
                {forecast && (
                  <>
                    <div style={{ marginTop: "8px", fontSize: "13px" }}>
                      Peak: <b>{forecast.peak_raw_mm_h} mm/h</b> at {forecast.peak_hotspot} ({forecast.peak_time || "dry"})
                    </div>
                    {forecast.daily_peaks && (
                      <div className="bars">
                        {forecast.daily_peaks.map((p, idx) => (
                          <div key={idx} className="bar">
                            <b>{p.max_mm_h}</b>
                            <i style={{ height: `${Math.min(100, (p.max_mm_h / 60) * 100)}%` }}></i>
                            <span>{idx === 0 ? "Today" : `+${idx}d`}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <label className="toggle">
                <input
                  type="checkbox"
                  checked={query.correct_bias}
                  onChange={(e) => onChange({ correct_bias: e.target.checked })}
                />
                <span className="switch"></span>
                <span>
                  Scale with empirical bias factor (<b>×{biasFactor}</b>)
                </span>
              </label>
              <p className="hint">
                Reanalysis backtest showed Open-Meteo under-predicts Bengaluru convective peaks by ~{biasFactor}×.
              </p>
            </div>
          )}
        </section>

        <section>
          <h2>Drainage network</h2>
          <label className="field">
            <span className="field-head">
              Base drainage siltation / blockage{" "}
              <output>{Math.round(query.blockage * 100)}%</output>
            </span>
            <input
              type="range"
              min="0"
              max="90"
              step="5"
              value={Math.round(query.blockage * 100)}
              style={{ "--fill": `${(query.blockage / 0.9) * 100}%` }}
              onChange={(e) => onChange({ blockage: Number(e.target.value) / 100 })}
            />
            <span className="hint">Pre-monsoon target: ≤ 20% across primary & secondary SWD</span>
          </label>

          <label className="field">
            <span className="field-head">Culvert choke scenario</span>
            <select
              value={query.culvert || ""}
              onChange={(e) => onChange({ culvert: e.target.value || null })}
            >
              <option value="">None (normal flow across culverts)</option>
              {culverts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>

          {query.culvert && (
            <label className="field">
              <span className="field-head">
                Selected culvert blockage{" "}
                <output>{Math.round(query.culvert_blockage * 100)}%</output>
              </span>
              <input
                type="range"
                min="0"
                max="95"
                step="5"
                value={Math.round(query.culvert_blockage * 100)}
                style={{ "--fill": `${(query.culvert_blockage / 0.95) * 100}%` }}
                onChange={(e) => onChange({ culvert_blockage: Number(e.target.value) / 100 })}
              />
            </label>
          )}
        </section>

        <section>
          <h2>Safe flood-aware routing</h2>
          <div className="route-pick">
            <div className="rp-line" aria-hidden="true">
              <i className="a">A</i>
              <span></span>
              <i className="b">B</i>
            </div>
            <div className="rp-fields">
              <select
                value={query.origin}
                onChange={(e) => onChange({ origin: e.target.value })}
              >
                {places.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                value={query.dest}
                onChange={(e) => onChange({ dest: e.target.value })}
              >
                {places.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={handleSwap}
              title="Swap origin and destination"
              aria-label="Swap endpoints"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M7 16V4m0 0L3 8m4-4 4 4M17 8v12m0 0 4-4m-4 4-4-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <button type="button" className="btn ghost" onClick={useMyLocation} disabled={locating}>
            {locating ? "Locating…" : "Use my location as start"}
          </button>
          {geoMsg && <p className="hint">{geoMsg}</p>}
        </section>

        <section>
          <h2>Layer visibility</h2>
          <div style={{ display: "grid", gap: "8px" }}>
            <label className="toggle">
              <input
                type="checkbox"
                checked={layerVisibility.hotspots}
                onChange={(e) => onToggleLayer("hotspots", e.target.checked)}
              />
              <span className="switch"></span>
              <span>Hotspot points (388 locations)</span>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={layerVisibility.drains}
                onChange={(e) => onToggleLayer("drains", e.target.checked)}
              />
              <span className="switch"></span>
              <span>Drain network (~3,000 segments)</span>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={layerVisibility.zones}
                onChange={(e) => onToggleLayer("zones", e.target.checked)}
              />
              <span className="switch"></span>
              <span>Flooded catchments</span>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={layerVisibility.routes}
                onChange={(e) => onToggleLayer("routes", e.target.checked)}
              />
              <span className="switch"></span>
              <span>Routing paths (Usual vs Safe)</span>
            </label>
          </div>
        </section>
      </div>
    </aside>
  );
}

