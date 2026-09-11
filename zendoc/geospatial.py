"""Small, deterministic geographic helpers shared by Finder adapters.

Production PostGIS support is reported separately by the readiness probe.  The
helpers here provide a bounded SQLite/PostgreSQL compatibility path and are
only used after latitude/longitude values have passed validation.
"""
from __future__ import annotations

import math


EARTH_RADIUS_KM = 6371.0088


def haversine_km(latitude_a, longitude_a, latitude_b, longitude_b) -> float | None:
    """Return great-circle distance in kilometres, or ``None`` for bad data."""
    values = (latitude_a, longitude_a, latitude_b, longitude_b)
    try:
        lat_a, lon_a, lat_b, lon_b = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (lat_a, lon_a, lat_b, lon_b)):
        return None
    if not (-90 <= lat_a <= 90 and -90 <= lat_b <= 90 and -180 <= lon_a <= 180 and -180 <= lon_b <= 180):
        return None
    lat_a, lat_b = math.radians(lat_a), math.radians(lat_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(float(longitude_b) - float(longitude_a))
    sine = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(min(1.0, math.sqrt(max(0.0, sine))))


def bounding_box(latitude, longitude, radius_km: float) -> tuple[float, float, float, float]:
    """Return spherical bounds; west > east denotes a dateline crossing."""
    lat = float(latitude)
    lon = float(longitude)
    radius = float(radius_km)
    if not all(math.isfinite(value) for value in (lat, lon, radius)):
        raise ValueError("Coordinates and radius must be finite.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and radius >= 0):
        raise ValueError("Coordinates or radius are out of range.")
    angular = min(math.pi, radius / EARTH_RADIUS_KM)
    # Expand slightly so floating-point rounding cannot exclude boundary rows.
    lat_delta = math.degrees(angular) + 1e-9
    south, north = max(-90.0, lat - lat_delta), min(90.0, lat + lat_delta)
    if south <= -90 or north >= 90:
        return south, north, -180.0, 180.0
    lon_delta = math.degrees(math.asin(min(1.0, math.sin(angular) / math.cos(math.radians(lat))))) + 1e-9
    west = (lon - lon_delta + 180.0) % 360.0 - 180.0
    east = (lon + lon_delta + 180.0) % 360.0 - 180.0
    return south, north, west, east


def within_radius(record: dict, latitude, longitude, radius_km: float) -> bool:
    distance = haversine_km(latitude, longitude, record.get("latitude"), record.get("longitude"))
    return distance is not None and distance <= float(radius_km) + 1e-9


def nearby_records(records, latitude, longitude, radius_km):
    """Filter before limiting and order nearest first, preserving stable ties."""
    result = []
    for record in records:
        distance = haversine_km(latitude, longitude, record.get("latitude"), record.get("longitude"))
        if distance is not None and distance <= float(radius_km) + 1e-9:
            result.append({**record, "distance_km": distance})
    return sorted(result, key=lambda record: record["distance_km"])

