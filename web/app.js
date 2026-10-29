"use strict";

const STATUS = {
  red: { label: "Red alert", color: "var(--red)" },
  amber: { label: "Amber", color: "var(--amber)" },
  green: { label: "Clear", color: "var(--green)" },
};
const KIND = { underpass: "Underpass", junction: "Junction", low_lying: "Low-lying" };

const state = {
  mode: "scenario",
  rain_today: 30,
  rain_later: 0,
  later_day: 2,
  correct_bias: true,
  blockage: 0.2,
  culvert: "",
  culvert_blockage: 0.9,
  origin: "Koramangala (Forum)",
  dest: "Marathahalli",
};
let meta = null;
let last = null;
let selected = null;
let fitPending = true;
let controller = null;
let timer = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------- theme ----------------
function storedTheme() {
  try { return localStorage.getItem("theme"); } catch { return null; }
}
function effectiveTheme() {
  const t = document.documentElement.dataset.theme;
  if (t) return t;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
if (storedTheme()) document.documentElement.dataset.theme = storedTheme();

// ---------------- map ----------------
const map = L.map("map", { zoomControl: true, attributionControl: true }).setView([12.965, 77.63], 12);
// Standard OSM tiles (no key); styles.css tints them per theme via the .basemap class.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  className: "basemap",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const layers = {
  drains: L.layerGroup(),
  zones: L.layerGroup().addTo(map),
  routes: L.layerGroup().addTo(map),
  blocked: L.layerGroup().addTo(map),
  hotspots: L.layerGroup().addTo(map),
  endpoints: L.layerGroup().addTo(map),
};
let drainsLoaded = false;
const markers = {};

$("theme").addEventListener("click", () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch { /* private mode */ }
  if (last) render(last);
});

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ---------------- controls ----------------
function intensity(mm) {
  if (mm === 0) return ["No rain", "var(--surface-2)", "var(--muted)"];
  if (mm < 10) return ["Moderate", "color-mix(in srgb, var(--green) 15%, var(--surface))", "var(--green)"];
  if (mm < 30) return ["Heavy", "color-mix(in srgb, var(--amber) 18%, var(--surface))", "var(--amber)"];
  if (mm < 50) return ["Very heavy", "color-mix(in srgb, var(--red) 15%, var(--surface))", "var(--red)"];
  return ["Extreme", "var(--red)", "#fff"];
}

function paintRange(input) {
  const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty("--fill", pct + "%");
}

function syncOutputs() {
  $("o-today").textContent = `${state.rain_today} mm/h`;
  $("o-later").textContent = state.rain_later ? `${state.rain_later} mm/h` : "none";
  $("o-block").textContent = `${Math.round(state.blockage * 100)}%`;
  $("o-cblock").textContent = `${Math.round(state.culvert_blockage * 100)}%`;
  const [label, bg, fg] = intensity(state.rain_today);
  const it = $("i-today");
  it.textContent = label;
  it.style.background = bg;
  it.style.color = fg;
  document.querySelectorAll('input[type="range"]').forEach(paintRange);
}

function schedule(delay = 160) {
  clearTimeout(timer);
  timer = setTimeout(assess, delay);
}

function bindRange(id, key, scale = 1) {
  $(id).addEventListener("input", (e) => {
    state[key] = Number(e.target.value) / scale;
    syncOutputs();
    schedule();
  });
}
bindRange("rain-today", "rain_today");
bindRange("rain-later", "rain_later");
bindRange("blockage", "blockage", 100);
bindRange("culvert-block", "culvert_blockage", 100);

document.querySelectorAll(".segmented button").forEach((b) =>
  b.addEventListener("click", () => {
    state.mode = b.dataset.mode;
    document.querySelectorAll(".segmented button").forEach((x) => x.setAttribute("aria-selected", x === b));
    $("scenario-controls").hidden = state.mode !== "scenario";
    $("live-controls").hidden = state.mode !== "live";
    schedule(0);
  }),
);

document.querySelectorAll("#later-day button").forEach((b) =>
  b.addEventListener("click", () => {
    state.later_day = Number(b.dataset.day);
    document.querySelectorAll("#later-day button").forEach((x) => x.setAttribute("aria-checked", x === b));
    schedule(0);
  }),
);

$("bias").addEventListener("change", (e) => { state.correct_bias = e.target.checked; schedule(0); });
$("culvert").addEventListener("change", (e) => {
  state.culvert = e.target.value;
  $("culvert-block-field").hidden = !state.culvert;
  schedule(0);
});
$("origin").addEventListener("change", (e) => { state.origin = e.target.value; fitPending = true; schedule(0); });
$("dest").addEventListener("change", (e) => { state.dest = e.target.value; fitPending = true; schedule(0); });
$("swap").addEventListener("click", () => {
  [state.origin, state.dest] = [state.dest, state.origin];
  $("origin").value = state.origin;
  $("dest").value = state.dest;
  fitPending = true;
  schedule(0);
});

document.querySelectorAll("[data-layer]").forEach((cb) =>
  cb.addEventListener("change", async () => {
    const layer = layers[cb.dataset.layer];
    if (cb.dataset.layer === "drains" && cb.checked && !drainsLoaded) await loadDrains();
    cb.checked ? layer.addTo(map) : map.removeLayer(layer);
  }),
);

document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)),
);
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === name));
  ["route", "hotspots", "priorities"].forEach((t) => ($(`tab-${t}`).hidden = t !== name));
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.hidden = true), 4000);
}

function progress(on) {
  const p = $("progress");
  if (on) { p.className = "progress"; void p.offsetWidth; p.className = "progress on"; }
  else { p.className = "progress done"; }
}

// ---------------- data ----------------
async function loadDrains() {
  const gj = await (await fetch("/api/drains")).json();
  L.geoJSON(gj, {
    style: (f) => ({ color: css("--accent"), weight: 0.8 + Math.min(f.properties.area_km2, 60) / 14, opacity: 0.55 }),
    onEachFeature: (f, l) =>
      l.bindTooltip(`Upstream ${f.properties.area_km2.toFixed(1)} km²${f.properties.culverts ? "<br>Crosses: " + esc(f.properties.culverts) : ""}`, { sticky: true }),
  }).addTo(layers.drains);
  drainsLoaded = true;
}

async function init() {
  meta = await (await fetch("/api/meta")).json();
  const opts = meta.places.map((p) => `<option>${esc(p.name)}</option>`).join("");
  $("origin").innerHTML = opts;
  $("dest").innerHTML = opts;
  $("origin").value = state.origin;
  $("dest").value = state.dest;
  $("culvert").innerHTML += meta.culverts.map((c) => `<option value="${esc(c.id)}">${esc(c.label)}</option>`).join("");
  $("bias-x").textContent = `×${meta.bias_factor}`;
  syncOutputs();
  assess();
}

async function assess() {
  if (controller) controller.abort();
  controller = new AbortController();
  progress(true);
  try {
    const r = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state, culvert: state.culvert || null }),
      signal: controller.signal,
    });
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail || r.statusText;
      toast(`Couldn't update: ${detail}`);
      if (state.mode === "live") $("fc-title").textContent = "Forecast unavailable";
      return;
    }
    last = await r.json();
    render(last);
  } catch (e) {
    if (e.name !== "AbortError") toast("Server not reachable. Is server.py running?");
  } finally {
    progress(false);
  }
}

// ---------------- rendering ----------------
function render(d) {
  $("k-red").textContent = d.counts.red;
  $("k-amber").textContent = d.counts.amber;
  $("k-green").textContent = d.counts.green;
  $("k-watch").textContent = d.watch_count;
  $("k-rule").textContent = `${d.rule_alerts}/${d.hotspots.length}`;

  renderHotspotMarkers(d);
  renderZones(d);
  renderRoutes(d);
  renderBlocked(d);
  renderRouteTab(d);
  renderHotspotTab(d);
  renderPriorities(d);
  if (d.forecast) renderForecast(d.forecast);
}

function watchText(days) {
  return days.length ? `Watch · in ${days.join(", ")} day${days.length > 1 || days[0] > 1 ? "s" : ""}` : "";
}

function popupHtml(h) {
  return `<h3>${esc(h.name)}</h3>
    <div><b style="color:${STATUS[h.status].color}">${STATUS[h.status].label}</b> · ${KIND[h.kind] || ""}</div>
    <div>Rain <b>${h.rain}</b> mm/h vs threshold <b>${h.threshold}</b> mm/h</div>
    <div class="muted">Bottleneck: ${esc(h.bottleneck)}</div>
    <div class="muted">Capacity: ${esc(h.capacity_source)}</div>
    ${h.watch.length ? `<div style="color:var(--watch);font-weight:600">${watchText(h.watch)}</div>` : ""}`;
}

function renderHotspotMarkers(d) {
  layers.hotspots.clearLayers();
  for (const h of d.hotspots) {
    const icon = L.divIcon({
      className: "",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: `<div class="hs-marker ${h.status}">${h.status === "red" ? '<span class="pulse"></span>' : ""}${h.watch.length ? '<span class="watch-ring"></span>' : ""}<span class="core"></span></div>`,
    });
    const m = L.marker([h.lat, h.lon], { icon, riseOnHover: true, zIndexOffset: h.status === "red" ? 300 : 0 })
      .bindPopup(popupHtml(h))
      .bindTooltip(esc(h.name), { direction: "top", offset: [0, -10] })
      .on("click", () => select(h.id, false));
    m.addTo(layers.hotspots);
    markers[h.id] = m;
  }
  if (selected && markers[selected]) markers[selected].openPopup();
}

function renderZones(d) {
  layers.zones.clearLayers();
  if (!d.zones) return;
  L.geoJSON(d.zones, {
    style: (f) => {
      const c = css(f.properties.status === "red" ? "--red" : "--amber");
      return { color: c, weight: 1.5, fillColor: c, fillOpacity: 0.16, dashArray: f.properties.status === "amber" ? "4 4" : null };
    },
    interactive: false,
  }).addTo(layers.zones);
}

function renderRoutes(d) {
  layers.routes.clearLayers();
  layers.endpoints.clearLayers();
  const { usual, safe } = d.route;
  const detour = usual && safe && usual.crosses.length;
  if (usual) {
    L.polyline(usual.latlon, { color: css("--route-usual"), weight: 5, opacity: detour ? 0.75 : 0.9, dashArray: detour ? "2 10" : null, lineCap: "round" })
      .bindTooltip(`Usual route · ${usual.min} min · ${usual.km} km`, { sticky: true })
      .addTo(layers.routes);
  }
  if (detour) {
    L.polyline(safe.latlon, { color: "#fff", weight: 10, opacity: 0.9, lineCap: "round" }).addTo(layers.routes);
    L.polyline(safe.latlon, { color: css("--route-safe"), weight: 6, opacity: 1, lineCap: "round" })
      .bindTooltip(`Suggested route · ${safe.min} min · ${safe.km} km`, { sticky: true })
      .addTo(layers.routes);
  }
  const pin = (cls, letter) => L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 26], html: `<div class="pin ${cls}"><span>${letter}</span></div>` });
  const o = meta.places.find((p) => p.name === state.origin);
  const t = meta.places.find((p) => p.name === state.dest);
  L.marker([o.lat, o.lon], { icon: pin("a", "A"), zIndexOffset: 1000 }).bindTooltip(esc(o.name)).addTo(layers.endpoints);
  L.marker([t.lat, t.lon], { icon: pin("b", "B"), zIndexOffset: 1000 }).bindTooltip(esc(t.name)).addTo(layers.endpoints);

  if (fitPending && usual) {
    const pts = usual.latlon.concat(safe ? safe.latlon : []);
    const wide = matchMedia("(min-width: 1101px)").matches;
    map.fitBounds(L.latLngBounds(pts), wide ? { paddingTopLeft: [380, 90], paddingBottomRight: [420, 40] } : { padding: [24, 24] });
    fitPending = false;
  }
}

function renderBlocked(d) {
  layers.blocked.clearLayers();
  if (!d.blocked_segment) return;
  L.polyline(d.blocked_segment, { color: "#0f172a", weight: 9, opacity: 0.85, lineCap: "round" }).addTo(layers.blocked);
  L.polyline(d.blocked_segment, { color: css("--red"), weight: 4, dashArray: "6 6" })
    .bindTooltip("Blocked culvert segment").addTo(layers.blocked);
}

const ICON = {
  ok: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  bad: '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3zm0 6v5m0 3v.5" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg>',
};

function hotspotPill(text) {
  const name = text.replace(/ \((red|amber)\)$/, "");
  const status = text.endsWith("(red)") ? "red" : "amber";
  return `<span class="pill"><i style="background:${STATUS[status].color}"></i>${esc(name)}</span>`;
}

function routeCard(kind, r, extra = "") {
  const color = kind === "safe" ? "var(--route-safe)" : "var(--route-usual)";
  const title = kind === "safe" ? "Suggested route" : "Usual route";
  return `<div class="route-card ${kind}">
    <header><i style="background:${color}"></i>${title}</header>
    <div class="big"><b>${r.min} min</b><span>${r.km} km</span>${extra}</div>
    ${r.crosses.length ? `<div class="crosses">${r.crosses.map(hotspotPill).join("")}</div>` : ""}
  </div>`;
}

function renderRouteTab(d) {
  const { usual, safe } = d.route;
  let html = "";
  if (!usual) {
    html = `<div class="callout bad">${ICON.bad}<div>No road route between these places.</div></div>`;
  } else if (!usual.crosses.length) {
    html = `<div class="callout ok">${ICON.ok}<div><b>Your usual route is clear.</b><br>It avoids every flagged hotspot.</div></div>${routeCard("usual", usual)}`;
  } else if (!safe) {
    html = `<div class="callout bad">${ICON.bad}<div><b>No dry route right now.</b><br>Every option crosses a red zone. Consider delaying the trip.</div></div>${routeCard("usual", usual)}`;
  } else {
    const delta = safe.min - usual.min;
    html = `<div class="callout bad">${ICON.bad}<div><b>Your usual route crosses ${usual.crosses.length} flood-risk hotspot${usual.crosses.length > 1 ? "s" : ""}.</b><br>Take the suggested route instead.</div></div>
      ${routeCard("safe", { ...safe, crosses: [] }, `<span class="delta">${delta > 0 ? "+" : ""}${delta} min</span>`)}
      ${routeCard("usual", usual)}`;
  }
  const watching = d.hotspots.filter((h) => h.watch.length);
  if (watching.length) {
    html += `<div class="callout watch">${ICON.eye}<div><b>Watch: ${watching.length} hotspot${watching.length > 1 ? "s" : ""} may flood in the next 1–3 days.</b><br>
      A heads-up, not a warning. Forecasts this far out change between runs.</div></div>`;
  }
  $("tab-route").innerHTML = html;
}

function renderHotspotTab(d) {
  const rows = d.hotspots.map((h) => {
    const pct = Math.min(h.ratio / 1.5, 1) * 100;
    const open = h.id === selected;
    return `<div class="hs ${open ? "active" : ""}" data-id="${esc(h.id)}" role="button" tabindex="0" aria-expanded="${open}">
      <span class="sdot" style="background:${STATUS[h.status].color}"></span>
      <span class="name">${esc(h.name)}</span>
      <span class="nums"><b>${h.rain}</b> / ${h.threshold} mm/h</span>
      <span></span>
      <div class="meter" title="Rain as a share of the flood threshold (tick = threshold)"><i style="width:${pct}%;background:${STATUS[h.status].color}"></i></div>
      <span></span>
      <div class="tags"><span class="tag">${KIND[h.kind] || h.kind}</span>${h.watch.length ? `<span class="tag watch">${watchText(h.watch)}</span>` : ""}${h.capacity_source.startsWith("field") ? '<span class="tag">Field-measured</span>' : ""}</div>
      ${open ? `<span></span><div class="detail">Bottleneck: ${esc(h.bottleneck)}</div>` : ""}
    </div>`;
  }).join("");
  $("tab-hotspots").innerHTML = `<p class="list-note">Sorted by how close rain is to each hotspot's flood threshold. Tap one to find it on the map.</p>${rows}`;
  $("tab-hotspots").querySelectorAll(".hs").forEach((el) => {
    const go = () => select(el.dataset.id, true);
    el.addEventListener("click", go);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
}

function select(id, fly) {
  selected = id;
  showTab("hotspots");
  if (last) renderHotspotTab(last);
  const m = markers[id];
  if (m) {
    if (fly) map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 14), { duration: 0.6 });
    m.openPopup();
  }
}

function renderPriorities(d) {
  if (!d.clear_first.length) {
    $("tab-priorities").innerHTML = `<p class="list-note">No blockage is limiting any hotspot right now. Raise the typical blockage to see where clearing helps.</p>`;
    return;
  }
  $("tab-priorities").innerHTML =
    `<p class="list-note">Drain segments where clearing silt and garbage raises hotspot flood thresholds the most. Hand this to BBMP maintenance.</p>` +
    d.clear_first.map((c, i) => `<div class="prio">
      <span class="rank">${i + 1}</span>
      <span class="t">${esc(c.label)}</span>
      <span class="gain">+${c.threshold_gain_mm_h} mm/h</span>
      <span></span>
      <span class="s">Helps ${esc(c.hotspots_helped)} · drains ${c.upstream_km2} km²</span>
    </div>`).join("");
}

function renderForecast(f) {
  const max = Math.max(10, ...f.daily_peaks.map((p) => p.max_mm_h));
  const names = ["Today", "Tomorrow", "In 2 days", "In 3 days"];
  $("fc-title").textContent = f.peak_time ? `Peak ${f.peak_raw_mm_h.toFixed(1)} mm/h · ${f.peak_hotspot}` : "No rain in the next 24 h";
  $("fc-time").textContent = `updated ${f.fetched_at}`;
  $("fc-bars").innerHTML = f.daily_peaks.map((p) => {
    const [, , fg] = intensity(p.max_mm_h);
    return `<div class="bar"><b>${p.max_mm_h}</b><i style="height:${Math.max(3, (p.max_mm_h / max) * 56)}px;background:${p.max_mm_h ? fg : "var(--border)"}"></i>${names[p.day]}</div>`;
  }).join("");
  $("fc-note").textContent = f.factor !== 1
    ? `Peak hourly rain per day, scaled ×${f.factor} because model rain is smoother than gauge rain.`
    : "Peak hourly rain per day, as forecast (no correction).";
}

init().catch(() => toast("Could not load data. Is server.py running?"));
