import { Polyline, Marker, Tooltip } from "react-leaflet";
import L from "leaflet";

const pinIcon = (cls, letter) =>
  L.divIcon({
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 26],
    html: `<div class="pin ${cls}"><span>${letter}</span></div>`,
  });

export default function RouteLayer({ route, blockedSegment, places = [], originName, destName }) {
  if (!route) return null;
  const { usual, safe } = route;
  const detour = Boolean(usual && safe && usual.crosses && usual.crosses.length > 0);

  const originPlace = places.find((p) => p.name === originName);
  const destPlace = places.find((p) => p.name === destName);

  return (
    <>
      {/* Blocked culvert segment */}
      {blockedSegment && blockedSegment.length > 0 && (
        <>
          <Polyline
            positions={blockedSegment}
            pathOptions={{ color: "#0f172a", weight: 9, opacity: 0.85, lineCap: "round" }}
          />
          <Polyline
            positions={blockedSegment}
            pathOptions={{ color: "var(--red)", weight: 4, dashArray: "6 6" }}
          >
            <Tooltip sticky>Blocked culvert bottleneck</Tooltip>
          </Polyline>
        </>
      )}

      {/* Usual Route */}
      {usual && usual.latlon && usual.latlon.length > 0 && (
        <Polyline
          positions={usual.latlon}
          pathOptions={{
            color: "var(--route-usual)",
            weight: 5,
            opacity: detour ? 0.75 : 0.95,
            dashArray: detour ? "2 10" : undefined,
            lineCap: "round",
          }}
        >
          <Tooltip sticky>
            Usual route · {usual.min} min · {usual.km} km
            {detour ? " (Passes flooded hotspots!)" : " (Clear)"}
          </Tooltip>
        </Polyline>
      )}

      {/* Safe Route (when detouring around flooded zones) */}
      {detour && safe && safe.latlon && safe.latlon.length > 0 && (
        <>
          {/* White outline for high contrast */}
          <Polyline
            positions={safe.latlon}
            pathOptions={{
              color: "#ffffff",
              weight: 10,
              opacity: 0.9,
              lineCap: "round",
            }}
          />
          <Polyline
            positions={safe.latlon}
            pathOptions={{
              color: "var(--route-safe)",
              weight: 6,
              opacity: 1,
              lineCap: "round",
            }}
          >
            <Tooltip sticky>
              Safe recommended route · {safe.min} min · {safe.km} km (Avoids waterlogging)
            </Tooltip>
          </Polyline>
        </>
      )}

      {/* Origin A and Destination B pins */}
      {originPlace && (
        <Marker
          position={[originPlace.lat, originPlace.lon]}
          icon={pinIcon("a", "A")}
          zIndexOffset={1000}
        >
          <Tooltip direction="top" offset={[0, -26]}>
            Start: {originPlace.name}
          </Tooltip>
        </Marker>
      )}
      {destPlace && (
        <Marker
          position={[destPlace.lat, destPlace.lon]}
          icon={pinIcon("b", "B")}
          zIndexOffset={1000}
        >
          <Tooltip direction="top" offset={[0, -26]}>
            Destination: {destPlace.name}
          </Tooltip>
        </Marker>
      )}
    </>
  );
}

