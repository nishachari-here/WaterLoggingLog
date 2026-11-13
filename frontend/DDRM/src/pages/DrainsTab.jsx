export default function DrainsTab({ clearFirst = [] }) {
  return (
    <div className="tab">
      <div className="callout ok" style={{ marginBottom: "12px" }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" strokeLinecap="round" />
        </svg>
        <div>
          <b>Pre-monsoon Desilting Priority</b>
          <div style={{ marginTop: "2px", opacity: 0.85 }}>
            Clearing these hydraulic bottlenecks first produces maximum downstream flood relief across the drain network.
          </div>
        </div>
      </div>

      <p className="list-note">Ranked by downstream vulnerability and flow capacity:</p>

      {clearFirst && clearFirst.length > 0 ? (
        <div style={{ display: "grid", gap: "2px" }}>
          {clearFirst.map((item, idx) => (
            <div key={idx} className="prio">
              <span className="rank">{idx + 1}</span>
              <div className="t">{item.label || item.bottleneck || "Culvert Bottleneck"}</div>
              <div className="gain">
                {item.downstream_hotspot ? `Relieves ${item.downstream_hotspot}` : "High relief"}
              </div>
              <div className="s">
                {item.detail || `Critical choke point along ${item.name || "secondary SWD"}`}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted" style={{ padding: "16px 8px" }}>
          No choke-point bottlenecks flagged under current siltation scenario.
        </div>
      )}

      <p className="footnote">
        Priorities derived by graph traversal over BBMP SWD shapefiles and Manning open-channel
        discharge calculations.
      </p>
    </div>
  );
}

