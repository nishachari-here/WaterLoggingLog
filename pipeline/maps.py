"""Step 4: a static overview figure and an interactive Leaflet map (folium, OSM tiles, no API key)."""
import base64
import io

import folium
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource
from rasterio.warp import Resampling, calculate_default_transform, reproject

import config


def _read(name):
    with rasterio.open(config.PROCESSED_DIR / f"{name}.tif") as src:
        return src.read(1).astype("float32"), src


def static_figure(hot):
    dem, src = _read("dem_utm")
    ext = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
    panels = [
        ("Elevation (m) + hillshade", dem, "terrain", None),
        ("Upstream area, log10 km2", np.log10(_read("upstream_km2")[0]), "Blues", (-3, 1.5)),
        ("Height above nearest drainage (m)", _read("hand")[0], "viridis_r", (0, 30)),
        ("Terrain-only susceptibility (0-100)", _read("terrain_score")[0], "magma", (40, 100)),
    ]
    hs = LightSource(azdeg=315, altdeg=45).hillshade(dem, vert_exag=3, dx=30, dy=30)
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))
    for ax, (title, arr, cmap, lim) in zip(axes.ravel(), panels):
        im = ax.imshow(arr, cmap=cmap, extent=ext, vmin=lim and lim[0], vmax=lim and lim[1])
        if title.startswith("Elevation"):
            ax.imshow(hs, cmap="gray", extent=ext, alpha=0.35)
        ax.scatter(hot.x, hot.y, s=40, c="red", edgecolor="white", zorder=3)
        for h in hot.itertuples():
            ax.annotate(h.id, (h.x, h.y), fontsize=7, xytext=(4, 4), textcoords="offset points", color="black",
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", alpha=0.6, lw=0))
        ax.set_title(title)
        ax.set_xticks([]), ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.7)
    fig.suptitle("Bengaluru terrain layer (Copernicus GLO-30, UTM 43N)", fontsize=14)
    fig.tight_layout()
    out = config.OUT_DIR / "terrain_overview.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"  {out.name}")


def _overlay(name, cmap, vmin, vmax, mask_below=None):
    """Reproject a layer to lon/lat and render it as a transparent PNG for Leaflet."""
    arr, src = _read(name)
    tf, w, h = calculate_default_transform(src.crs, "EPSG:4326", src.width, src.height, *src.bounds)
    dst = np.full((h, w), np.nan, dtype="float32")
    reproject(arr, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=tf,
              dst_crs="EPSG:4326", resampling=Resampling.nearest, dst_nodata=np.nan)
    rgba = plt.get_cmap(cmap)(np.clip((dst - vmin) / (vmax - vmin), 0, 1))
    hide = np.isnan(dst) if mask_below is None else (np.isnan(dst) | (dst < mask_below))
    rgba[..., 3] = np.where(hide, 0, 0.65)
    buf = io.BytesIO()
    plt.imsave(buf, rgba, format="png")
    west, north = tf.c, tf.f
    east, south = west + tf.a * w, north + tf.e * h
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return url, [[south, west], [north, east]]


def web_map(hot, catch):
    m = folium.Map(location=[12.97, 77.61], zoom_start=11, tiles="OpenStreetMap", control_scale=True)
    for label, args, show in [
        ("Terrain-only susceptibility (top 30%)", ("terrain_score", "magma_r", 70, 100, 70), True),
        ("Height above nearest drainage < 5 m", ("hand", "Blues_r", 0, 5, None), False),
        ("DEM-derived drainage lines", ("streams", "Blues", 0, 1, 1), False),
    ]:
        url, bounds = _overlay(*args)
        folium.raster_layers.ImageOverlay(url, bounds=bounds, name=label, show=show).add_to(m)

    folium.GeoJson(
        catch.to_crs("EPSG:4326"), name="Hotspot catchments",
        style_function=lambda f: {"color": "#1f6feb", "weight": 1.5, "fillOpacity": 0.08},
        tooltip=folium.GeoJsonTooltip(["name", "catchment_km2"], aliases=["Hotspot", "Catchment km2"]),
    ).add_to(m)

    fg = folium.FeatureGroup(name="Hotspots")
    for h in hot.itertuples():
        html = (f"<b>{h.name}</b><br>elev {h.elev_m:.0f} m · slope {h.slope_deg:.1f}°<br>"
                f"upstream area {h.upstream_km2:.2f} km² · catchment {h.catchment_km2:.2f} km²<br>"
                f"HAND {h.hand_m:.1f} m · TPI(300 m) {h.tpi300_m:.1f} m<br>"
                f"terrain score {h.terrain_score:.0f} (higher than {h.terrain_score_pctl:.0f}% of controls)<br>"
                f"<i>{h.coord_source}</i>")
        folium.CircleMarker([h.lat, h.lon], radius=7, color="white", weight=2, fill=True,
                            fill_color="#d1242f", fill_opacity=0.95,
                            popup=folium.Popup(html, max_width=320), tooltip=h.name).add_to(fg)
    fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    out = config.OUT_DIR / "terrain_map.html"
    m.save(out)
    print(f"  {out.name}")
