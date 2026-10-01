"""Unit and API tests for the Step 2 ingestion layer; no live network calls."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.weather import ForecastRecord, ModelDescriptor, ProviderForecast
from app.services.weather.ecmwf_ifs_provider import ECMWFIFSProvider
from app.services.weather.forecast_provider import (
    ForecastProvider,
    ProviderDataError,
)
from app.services.weather.weather_service import WeatherService


def sample_payload() -> dict:
    return {
        "latitude": 19.0,
        "longitude": 73.0,
        "hourly": {
            "time": ["2026-09-29T06:00", "2026-09-29T07:00"],
            "temperature_2m": [31.4, 31.2],
            "precipitation": [0.0, 0.4],
            "wind_speed_10m": [4.0, 5.2],
            "relative_humidity_2m": [67, 68],
        },
    }


def test_provider_implements_common_interface():
    provider = ECMWFIFSProvider()
    assert isinstance(provider, ForecastProvider)
    assert provider.get_model_name() == "ECMWF IFS"
    assert provider.get_status() == "live"


def test_forecast_normalization_preserves_init_time_and_lead_time():
    init_time = datetime(2026, 9, 29, 6, tzinfo=UTC)
    forecast = ECMWFIFSProvider().normalize_payload(sample_payload(), init_time)

    assert forecast.status == "live"
    assert forecast.init_time == init_time
    assert len(forecast.forecast) == 2
    assert forecast.forecast[0].lead_time_hours == 0
    assert forecast.forecast[1].lead_time_hours == 1
    assert forecast.forecast[1].precipitation == 0.4


def test_missing_optional_variable_is_returned_as_null():
    init_time = datetime(2026, 9, 29, 6, tzinfo=UTC)
    payload = sample_payload()
    del payload["hourly"]["relative_humidity_2m"]

    forecast = ECMWFIFSProvider().normalize_payload(payload, init_time)
    assert forecast.forecast[0].humidity is None


def test_malformed_provider_response_is_rejected():
    init_time = datetime(2026, 9, 29, 6, tzinfo=UTC)
    payload = sample_payload()
    payload["hourly"]["precipitation"] = [-0.1, 0.4]

    with pytest.raises(ProviderDataError):
        ECMWFIFSProvider().normalize_payload(payload, init_time)


class FailingProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="Failing model",
        model_type="Test",
        provider="Test",
        status="live",
    )

    async def get_forecast(self, latitude, longitude, forecast_days):
        raise ProviderDataError("source unavailable")


class WorkingProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="Working model",
        model_type="Test",
        provider="Test",
        status="live",
    )

    async def get_forecast(self, latitude, longitude, forecast_days):
        init_time = datetime(2026, 9, 29, 6, tzinfo=UTC)
        return ProviderForecast(
            model=self.get_model_name(),
            model_type="Test",
            provider="Test",
            status="live",
            init_time=init_time,
            forecast=[
                ForecastRecord(
                    model=self.get_model_name(),
                    model_type="Test",
                    provider="Test",
                    latitude=latitude,
                    longitude=longitude,
                    init_time=init_time,
                    valid_time=init_time,
                    lead_time_hours=0,
                )
            ],
        )


@pytest.mark.asyncio
async def test_one_provider_failure_does_not_block_other_results():
    service = WeatherService(providers=[FailingProvider(), WorkingProvider()])
    response = await service.get_all_models(19.076, 72.8777, 1)

    assert response.results[0].status == "error"
    assert response.results[1].status == "live"
    assert len(response.results[1].forecast) == 1


@pytest.mark.asyncio
async def test_model_registry_and_locations_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        models_response = await client.get("/api/weather/models")
        locations_response = await client.get("/api/weather/locations")

    assert models_response.status_code == 200
    models = models_response.json()["models"]
    by_name = {model["name"]: model for model in models}
    assert list(by_name) == [
        "ECMWF IFS", "NOAA GFS", "ECMWF AIFS", "NCUM-G", "DWD AICON", "NOAA AIGEFS",
        "DWD ICON", "GraphCast", "Pangu-Weather",
    ]
    assert by_name["GraphCast"]["status"] == "inactive" and by_name["GraphCast"]["tier"] == "optional"
    assert by_name["Pangu-Weather"]["status"] == "inactive"
    assert by_name["DWD ICON"]["tier"] == "optional"
    assert all(m["status"] != "demo" for m in models)
    assert locations_response.status_code == 200
    assert [location["name"] for location in locations_response.json()] == [
        "Mumbai",
        "Delhi",
        "Pune",
        "Kolkata",
        "Chennai",
    ]


@pytest.mark.asyncio
async def test_weather_endpoint_validates_coordinates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/weather/all-models?latitude=100&longitude=72")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ncum_adapter_is_honest_and_never_returns_values(monkeypatch):
    """NCUM-G is unavailable: no values, official source checked and reported, excluded from scoring."""
    from app.services.weather.ncum_provider import NCUMProvider

    async def fake_probe(self):  # test fixture: stands in for the official NCMRWF API call
        return {"official_api": "fixture", "machine_readable_point_data": False}

    monkeypatch.setattr(NCUMProvider, "probe", fake_probe)
    from app.services.weather.weather_service import weather_service
    weather_service.probe_cache._entries.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/weather/forecast?latitude=19.076&longitude=72.8777&model=NCUM-G")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["forecast"] == []
    assert data["provider"] == "NCMRWF / MoES"
    assert data["source_url"] == "https://nwp.ncmrwf.gov.in/HomePage/NEPS-prod-1.php"
    assert "no machine-readable NCUM-G point-forecast feed" in data["error"]
    assert data["provenance"]["machine_readable_point_data"] is False
