export default function StatusBar({ counts, watchCount, ruleAlerts, totalHotspots }) {
  const red = counts?.red ?? "–";
  const amber = counts?.amber ?? "–";
  const green = counts?.green ?? "–";
  const watch = watchCount ?? "–";
  const rule = ruleAlerts !== undefined && totalHotspots !== undefined ? `${ruleAlerts}/${totalHotspots}` : "–";

  return (
    <header className="statusbar card" aria-live="polite">
      <div className="stat red">
        <span className="dot"></span>
        <div>
          <b>{red}</b>
          <small>Red alert</small>
        </div>
      </div>
      <div className="stat amber">
        <span className="dot"></span>
        <div>
          <b>{amber}</b>
          <small>Amber</small>
        </div>
      </div>
      <div className="stat green">
        <span className="dot"></span>
        <div>
          <b>{green}</b>
          <small>Clear</small>
        </div>
      </div>
      <div className="stat watch">
        <span className="dot ring"></span>
        <div>
          <b>{watch}</b>
          <small>Watch 1–3 d</small>
        </div>
      </div>
      <div className="stat rule" title="Baseline: city-wide 40 mm/h rule that alerts every hotspot indiscriminately">
        <div>
          <b>{rule}</b>
          <small>40 mm/h rule</small>
        </div>
      </div>
    </header>
  );
}

