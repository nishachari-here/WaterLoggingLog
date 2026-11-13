import { Marker, Popup, Tooltip } from "react-leaflet";
import L from "leaflet";

const STATUS_LABELS = {
  red: { label: "Red alert", color: "var(--red)" },
  amber: { label: "Amber warning", color: "var(--amber)" },
  green: { label: "Clear / normal", color: "var(--green)" },
};

const KIND_LABELS = {
  underpass: "Underpass",
  junction: "Junction",
  low_lying: "Low-lying area",
};

export default function HotspotLayer({ hotspots = [], selectedId, onSelectHotspot }) {
  // Pre-create divIcons by key or dynamically
  const createIcon = (status, hasWatch, isSelected) => {
    return L.divIcon({
      className: "",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: `
        <div class="hs-marker ${status}${isSelected ? " selected" : ""}">
          ${status === "red" ? '<span class="pulse"></span>' : ""}
          ${hasWatch ? '<span class="watch-ring"></span>' : ""}
          <span class="core"></span>
        </div>
      `,
    });
  };

  return (
    <>
      {hotspots.map((h) => {
        const hasWatch = Array.isArray(h.watch) && h.watch.length > 0;
        const icon = createIcon(h.status, hasWatch, h.id === selectedId);
        const zIndexOffset = h.status === "red" ? 300 : h.status === "amber" ? 150 : 0;
        const statusMeta = STATUS_LABELS[h.status] || STATUS_LABELS.green;

        return (
          <Marker
            key={h.id}
            position={[h.lat, h.lon]}
            icon={icon}
            zIndexOffset={zIndexOffset}
            eventHandlers={{
              click: () => onSelectHotspot && onSelectHotspot(h.id),
            }}
          >
            <Tooltip direction="top" offset={[0, -10]}>
              <b>{h.name}</b>
              <br />
              <span style={{ color: statusMeta.color }}>{statusMeta.label}</span>
            </Tooltip>
            <Popup>
              <div style={{ minWidth: "180px" }}>
                <h3 style={{ margin: "0 0 6px", fontSize: "14px" }}>{h.name}</h3>
                <div style={{ marginBottom: "4px" }}>
                  <b style={{ color: statusMeta.color }}>{statusMeta.label}</b> · {KIND_LABELS[h.kind] || h.kind}
                </div>
                <div>
                  Rain: <b>{h.rain} mm/h</b> vs threshold{" "}
                  <b>{h.threshold == null ? "no modelled drain path" : `${h.threshold} mm/h`}</b>
                </div>
                <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
                  Load ratio: <b>{h.ratio}×</b>
                </div>
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Bottleneck: {h.bottleneck || "None"}
                </div>
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Capacity source: {h.capacity_source || "Manning/DEM"}
                </div>
                {hasWatch && (
                  <div style={{ color: "var(--watch)", fontWeight: 600, marginTop: "6px" }}>
                    ⚠️ Watch: storm in {h.watch.join(", ")} day{h.watch.length > 1 || h.watch[0] > 1 ? "s" : ""}
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}

