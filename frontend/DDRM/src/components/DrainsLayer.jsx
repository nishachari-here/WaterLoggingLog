import { useEffect, useState } from "react";
import { GeoJSON } from "react-leaflet";

export default function DrainsLayer() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let active = true;
    fetch("/api/drains")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load drain network");
        return res.json();
      })
      .then((json) => {
        if (active) setData(json);
      })
      .catch((err) => console.error("Error loading drains:", err));

    return () => {
      active = false;
    };
  }, []);

  if (!data) return null;

  const styleFeature = (feature) => {
    const area = feature.properties?.area_km2 || 0;
    const weight = 0.8 + Math.min(area, 60) / 14;
    return {
      color: "var(--accent)",
      weight: weight,
      opacity: 0.55,
    };
  };

  const onEachFeature = (feature, layer) => {
    const p = feature.properties || {};
    const text = `Upstream area: ${(p.area_km2 || 0).toFixed(1)} km²${
      p.culverts ? `<br/>Crosses culvert: ${p.culverts}` : ""
    }`;
    layer.bindTooltip(text, { sticky: true });
  };

  return <GeoJSON data={data} style={styleFeature} onEachFeature={onEachFeature} />;
}

