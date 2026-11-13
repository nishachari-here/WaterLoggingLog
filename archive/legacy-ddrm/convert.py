import json

EPS = 0.0001  # tolerance

# Load geojson
with open("zones.geojson", "r") as f:
    data = json.load(f)

# Separate points and polygons
points = []
polygons = []

for feature in data["features"]:
    geom = feature["geometry"]
    if geom["type"] == "Point":
        points.append(geom["coordinates"])
    elif geom["type"] == "Polygon":
        polygons.append(feature)

# For each polygon vertex, snap to nearest marked point
for feature in polygons:
    rings = feature["geometry"]["coordinates"]
    for r_idx, ring in enumerate(rings):
        for v_idx, (x, y) in enumerate(ring):
            for px, py in points:
                if abs(x - px) < EPS and abs(y - py) < EPS:
                    # copy-paste the point coordinates
                    rings[r_idx][v_idx] = [px, py]
                    break  # stop once matched

# Save output
with open("zones_mapped.geojson", "w") as f:
    json.dump(data, f, indent=2)

print("Done. Polygon vertices mapped to marked points.")
