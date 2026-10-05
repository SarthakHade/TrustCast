"""Forecast location context shared by every pipeline step.

A location is either
  * a preset name from app/data/locations.py (backward compatible, e.g. "Mumbai"), or
  * a selected point {"name", "latitude", "longitude"} — typically a real geocoder result.

Selected coordinates are used exactly as given: there is no fallback to, or substitution with,
a preset city. Caches are keyed by coordinates, so two places never share results.
"""

import math

from app.data.locations import DEMO_LOCATIONS

LocationInput = str | dict
EARTH_RADIUS_KM = 6371.0088
# Model grid points farther than this from the selected coordinates are flagged in provenance.
GRID_DISTANCE_NOTE_KM = 10.0


def resolve_location(location: LocationInput) -> dict:
    """Return {"name", "latitude", "longitude"} for a preset name or a selected point."""
    if isinstance(location, dict):
        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KeyError("A selected location needs numeric latitude and longitude") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise KeyError(f"Coordinates out of range: {latitude}, {longitude}")
        name = str(location.get("name") or f"{latitude:.4f}, {longitude:.4f}")
        return {"name": name, "latitude": latitude, "longitude": longitude}

    preset = next((loc for loc in DEMO_LOCATIONS if loc["name"].casefold() == str(location).casefold()), None)
    if preset is None:
        names = ", ".join(loc["name"] for loc in DEMO_LOCATIONS)
        raise KeyError(f"Unknown location '{location}'. Use one of: {names}, or pass latitude/longitude")
    return dict(preset)


def location_key(location: dict) -> str:
    """Cache key from coordinates (≈11 m precision), never from the display name."""
    return f"{location['latitude']:.4f},{location['longitude']:.4f}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def annotate_grid_distance(provenance: dict, latitude: float, longitude: float) -> dict:
    """Record the requested point and its real distance to the model grid point the source used."""
    provenance["requested_latitude"] = round(latitude, 5)
    provenance["requested_longitude"] = round(longitude, 5)
    grid_lat, grid_lon = provenance.get("grid_latitude"), provenance.get("grid_longitude")
    if isinstance(grid_lat, (int, float)) and isinstance(grid_lon, (int, float)):
        distance = haversine_km(latitude, longitude, float(grid_lat), float(grid_lon))
        provenance["grid_distance_km"] = round(distance, 2)
        provenance["grid_beyond_10km"] = distance > GRID_DISTANCE_NOTE_KM
    return provenance
