"""Tests for Step 7 forecast-based risk indicators; no network calls."""

from datetime import UTC, datetime, timedelta

import pytest

from app.data.risk_thresholds import RISK_RULES
from app.schemas.blend import BlendModel, BlendResponse
from app.schemas.uncertainty import UncertaintyResponse
from app.services.blend_service import blend_forecasts
from app.services.risk_service import (
    RiskService,
    Sample,
    accumulate_24h,
    assess,
    check_threshold_with_uncertainty,
    risk_level,
)
from app.services.uncertainty_service import compute_points

RULES = {r.risk_type: r for r in RISK_RULES}
HEAT, COLD, RAIN, WIND = RULES["HEAT"], RULES["COLD"], RULES["HEAVY_RAIN"], RULES["HIGH_WIND"]
T0 = datetime(2026, 9, 30, 6, tzinfo=UTC)


def sample(value, lower=None, upper=None, models=None, hour=0):
    return Sample(
        valid_time=T0 + timedelta(hours=hour), value=value,
        lower=value if lower is None else lower, upper=value if upper is None else upper,
        range_source="test", model_values=models or {},
    )


def test_temperature_below_threshold_is_normal():
    result = assess(HEAT, [sample(30.0, 29.5, 30.8, {"A": 30.2, "B": 29.9})])
    assert result.level == "NORMAL"
    assert result.range_position == "CLEARLY_BELOW" and not result.threshold_crossing


def test_temperature_above_heat_thresholds():
    assert risk_level(HEAT.elevated + 0.5, HEAT) == "ELEVATED"
    assert risk_level(HEAT.high + 0.1, HEAT) == "HIGH"
    result = assess(HEAT, [sample(HEAT.high + 1, models={"A": HEAT.high + 2, "B": HEAT.high - 1, "C": HEAT.high + 0.5})])
    assert result.level == "HIGH"
    assert result.model_consensus == "2/3"


def test_temperature_below_cold_threshold():
    result = assess(COLD, [sample(COLD.elevated - 1, models={"A": COLD.elevated - 2, "B": COLD.elevated + 1})])
    assert result.level == "ELEVATED"
    assert result.model_consensus == "1/2"
    assert risk_level(COLD.high - 0.5, COLD) == "HIGH"


def test_heavy_rain_uses_24h_accumulation():
    # 24 hours of 3 mm/h = 72 mm -> ELEVATED (not 3 mm "daily")
    hourly = [sample(3.0, models={"A": 3.5, "B": 2.0}, hour=h) for h in range(24)]
    windows = accumulate_24h(hourly)
    assert windows[-1].value == pytest.approx(72.0) and windows[-1].hours == 24
    assert windows[-1].model_values == {"A": pytest.approx(84.0), "B": pytest.approx(48.0)}
    result = assess(RAIN, windows)
    assert result.level == "ELEVATED" and result.accumulation_hours == 24
    assert (result.lower, result.upper) == (pytest.approx(48.0), pytest.approx(84.0))
    assert result.threshold_crossing  # 48–84 mm straddles 64.5 mm


def test_rain_window_never_exceeds_24_hours():
    hourly = [sample(1.0, hour=h) for h in range(40)]
    assert max(w.hours for w in accumulate_24h(hourly)) == 24


def test_high_wind_above_threshold():
    result = assess(WIND, [sample(WIND.high + 5, WIND.high + 1, WIND.high + 9, {"A": WIND.high + 3})])
    assert result.level == "HIGH" and result.unit == "km/h"
    assert result.range_position == "CLEARLY_ABOVE"


def test_uncertainty_crossing_threshold():
    assert check_threshold_with_uncertainty(29.5, 29.0, 32.0, 30.0) == "THRESHOLD_CROSSED"
    result = assess(HEAT, [sample(HEAT.elevated - 0.5, HEAT.elevated - 1.2, HEAT.elevated + 0.6)])
    assert result.level == "NORMAL" and result.threshold_crossing
    assert "cannot be ruled out" in result.messages[0]


def test_uncertainty_entirely_below_threshold():
    assert check_threshold_with_uncertainty(26.5, 25.0, 28.0, 30.0) == "CLEARLY_BELOW"
    assert check_threshold_with_uncertainty(32.0, 31.0, 34.0, 30.0) == "CLEARLY_ABOVE"
    assert not assess(HEAT, [sample(26.5, 25.0, 28.0)]).threshold_crossing


def test_missing_variable_is_data_unavailable():
    result = assess(WIND, [])
    assert result.status == "data_unavailable" and result.level is None and result.forecast_value is None


def test_same_input_same_risk():
    samples = [sample(36.2, 35.1, 37.0, {"A": 36.0, "B": 37.1}, hour=h) for h in range(3)]
    assert assess(HEAT, samples) == assess(HEAT, samples)


def test_peak_hour_and_timeline():
    samples = [sample(v, hour=h) for h, v in enumerate([30.0, 36.0, 41.0, 33.0])]
    result = assess(HEAT, samples)
    assert result.peak_time == T0 + timedelta(hours=2) and result.forecast_value == 41.0
    assert [p.level for p in result.timeline] == ["NORMAL", "ELEVATED", "HIGH", "NORMAL"]


class NoDataBlend:
    async def get_blend(self, location, variable, forecast_days, lead_day, days):
        return BlendResponse(
            location=location, latitude=0, longitude=0, variable=variable, unit="x", forecast_days=forecast_days,
            trust_lead_day=lead_day, status="insufficient_data", method="x", formula=[],
            models_used=[], excluded_models=[], forecast=[],
        )


class NoDataUncertainty:
    async def get_uncertainty(self, location, variable, forecast_days, lead_day, days):
        return UncertaintyResponse(
            location=location, variable=variable, unit="x", forecast_days=forecast_days, lead_day=lead_day,
            status="insufficient_data", explanation="x", formula=[], thresholds=None, historical=None,
            models_used=[], excluded_models=[], forecast=[],
        )


@pytest.mark.asyncio
async def test_no_forecast_models_is_insufficient_data():
    result = await RiskService(NoDataBlend(), NoDataUncertainty()).get_risks("Mumbai", 2, 1, 21, now=T0)
    assert result.status == "insufficient_data"
    assert result.message == "Risk assessment unavailable because forecast data is unavailable."
    assert all(r.status == "data_unavailable" for r in result.risks)


class OneValueBlend:
    """Temperature 36 °C from two models; other variables fail like an unavailable source."""

    async def get_blend(self, location, variable, forecast_days, lead_day, days):
        if variable != "temperature":
            raise RuntimeError("source down")
        weights = {"A": 0.6, "B": 0.4}
        series = {"A": {T0: 36.0, T0 - timedelta(hours=1): 50.0}, "B": {T0: 36.0}}
        return BlendResponse(
            location=location, latitude=0, longitude=0, variable=variable, unit="°C", forecast_days=forecast_days,
            trust_lead_day=lead_day, status="ok", method="x", formula=[],
            models_used=[BlendModel(model=m, trust_weight=w, trust_weight_percent=w * 100, init_time=T0, points=1) for m, w in weights.items()],
            excluded_models=[], forecast=blend_forecasts(series, weights),
        )


class OneValueUncertainty:
    async def get_uncertainty(self, location, variable, forecast_days, lead_day, days):
        blend = await OneValueBlend().get_blend(location, variable, forecast_days, lead_day, days)
        return UncertaintyResponse(
            location=location, variable=variable, unit="°C", forecast_days=forecast_days, lead_day=lead_day,
            status="ok", explanation="x", formula=[], thresholds=None, historical=None,
            models_used=["A", "B"], excluded_models=[], forecast=compute_points(blend.forecast, None, None, False),
        )


@pytest.mark.asyncio
async def test_service_uses_blend_ignores_past_hours_and_isolates_missing_variables():
    result = await RiskService(OneValueBlend(), OneValueUncertainty()).get_risks("Mumbai", 2, 1, 21, now=T0)
    by_type = {r.risk_type: r for r in result.risks}
    assert result.status == "ok"
    assert by_type["HEAT"].level == "ELEVATED" and by_type["HEAT"].forecast_value == 36.0  # past 50 °C hour ignored
    assert by_type["HEAT"].model_consensus == "2/2"
    assert by_type["HEAVY_RAIN"].status == "data_unavailable" and "source down" in by_type["HEAVY_RAIN"].reason
    assert by_type["HIGH_WIND"].status == "data_unavailable"
