"""Tests for Step 3 historical verification; network calls are stubbed out."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import performance_service as perf
from app.services.performance_service import (
    PerformanceService,
    compute_metrics,
    compute_skill_scores,
)


def test_metrics_match_hand_calculation():
    # errors: +1, -1, +2  -> MAE 4/3, RMSE sqrt(6/3), bias 2/3
    metrics = compute_metrics([(11.0, 10.0), (19.0, 20.0), (32.0, 30.0)])
    assert metrics["mae"] == pytest.approx(4 / 3)
    assert metrics["rmse"] == pytest.approx(2**0.5)
    assert metrics["bias"] == pytest.approx(2 / 3)
    assert metrics["correlation"] == pytest.approx(0.99, abs=0.01)


def test_metrics_empty_and_constant_series():
    assert compute_metrics([])["mae"] is None
    assert compute_metrics([(0.0, 0.0)] * 5)["correlation"] is None


def test_skill_scores_favor_lower_error_and_sum_to_one():
    scores = compute_skill_scores({"A": 0.5, "B": 1.0, "C": 2.0})
    assert sum(scores.values()) == pytest.approx(1.0)
    assert scores["A"] > scores["B"] > scores["C"]


@pytest.mark.asyncio
async def test_performance_pairs_forecasts_with_observations(monkeypatch):
    start = datetime(2026, 9, 1, tzinfo=UTC)
    hours = [start + timedelta(hours=i) for i in range(24 * 7)]
    observations = {t: 25.0 for t in hours}

    async def fake_observations(client, location, om_variable):
        return observations

    async def fake_forecast(client, provider, location, om_variable, lead_day):
        offset = {"ECMWF IFS": 1.0, "NOAA GFS": 2.0, "ECMWF AIFS": 0.5, "DWD ICON": 1.5}[provider.get_model_name()]
        return {t: 25.0 + offset for t in hours[:-1]}  # one hour missing -> not scored

    service = PerformanceService()
    monkeypatch.setattr(service, "_fetch_observations", fake_observations)
    monkeypatch.setattr(service, "_fetch_archived_forecast", fake_forecast)
    result = await service.evaluate("Mumbai", "temperature", 7, 1)

    by_name = {m.model: m for m in result.models}
    assert result.data_mode == "real_archived_forecasts"
    assert by_name["ECMWF IFS"].samples == len(hours) - 1
    assert by_name["NOAA GFS"].mae == 2.0 and by_name["NOAA GFS"].bias == 2.0
    assert by_name["ECMWF AIFS"].skill_score > by_name["ECMWF IFS"].skill_score
    # Unconnected models are reported, never scored.
    assert by_name["NCUM-G"].mae is None and by_name["NCUM-G"].skill_score is None
    assert by_name["NCUM-G"].status == "unavailable"
    # Live but without archived forecasts: listed, never scored (no fabricated verification).
    assert by_name["NOAA AIGEFS"].status == "live" and by_name["NOAA AIGEFS"].mae is None
    assert by_name["DWD ICON"].mae == 1.5 and by_name["DWD ICON"].calibration == "archived_forecasts"
    assert "GraphCast" not in by_name and "Pangu-Weather" not in by_name  # optional, not running


@pytest.mark.asyncio
async def test_transient_source_failure_is_not_cached(monkeypatch):
    start = datetime(2026, 9, 1, tzinfo=UTC)
    hours = [start + timedelta(hours=i) for i in range(24 * 7)]
    calls = {"aifs": 0}

    async def fake_observations(client, location, om_variable):
        return {t: 25.0 for t in hours}

    async def fake_forecast(client, provider, location, om_variable, lead_day):
        if provider.get_model_name() == "ECMWF AIFS":
            calls["aifs"] += 1
            if calls["aifs"] == 1:
                raise perf.ProviderDataError("429 Too Many Requests")
        return {t: 26.0 for t in hours}

    service = PerformanceService()
    monkeypatch.setattr(service, "_fetch_observations", fake_observations)
    monkeypatch.setattr(service, "_fetch_archived_forecast", fake_forecast)

    first = {m.model: m for m in (await service.evaluate("Mumbai", "temperature", 7, 1)).models}
    assert first["ECMWF AIFS"].status == "error" and first["ECMWF AIFS"].mae is None
    second = {m.model: m for m in (await service.evaluate("Mumbai", "temperature", 7, 1)).models}
    assert second["ECMWF AIFS"].status == "live" and second["ECMWF AIFS"].mae == 1.0


@pytest.mark.asyncio
async def test_performance_endpoint_rejects_unknown_location():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/performance", params={"location": "Atlantis"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_performance_endpoint_reports_source_failure(monkeypatch):
    async def failing(*args, **kwargs):
        raise perf.ProviderDataError("ERA5 down")

    monkeypatch.setattr(perf.performance_service, "evaluate", failing)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/performance")
    assert response.status_code == 502
