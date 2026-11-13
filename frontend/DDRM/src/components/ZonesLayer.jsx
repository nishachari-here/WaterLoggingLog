import { GeoJSON } from "react-leaflet";

export default function ZonesLayer({ zones }) {
  if (!zones || !zones.features || zones.features.length === 0) return null;

  const styleZone = (feature) => {
    const isRed = feature.properties?.status === "red";
    const color = isRed ? "var(--red)" : "var(--amber)";
    return {
      color: color,
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.16,
      dashArray: isRed ? undefined : "4 4",
    };
  };

  return <GeoJSON key={JSON.stringify(zones)} data={zones} style={styleZone} interactive={false} />;
}

