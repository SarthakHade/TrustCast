"""Location search + coordinate-based pipeline. External HTTP is mocked; fixtures are marked as such."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.trust import ModelTrust, TrustResponse
from app.schemas.weather import AllModelsForecastResponse, ForecastRecord, ProviderForecast
from app.services import geocoding_service as geo
from app.services.blend_service import BlendService
from app.services.location_service import annotate_grid_distance, haversine_km, location_key, resolve_location
from app.services.performance_service import PerformanceService

# TEST FIXTURE shaped like a real Open-Meteo geocoding response (values as returned for this query).
ICHALKARANJI = {
    "id": 1269834, "name": "Ichalkaranji", "latitude": 16.69117, "longitude": 74.46054, "feature_code": "PPL",
    "country_code": "IN", "country": "India", "admin1": "Maharashtra", "admin2": "Kolhapur", "admin3": "Hatkanangle",
    "population": 287353, "elevation": 551.0, "timezone": "Asia/Kolkata",
}
SELECTED = {"name": "Ichalkaranji", "latitude": 16.69117, "longitude": 74.46054}


@pytest.fixture
def geocoder(monkeypatch):
    """Route the geocoding service's HTTP calls to a mock transport; record the requests."""
    calls: list[httpx.Request] = []
    state = {"status": 200, "body": {"results": [ICHALKARANJI]}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(state["status"], json=state["body"])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(geo.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    geo.geocoding_service.cache._entries.clear()
    yield calls, state
    geo.geocoding_service.cache._entries.clear()


async def get(path: str, **params):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, params=params)


# ---------------- search endpoint ----------------

@pytest.mark.asyncio
async def test_search_returns_normalized_real_fields_and_filters_india(geocoder):
    calls, _ = geocoder
    response = await get("/api/locations/search", q="Ichalkaranji")
    assert response.status_code == 200
    [result] = response.json()["results"]
    assert (result["latitude"], result["longitude"]) == (16.69117, 74.46054)  # exactly as returned
    assert result["display_name"] == "Ichalkaranji, Hatkanangle, Kolhapur, Maharashtra, India"
    assert result["area"] == "Hatkanangle, Kolhapur, Maharashtra, India"
    assert result["admin1"] == "Maharashtra" and result["country_code"] == "IN"
    assert "admin4" not in result  # fields the API did not return are not invented
    assert calls[0].url.params["countryCode"] == "IN" and calls[0].url.params["name"] == "Ichalkaranji"


@pytest.mark.asyncio
async def test_search_is_cached(geocoder):
    calls, _ = geocoder
    await get("/api/locations/search", q="Ichalkaranji")
    await get("/api/locations/search", q="  ichalkaranji ")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_empty_or_short_search_is_rejected(geocoder):
    calls, _ = geocoder
    assert (await get("/api/locations/search", q="")).status_code == 422
    assert (await get("/api/locations/search", q="a")).status_code == 422
    assert (await get("/api/locations/search", q="  ")).status_code == 422
    assert calls == []


@pytest.mark.asyncio
async def test_no_results_returns_empty_list_not_a_fallback(geocoder):
    _, state = geocoder
    state["body"] = {"generationtime_ms": 0.2}  # the real API omits "results" when nothing matches
    response = await get("/api/locations/search", q="Munshi Nagar")
    assert response.status_code == 200 and response.json()["results"] == []


@pytest.mark.asyncio
async def test_geocoder_failure_is_reported(geocoder):
    _, state = geocoder
    state["status"] = 503
    response = await get("/api/locations/search", q="Powai")
    assert response.status_code == 502


# ---------------- coordinates & no fallback ----------------

@pytest.mark.asyncio
async def test_invalid_or_partial_coordinates_are_rejected():
    assert (await get("/api/blend", latitude=100, longitude=72)).status_code == 422
    assert (await get("/api/blend", latitude=16.7)).status_code == 422
    assert (await get("/api/trust", longitude=74.4)).status_code == 422


def test_selected_coordinates_are_kept_and_presets_still_resolve():
    assert resolve_location(SELECTED) == SELECTED  # no snapping to Kolhapur / Pune / Mumbai
    mumbai = resolve_location("mumbai")
    assert mumbai["name"] == "Mumbai" and (mumbai["latitude"], mumbai["longitude"]) == (19.076, 72.8777)
    with pytest.raises(KeyError):
        resolve_location("Ichalkaranji")  # an unknown NAME is an error, never a silent preset fallback
    with pytest.raises(KeyError):
        resolve_location({"name": "x", "latitude": 95, "longitude": 10})


def test_cache_keys_use_coordinates_not_names():
    assert location_key(SELECTED) != location_key(resolve_location("Mumbai"))
    assert location_key({"name": "A", "latitude": 16.69117, "longitude": 74.46054}) == location_key(SELECTED)


def test_haversine_and_grid_distance_flag():
    assert haversine_km(19.076, 72.8777, 18.5204, 73.8567) == pytest.approx(119.5, abs=1.5)  # Mumbai–Pune
    near = annotate_grid_distance({"grid_latitude": 16.75, "grid_longitude": 74.5}, 16.69117, 74.46054)
    assert near["grid_distance_km"] == pytest.approx(7.7, abs=0.3) and near["grid_beyond_10km"] is False
    far = annotate_grid_distance({"grid_latitude": 16.5, "grid_longitude": 74.5}, 16.69117, 74.46054)
    assert far["grid_beyond_10km"] is True
    assert annotate_grid_distance({}, 1.0, 2.0) == {"requested_latitude": 1.0, "requested_longitude": 2.0}


# ---------------- pipeline uses the selected coordinates ----------------

RUN = datetime(2026, 10, 1, tzinfo=UTC)


class RecordingWeather:
    def __init__(self):
        self.requests = []

    async def get_all_models(self, latitude, longitude, forecast_days):
        self.requests.append((latitude, longitude))
        record = ForecastRecord(model="A", model_type="x", provider="x", latitude=latitude, longitude=longitude,
                                init_time=RUN, valid_time=RUN + timedelta(hours=1), lead_time_hours=1, temperature=30.0)
        return AllModelsForecastResponse(latitude=latitude, longitude=longitude, forecast_days=forecast_days, results=[
            ProviderForecast(model="A", model_type="x", provider="x", status="live", init_time=RUN, forecast=[record])])


class RecordingTrust:
    def __init__(self):
        self.locations = []

    async def get_trust(self, location, variable, days, lead_day):
        self.locations.append(location)
        return TrustResponse(
            location=location["name"], variable=variable, unit="°C", lead_day=lead_day, status="ok",
            historical_period_start=None, historical_period_end=None, historical_days=21, recent_days=7, method="x", formula=[],
            models=[ModelTrust(model="A", model_type="x", status="live", included=True, weight=1.0, weight_percent=100.0)])


@pytest.mark.asyncio
async def test_blend_requests_forecasts_and_trust_for_the_selected_point():
    weather, trust = RecordingWeather(), RecordingTrust()
    result = await BlendService(weather, trust).get_blend(dict(SELECTED), "temperature", 1, 1, 21)
    assert weather.requests == [(16.69117, 74.46054)]
    assert trust.locations[0]["latitude"] == 16.69117 and trust.locations[0]["name"] == "Ichalkaranji"
    assert result.location == "Ichalkaranji" and (result.latitude, result.longitude) == (16.69117, 74.46054)


@pytest.mark.asyncio
async def test_verification_fetches_era5_and_archives_at_the_selected_point(monkeypatch):
    seen = []
    hours = [datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(24 * 8)]

    async def fake_observations(client, location, om_variable):  # TEST FIXTURE stand-in for ERA5
        seen.append(("era5", location["latitude"], location["longitude"]))
        return {t: 25.0 for t in hours}

    async def fake_archived(client, provider, location, om_variable, lead_day):  # TEST FIXTURE stand-in
        seen.append((provider.get_model_name(), location["latitude"], location["longitude"]))
        return {t: 25.5 for t in hours}

    service = PerformanceService()
    monkeypatch.setattr(service, "_fetch_observations", fake_observations)
    monkeypatch.setattr(service, "_fetch_archived_forecast", fake_archived)
    result = await service.evaluate(dict(SELECTED), "temperature", 7, 1)
    assert result.location == "Ichalkaranji" and (result.latitude, result.longitude) == (16.69117, 74.46054)
    assert seen and all((lat, lon) == (16.69117, 74.46054) for _, lat, lon in seen)


@pytest.mark.asyncio
async def test_preset_city_endpoint_still_works_by_name(monkeypatch):
    async def fake_evaluate(location, variable, days, lead_day):
        assert location == "Mumbai"  # unchanged backward-compatible path
        raise KeyError("stop here")

    from app.services.performance_service import performance_service
    monkeypatch.setattr(performance_service, "evaluate", fake_evaluate)
    assert (await get("/api/performance", location="Mumbai")).status_code == 404
