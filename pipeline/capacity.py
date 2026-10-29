"""Bridge between field measurements and the terrain layer.

Field visit gives drain width, depth, silt and slope -> Manning's equation gives how much the drain
can carry. The DEM gives the catchment area A -> the rational method gives how much rain produces
that much runoff. Solving one against the other gives a per-hotspot critical rainfall intensity:
the alert threshold that replaces a single city-wide "40 mm/h" rule.

Rational method is only meant for small catchments (roughly < 2.5 km2). For a hotspot sitting on a
big valley channel, use the local area that reaches the measured drain or inlet, not the whole valley.
"""
import math

# Manning roughness n
ROUGHNESS = {"concrete": 0.015, "stone": 0.025, "earthen": 0.030, "silted": 0.035}

# Runoff coefficient C for Bengaluru-style land cover (standard textbook ranges, mid values)
RUNOFF_C = {"dense_urban": 0.85, "residential": 0.6, "mixed": 0.5, "park": 0.2}


def manning_capacity(width_m, depth_m, silt_m=0.0, slope=0.002, lining="concrete", freeboard_m=0.0):
    """Full-flow capacity (m3/s) of a rectangular open drain, after silt and freeboard are taken off."""
    h = max(depth_m - silt_m - freeboard_m, 0.0)
    if h == 0.0:
        return 0.0
    area = width_m * h
    radius = area / (width_m + 2 * h)
    return area * radius ** (2 / 3) * math.sqrt(slope) / ROUGHNESS[lining]


def rational_runoff(intensity_mm_h, area_km2, c):
    """Peak runoff Q = C*i*A in m3/s (i in mm/h, A in km2)."""
    return 0.278 * c * intensity_mm_h * area_km2


def critical_intensity(capacity_m3s, area_km2, c):
    """Rain intensity (mm/h) at which runoff equals drain capacity, i.e. the hotspot's alert threshold."""
    return capacity_m3s / (0.278 * c * area_km2)


if __name__ == "__main__":
    # Worked example with placeholder numbers: 1.2 m x 1.0 m drain, 0.4 m silt, 0.2 km2 local catchment.
    clean = manning_capacity(1.2, 1.0, silt_m=0.0)
    silted = manning_capacity(1.2, 1.0, silt_m=0.4, lining="silted")
    for label, q in [("clean", clean), ("silted", silted)]:
        print(f"{label:7s} capacity {q:.2f} m3/s -> floods above "
              f"{critical_intensity(q, 0.2, RUNOFF_C['dense_urban']):.0f} mm/h")
