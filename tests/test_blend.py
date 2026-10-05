"""Tests for Step 5 trust-weighted blending; no network calls."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.trust import ModelTrust, TrustResponse
from app.schemas.weather import AllModelsForecastResponse, ForecastRecord, ProviderForecast
from app.services.blend_service import BlendService, blend_forecasts

T0 = datetime(2026, 9, 30, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)
WEIGHTS = {"A": 0.5, "B": 0.3, "C": 0.2}


def test_weighted_average_is_correct():
    series = {"A": {T0: 20.0}, "B": {T0: 24.0}, "C": {T0: 22.0}}
    [point] = blend_forecasts(series, WEIGHTS)
    assert point.status == "ok"
    assert point.blended_value == pytest.approx(20 * 0.5 + 24 * 0.3 + 22 * 0.2)  # 21.6
    assert point.contributors == {"A": 20.0, "B": 24.0, "C": 22.0}


def test_effective_weights_sum_to_one():
    series = {"A": {T0: 20.0, T1: 21.0}, "B": {T0: 24.0, T1: 23.0}, "C": {T0: 22.0, T1: 22.5}}
    for point in blend_forecasts(series, {"A": 3.0, "B": 2.0, "C": 1.0}):  # unnormalized input
        assert sum(point.effective_weights.values()) == pytest.approx(1.0)


def test_missing_model_is_renormalized_not_zero():
    series = {"A": {T0: 20.0}, "B": {T0: 24.0}, "C": {T0: None}}
    [point] = blend_forecasts(series, WEIGHTS)
    assert "C" not in point.contributors
    assert point.renormalized
    assert point.effective_weights["A"] == pytest.approx(0.5 / 0.8)  # 62.5%
    assert point.effective_weights["B"] == pytest.approx(0.3 / 0.8)  # 37.5%
    assert point.blended_value == pytest.approx(20 * 0.625 + 24 * 0.375)


def test_all_models_missing_reports_insufficient_data():
    series = {"A": {T0: None}, "B": {T0: None}}
    [point] = blend_forecasts(series, WEIGHTS)
    assert point.status == "insufficient_data"
    assert point.blended_value is None
    assert blend_forecasts({}, WEIGHTS) == []


def test_models_are_aligned_by_valid_time():
    # B starts an hour later; C only has T2. Values must never mix across timestamps.
    series = {"A": {T0: 10.0, T1: 11.0, T2: 12.0}, "B": {T1: 21.0, T2: 22.0}, "C": {T2: 32.0}}
    points = {p.valid_time: p for p in blend_forecasts(series, WEIGHTS)}
    assert points[T0].contributors == {"A": 10.0} and points[T0].blended_value == pytest.approx(10.0)
    assert points[T1].blended_value == pytest.approx((11 * 0.5 + 21 * 0.3) / 0.8)
    assert points[T2].blended_value == pytest.approx(12 * 0.5 + 22 * 0.3 + 32 * 0.2)
    assert [p.valid_time for p in blend_forecasts(series, WEIGHTS)] == [T0, T1, T2]


def test_same_input_gives_identical_output():
    series = {"A": {T0: 20.123456}, "B": {T0: 24.987654}}
    assert blend_forecasts(series, WEIGHTS) == blend_forecasts(series, WEIGHTS)


def test_full_precision_is_kept():
    [point] = blend_forecasts({"A": {T0: 25.237481}, "B": {T0: 25.1}}, {"A": 0.7, "B": 0.3})
    assert point.blended_value == pytest.approx(25.237481 * 0.7 + 25.1 * 0.3, abs=1e-12)


def _record(model: str, t: datetime, value: float | None) -> ForecastRecord:
    return ForecastRecord(
        model=model, model_type="x", provider="x", latitude=19.0, longitude=73.0,
        init_time=T0, valid_time=t, lead_time_hours=int((t - T0).total_seconds() // 3600),
        temperature=value,
    )


class FakeWeather:
    async def get_all_models(self, latitude, longitude, forecast_days):
        def live(name, values):
            return ProviderForecast(
                model=name, model_type="x", provider="x", status="live", init_time=T0,
                forecast=[_record(name, t, v) for t, v in values],
            )
        return AllModelsForecastResponse(
            latitude=latitude, longitude=longitude, forecast_days=forecast_days,
            results=[
                live("ECMWF IFS", [(T0, 30.0), (T1, 31.0)]),
                live("NOAA GFS", [(T0, 32.0), (T1, None)]),
                ProviderForecast(model="NCUM", model_type="x", provider="x",
                                 status="data_unavailable", error="No endpoint"),
            ],
        )


class FakeTrust:
    async def get_trust(self, location, variable, days, lead_day):
        def row(name, weight, status="live"):
            return ModelTrust(model=name, model_type="x", status=status, included=weight is not None,
                              weight=weight, weight_percent=None if weight is None else weight * 100)
        return TrustResponse(
            location=location["name"] if isinstance(location, dict) else location, variable=variable, unit="°C", lead_day=lead_day, status="ok",
            historical_period_start=None, historical_period_end=None, historical_days=21,
            recent_days=7, method="x", formula=[],
            models=[row("ECMWF IFS", 0.75), row("NOAA GFS", 0.25), row("NCUM", None, "data_unavailable")],
        )


@pytest.mark.asyncio
async def test_blend_service_uses_step2_forecasts_and_step4_weights():
    result = await BlendService(FakeWeather(), FakeTrust()).get_blend("Mumbai", "temperature", 2, 1, 21)
    assert result.status == "ok"
    assert [m.model for m in result.models_used] == ["ECMWF IFS", "NOAA GFS"]
    assert [m.model for m in result.excluded_models] == ["NCUM"]
    first, second = result.forecast
    assert first.blended_value == pytest.approx(30 * 0.75 + 32 * 0.25)
    assert second.contributors == {"ECMWF IFS": 31.0} and second.blended_value == pytest.approx(31.0)


@pytest.mark.asyncio
async def test_blend_endpoint_rejects_unknown_location():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/blend", params={"location": "Atlantis"})
    assert response.status_code == 404
