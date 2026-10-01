"""Model lineup: new adapters, honest statuses, failure handling and variable-specific blending.

Network responses are replaced by small TEST FIXTURES shaped like the real APIs; production code
never uses them. Assertions check behaviour (filtering, exclusion, renormalisation), not weather values.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.trust import ModelTrust, TrustResponse
from app.schemas.weather import AllModelsForecastResponse, ForecastRecord, ModelDescriptor, ProviderForecast
from app.services.blend_service import BlendService
from app.services.weather import open_meteo_provider
from app.services.weather.aicon_provider import AICONProvider, parse_run_listing
from app.services.weather.aigefs_provider import AIGEFSProvider
from app.services.weather.forecast_provider import ForecastProvider, ProviderWaitingError
from app.services.weather.graphcast_provider import GraphCastProvider, PanguProvider
from app.services.weather.icon_provider import ICONProvider
from app.services.weather.ncum_provider import NCUMProvider, summarize_catalogue
from app.services.weather.weather_service import WeatherService

RUN = datetime(2026, 10, 1, 0, tzinfo=UTC)


# ---------------- NOAA AIGEFS (ensemble) ----------------

def aigefs_fixture():
    """TEST FIXTURE shaped like the Open-Meteo ensemble response (control + 2 members)."""
    times = [(RUN + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(-6, 13)]
    n = len(times)
    return (
        {"last_run_initialisation_time": int(RUN.timestamp()), "last_run_availability_time": int((RUN + timedelta(hours=9)).timestamp())},
        {
            "latitude": 19.0, "longitude": 73.0,
            "hourly": {
                "time": times,
                "temperature_2m": [30.0] * n,
                "temperature_2m_member01": [31.0] * n,
                "temperature_2m_member02": [29.0] * n,
                "wind_speed_10m": [10.0] * n,
                "wind_speed_10m_member01": [12.0] * n,
                "wind_speed_10m_member02": [8.0] * n,
            },
        },
    )


def test_aigefs_keeps_native_steps_after_the_run_with_real_spread():
    meta, payload = aigefs_fixture()
    result = AIGEFSProvider().normalize(meta, payload, RUN + timedelta(hours=10))
    assert result.status == "live" and result.init_time == RUN
    # Only 00/06/12 UTC (native 6-hourly) at or after the run: no pre-run or interpolated hours.
    assert [r.valid_time.hour for r in result.forecast] == [0, 6, 12]
    first = result.forecast[0]
    assert first.lead_time_hours == 0 and first.ensemble_members == 3
    assert first.temperature == pytest.approx(30.0)  # ensemble mean of 30, 31, 29
    assert first.temperature_spread == pytest.approx((2 / 3) ** 0.5)  # population std of the members
    assert first.precipitation is None  # deliberately not ingested
    assert result.variables == ["temperature", "wind_speed"]
    assert result.provenance["ensemble_members"] == 3


def test_aigefs_stale_run_is_waiting_not_live():
    meta, payload = aigefs_fixture()
    with pytest.raises(ProviderWaitingError):
        AIGEFSProvider().normalize(meta, payload, RUN + timedelta(hours=48))


# ---------------- DWD AICON / NCMRWF NCUM-G (official sources, no values) ----------------

def test_aicon_listing_parse_and_never_values():
    html = '<a href="../">../</a><a href="2026-09-30T18%3A00/">x</a><a href="2026-10-01T12%3A00/">y</a>'
    assert parse_run_listing(html) == ["2026-09-30T18:00", "2026-10-01T12:00"]
    assert AICONProvider().get_status() == "unavailable"


@pytest.mark.asyncio
async def test_unavailable_adapters_raise_instead_of_returning_values():
    for provider in (AICONProvider(), NCUMProvider(), GraphCastProvider(), PanguProvider()):
        with pytest.raises(Exception):
            await provider.get_forecast(19.0, 72.8, 2)


def test_ncum_catalogue_summary():
    # TEST FIXTURE shaped like the official NCMRWF API replies.
    models = {"models": [{"model_id": 1, "model_name": "global", "model_abbreviation": "ncum-g", "duration": "10 days"}]}
    products = {"products": [{"id": 3, "product_name": "Rain-Forecast", "active": True}, {"id": 4, "product_name": "Meteogram", "active": True}]}
    summary = summarize_catalogue(models, products, {"Rain-Forecast": [24, 48, 240], "Meteogram": []})
    assert summary["model_listed"] == "ncum-g · global · 10 days"
    assert summary["machine_readable_point_data"] is False
    assert summary["Rain-Forecast_hours"] == "24–240 h (3 steps)" and summary["Meteogram_hours"] == "none listed"


# ---------------- registry / service behaviour ----------------

class FakeLive(ForecastProvider):
    def __init__(self, name: str, temperature: float | None, precipitation: float | None = 0.2, fail: Exception | None = None):
        self.descriptor = ModelDescriptor(name=name, model_type="x", provider="x", status="live")
        self.temperature, self.precipitation, self.fail = temperature, precipitation, fail

    async def get_forecast(self, latitude, longitude, forecast_days):
        if self.fail:
            raise self.fail
        records = [
            ForecastRecord(model=self.descriptor.name, model_type="x", provider="x", latitude=latitude, longitude=longitude,
                           init_time=RUN, valid_time=RUN + timedelta(hours=h), lead_time_hours=h,
                           temperature=self.temperature, precipitation=self.precipitation)
            for h in range(3)
        ]
        return ProviderForecast(model=self.descriptor.name, model_type="x", provider="x", status="live", init_time=RUN, forecast=records)


class MustNotFetch(GraphCastProvider):
    async def get_forecast(self, latitude, longitude, forecast_days):  # pragma: no cover - must never run
        raise AssertionError("inactive models must never be fetched")


@pytest.mark.asyncio
async def test_inactive_models_are_never_fetched_and_failures_are_isolated():
    weather = WeatherService([
        FakeLive("A", 30.0),
        FakeLive("B", None, fail=ProviderWaitingError("run not published yet")),
        FakeLive("C", None, fail=RuntimeError("boom")),
        MustNotFetch(),
    ])
    result = {r.model: r for r in (await weather.get_all_models(19.0, 72.8, 1)).results}
    assert result["A"].status == "live"
    assert result["B"].status == "waiting" and result["B"].forecast == []
    assert result["C"].status == "error" and result["C"].forecast == []
    assert result["GraphCast"].status == "inactive" and result["GraphCast"].forecast == []


@pytest.mark.asyncio
async def test_open_meteo_reports_waiting_when_no_run_is_published(monkeypatch):
    def handler(request):  # TEST FIXTURE: every candidate run "not available"
        return httpx.Response(400, json={"error": True, "reason": "The requested model run is not available."})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(open_meteo_provider.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ProviderWaitingError):
        await ICONProvider().get_forecast(19.0, 72.8, 1)


class FakeWeather:
    def __init__(self, providers):
        self.providers = providers

    async def get_all_models(self, latitude, longitude, forecast_days):
        return AllModelsForecastResponse(
            latitude=latitude, longitude=longitude, forecast_days=forecast_days,
            results=[await p.get_forecast(latitude, longitude, forecast_days) if p.descriptor.status == "live" and not getattr(p, "fail", None)
                     else ProviderForecast(model=p.descriptor.name, model_type="x", provider="x", status="error" if getattr(p, "fail", None) else p.descriptor.status)
                     for p in self.providers],
        )


class FakeTrust:
    """Trust Engine output stand-in: weights for A/B/C, D live but not calibrated."""

    async def get_trust(self, location, variable, days, lead_day):
        def row(name, weight, reason=None):
            return ModelTrust(model=name, model_type="x", status="live", included=weight is not None, weight=weight,
                              weight_percent=None if weight is None else weight * 100, reasons=[reason] if reason else [])
        return TrustResponse(
            location=location, variable=variable, unit="°C", lead_day=lead_day, status="ok", historical_period_start=None,
            historical_period_end=None, historical_days=21, recent_days=7, method="x", formula=[],
            models=[row("A", 0.5), row("B", 0.3), row("C", 0.2),
                    row("D", None, "Forecast available · reliability not yet calibrated (no archived forecasts to verify); not weighted")],
        )


@pytest.mark.asyncio
async def test_blend_renormalises_over_valid_models_and_respects_variables():
    providers = [
        FakeLive("A", 20.0, precipitation=1.0),
        FakeLive("B", 24.0, precipitation=None),          # no rainfall from this model
        FakeLive("C", None, fail=RuntimeError("down")),   # failed this time
        FakeLive("D", 99.0, precipitation=5.0),           # live but uncalibrated -> not weighted
        GraphCastProvider(),
    ]
    blend = BlendService(FakeWeather(providers), FakeTrust())

    temperature = await blend.get_blend("Mumbai", "temperature", 1, 1, 21)
    assert [m.model for m in temperature.models_used] == ["A", "B"]
    point = temperature.forecast[0]
    assert point.effective_weights == pytest.approx({"A": 0.5 / 0.8, "B": 0.3 / 0.8})  # C and D not in the denominator
    assert point.blended_value == pytest.approx(20 * 0.625 + 24 * 0.375)
    excluded = {m.model: m.reason for m in temperature.excluded_models}
    assert "not yet calibrated" in excluded["D"] and "C" in excluded
    assert "GraphCast" not in excluded  # optional / not running never listed as a contributor

    rain = await blend.get_blend("Mumbai", "precipitation", 1, 1, 21)
    assert [m.model for m in rain.models_used] == ["A"]  # B has no rainfall values
    assert "No valid precipitation values" in {m.model: m.reason for m in rain.excluded_models}["B"]
    assert rain.forecast[0].blended_value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_demo_endpoints_are_gone():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/weather/ncum-demo/status")).status_code == 404
        assert (await client.post("/api/weather/ncum-demo/enable")).status_code == 404
