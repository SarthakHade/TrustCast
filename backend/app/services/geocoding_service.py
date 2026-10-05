"""Location search via the free Open-Meteo Geocoding API (https://open-meteo.com/en/docs/geocoding-api).

* Results are restricted to India with `countryCode=IN`.
* Every field returned to the UI comes from the API response; nothing is invented. Optional
  fields the API does not return for a place are simply omitted.
* No results → an empty list (the caller shows "No locations found"); API failures raise.
* Recent queries are cached in memory (the project's existing TTL cache) to respect the free
  service's rate limits; the frontend also debounces typing.
"""

from typing import Any

import httpx

from app.config import GEOCODING_CACHE_TTL_SECONDS, OPEN_METEO_GEOCODING_URL
from app.services.weather.cache import InMemoryTTLCache

COUNTRY_CODE = "IN"
MAX_RESULTS = 10
OPTIONAL_FIELDS = ("admin1", "admin2", "admin3", "admin4", "feature_code", "population", "elevation", "timezone")


class GeocodingError(RuntimeError):
    """The geocoding service could not be reached or returned an unusable response."""


def normalize_result(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only real API fields; skip entries without a name or valid coordinates."""
    name, lat, lon = raw.get("name"), raw.get("latitude"), raw.get("longitude")
    if not isinstance(name, str) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    result: dict[str, Any] = {"id": raw.get("id"), "name": name, "latitude": float(lat), "longitude": float(lon)}
    for field in OPTIONAL_FIELDS:
        if raw.get(field) not in (None, ""):
            result[field] = raw[field]
    for field in ("country", "country_code"):
        if raw.get(field):
            result[field] = raw[field]
    # Parent areas from the API's own admin hierarchy, most local first, without repeats.
    parents: list[str] = []
    for field in ("admin4", "admin3", "admin2", "admin1", "country"):
        value = raw.get(field)
        if isinstance(value, str) and value and value != name and value not in parents:
            parents.append(value)
    result["area"] = ", ".join(parents)
    result["display_name"] = ", ".join([name, *parents])
    return result


class GeocodingService:
    def __init__(self) -> None:
        self.cache = InMemoryTTLCache(ttl_seconds=GEOCODING_CACHE_TTL_SECONDS)

    async def search(self, query: str) -> list[dict[str, Any]]:
        text = " ".join(query.split())
        if len(text) < 2:
            raise ValueError("Search text must have at least 2 characters")
        return await self.cache.get_or_set(f"geo:{text.casefold()}", lambda: self._search(text))

    async def _search(self, text: str) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    OPEN_METEO_GEOCODING_URL,
                    params={"name": text, "count": MAX_RESULTS, "language": "en", "format": "json", "countryCode": COUNTRY_CODE},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocodingError(f"Location search is unavailable right now ({type(exc).__name__})") from exc
        if not isinstance(payload, dict):
            raise GeocodingError("Location search returned an unexpected response")
        return [r for r in (normalize_result(raw) for raw in payload.get("results") or []) if r is not None]


geocoding_service = GeocodingService()
