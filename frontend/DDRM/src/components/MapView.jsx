import { useEffect } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import HotspotLayer from "./HotspotLayer";
import RouteLayer from "./RouteLayer";
import DrainsLayer from "./DrainsLayer";
import ZonesLayer from "./ZonesLayer";
import "leaflet/dist/leaflet.css";

function MapBoundsController({ route, selectedHotspot, fitPending, onFitted }) {
  const map = useMap();

  useEffect(() => {
    if (selectedHotspot) {
      map.flyTo([selectedHotspot.lat, selectedHotspot.lon], 15, {
        duration: 1.2,
      });
      return;
    }

    if (fitPending && route?.usual?.latlon?.length) {
      const allPts = [
        ...route.usual.latlon,
        ...(route.safe?.latlon || []),
      ];
      if (allPts.length > 0) {
        const bounds = L.latLngBounds(allPts);
        const wide = window.innerWidth >= 1100;
        map.fitBounds(
          bounds,
          wide
            ? { paddingTopLeft: [380, 90], paddingBottomRight: [420, 40] }
            : { padding: [24, 24] }
        );
        if (onFitted) onFitted();
      }
    }
  }, [route, selectedHotspot, fitPending, map, onFitted]);

  return null;
}

export default function MapView({
  hotspots = [],
  zones = null,
  route = null,
  blockedSegment = null,
  places = [],
  originName = "",
  destName = "",
  selectedId = null,
  onSelectHotspot,
  layerVisibility = { drains: false, zones: true, routes: true, hotspots: true },
  fitPending = false,
  onFitted,
}) {
  const selectedHotspot = hotspots.find((h) => h.id === selectedId);

  return (
    <div className="map">
      <MapContainer
        center={[12.965, 77.63]}
        zoom={12}
        style={{ height: "100%", width: "100%" }}
        zoomControl={true}
        attributionControl={true}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="basemap"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />

        <MapBoundsController
          route={route}
          selectedHotspot={selectedHotspot}
          fitPending={fitPending}
          onFitted={onFitted}
        />

        {layerVisibility.drains && <DrainsLayer />}
        {layerVisibility.zones && <ZonesLayer zones={zones} />}
        {layerVisibility.routes && (
          <RouteLayer
            route={route}
            blockedSegment={blockedSegment}
            places={places}
            originName={originName}
            destName={destName}
          />
        )}
        {layerVisibility.hotspots && (
          <HotspotLayer
            hotspots={hotspots}
            selectedId={selectedId}
            onSelectHotspot={onSelectHotspot}
          />
        )}
      </MapContainer>

      <div className="legend card">
        <span><i className="lg-dot red"></i>Red alert</span>
        <span><i className="lg-dot amber"></i>Amber</span>
        <span><i className="lg-dot green"></i>Clear</span>
        <span><i className="lg-dot watch"></i>Watch (1–3 d)</span>
        <span><i className="lg-line usual"></i>Usual</span>
        <span><i className="lg-line safe"></i>Safe route</span>
      </div>
    </div>
  );
}
