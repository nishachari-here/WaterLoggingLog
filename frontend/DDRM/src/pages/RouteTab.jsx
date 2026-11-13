export default function RouteTab({ route, originName, destName }) {
  if (!route) {
    return <div className="tab muted">Evaluating route...</div>;
  }

  const { usual, safe } = route;
  const detour = Boolean(usual && safe && usual.crosses && usual.crosses.length > 0);
  const extraMin = detour ? safe.min - usual.min : 0;
  const extraKm = detour ? (safe.km - usual.km).toFixed(1) : 0;

  const parseHotspotCross = (crossStr) => {
    const isRed = crossStr.endsWith("(red)");
    const isAmber = crossStr.endsWith("(amber)");
    const name = crossStr.replace(/ \((red|amber)\)$/, "");
    const color = isRed ? "var(--red)" : isAmber ? "var(--amber)" : "var(--muted)";
    return { name, color };
  };

  return (
    <div className="tab">
      {detour ? (
        <div className="callout bad">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3 2 21h20L12 3zm0 6v5m0 3v.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <b>Usual route passes {usual.crosses.length} waterlogged hotspot{usual.crosses.length > 1 ? "s" : ""}!</b>
            <div style={{ marginTop: "2px", opacity: 0.85 }}>
              Detour avoids all submerged sections (+{extraMin} min, +{extraKm} km).
            </div>
          </div>
        </div>
      ) : usual ? (
        <div className="callout ok">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <b>Direct route is clear of flood risks</b>
            <div style={{ marginTop: "2px", opacity: 0.85 }}>
              No waterlogged hotspots along the corridor between {originName} and {destName}.
            </div>
          </div>
        </div>
      ) : null}

      {/* Suggested Safe Route Card (if detouring) */}
      {detour && safe && (
        <div className="route-card safe">
          <header>
            <i style={{ background: "var(--route-safe)" }}></i>
            Suggested safe route (Flood-aware)
          </header>
          <div className="big">
            <b>{safe.min} min</b>
            <span>{safe.km} km</span>
            <span className="delta">+{extraMin} min detour</span>
          </div>
          <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
            Zero flooded hotspots traversed
          </div>
        </div>
      )}

      {/* Usual Route Card */}
      {usual && (
        <div className="route-card">
          <header>
            <i style={{ background: "var(--route-usual)" }}></i>
            Usual fastest route
          </header>
          <div className="big">
            <b>{usual.min} min</b>
            <span>{usual.km} km</span>
          </div>
          {usual.crosses && usual.crosses.length > 0 && (
            <div className="crosses">
              {usual.crosses.map((c, i) => {
                const item = parseHotspotCross(c);
                return (
                  <span key={i} className="pill">
                    <i style={{ background: item.color }}></i>
                    {item.name}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      )}

      <p className="footnote">
        Routing uses OpenStreetMap road network with Dijkstra shortest path. Roads intersecting
        catchments exceeding 100% capacity are heavily penalized or marked impassable.
      </p>
    </div>
  );
}

