"""Tests for the Step 6 Uncertainty Engine; no network calls."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.blend import BlendModel, BlendResponse
from app.services.blend_service import blend_forecasts
from app.services.uncertainty_service import (
    UncertaintyService,
    classify,
    compute_points,
    disagreement_stats,
    historical_blend_errors,
    historical_error_summary,
    spread_thresholds,
)

T0 = datetime(2026, 9, 30, tzinfo=UTC)
HOURS = [T0 + timedelta(hours=i) for i in range(48)]


def points_for(series, weights):
    return compute_points(blend_forecasts(series, weights), None, None, non_negative=False)


def test_three_models_min_max_spread():
    [p] = points_for({"A": {T0: 20.0}, "B": {T0: 22.0}, "C": {T0: 24.0}}, {"A": 1, "B": 1, "C": 1})
    assert (p.model_min, p.model_max, p.model_spread) == (20.0, 24.0, 4.0)
    assert p.model_mean == pytest.approx(22.0)
    assert p.status == "ok"


def test_weighted_std_matches_formula():
    contributors = {"A": 20.0, "B": 24.0, "C": 22.0}
    weights = {"A": 0.5, "B": 0.3, "C": 0.2}
    blended = 21.6
    stats = disagreement_stats(contributors, weights, blended)
    expected = math.sqrt(0.5 * 1.6**2 + 0.3 * 2.4**2 + 0.2 * 0.4**2)
    assert stats["weighted_std"] == pytest.approx(expected)


def test_trust_weights_change_weighted_uncertainty():
    series = {"A": {T0: 20.0}, "B": {T0: 24.0}, "C": {T0: 22.0}}
    [balanced] = points_for(series, {"A": 1, "B": 1, "C": 1})
    [dominant] = points_for(series, {"A": 0.9, "B": 0.05, "C": 0.05})
    assert balanced.model_spread == dominant.model_spread  # raw spread is weight-free
    assert dominant.weighted_std != pytest.approx(balanced.weighted_std)


def test_missing_model_is_excluded_not_zero():
    [p] = points_for({"A": {T0: 20.0}, "B": {T0: 22.0}, "C": {T0: None}}, {"A": 1, "B": 1, "C": 1})
    assert p.models_used == ["A", "B"]
    assert p.model_min == 20.0 and p.model_spread == 2.0


def test_single_model_is_limited_data_not_fake_disagreement():
    [p] = points_for({"A": {T0: 20.0}, "B": {T0: None}}, {"A": 1, "B": 1})
    assert p.status == "limited_data"
    assert p.disagreement_level == "LIMITED_DATA"
    assert p.model_spread == 0.0 and p.weighted_std == 0.0


def test_no_model_data_is_insufficient():
    [p] = points_for({"A": {T0: None}}, {"A": 1})
    assert p.status == "insufficient_data" and p.blended_value is None and p.model_spread is None


def test_identical_inputs_give_identical_output():
    series = {"A": {T0: 20.123}, "B": {T0: 23.456}}
    assert points_for(series, {"A": 0.6, "B": 0.4}) == points_for(series, {"A": 0.6, "B": 0.4})


def test_thresholds_come_from_historical_spread_percentiles():
    # Historical spreads 0..47 -> P33 ≈ 15.5, P67 ≈ 31.5
    series = {"A": {t: 0.0 for t in HOURS}, "B": {t: float(i) for i, t in enumerate(HOURS)}}
    th = spread_thresholds(series, ["A", "B"])
    assert th.samples == 48
    assert th.low_max == pytest.approx(15.51, abs=0.01) and th.medium_max == pytest.approx(31.49, abs=0.01)
    assert classify(1.0, 2, th) == "LOW"
    assert classify(20.0, 2, th) == "MEDIUM"
    assert classify(40.0, 2, th) == "HIGH"
    assert spread_thresholds({"A": {T0: 1.0}}, ["A"]) is None  # not enough data -> no invented cut-offs


def test_historical_range_uses_blend_error_percentiles():
    observations = {t: 25.0 for t in HOURS}
    errors = [((i % 10) - 4.5) / 10 for i in range(48)]  # symmetric errors between -0.45 and +0.45
    series = {"A": {t: 25.0 + e for t, e in zip(HOURS, errors)}}
    errs = historical_blend_errors(observations, series, {"A": 1.0})
    assert errs == pytest.approx(errors)
    hist = historical_error_summary(errs, HOURS, "test")
    [p] = compute_points(blend_forecasts({"A": {T0: 30.0}}, {"A": 1.0}), None, hist, non_negative=False)
    assert p.historical_lower == pytest.approx(30.0 - hist.error_p90)
    assert p.historical_upper == pytest.approx(30.0 - hist.error_p10)
    assert p.historical_lower < 30.0 < p.historical_upper


def test_precipitation_range_is_never_negative():
    hist = historical_error_summary([float(e) for e in range(-10, 38)], HOURS, "test")
    [p] = compute_points(blend_forecasts({"A": {T0: 0.1}}, {"A": 1.0}), None, hist, non_negative=True)
    assert p.historical_lower >= 0.0 and p.historical_upper >= 0.0


class FakeBlend:
    async def get_blend(self, location, variable, forecast_days, lead_day, days):
        series = {"A": {T0: 20.0}, "B": {T0: 24.0}}
        weights = {"A": 0.75, "B": 0.25}
        return BlendResponse(
            location=location, latitude=0, longitude=0, variable=variable, unit="°C",
            forecast_days=forecast_days, trust_lead_day=lead_day, status="ok", method="x", formula=[],
            models_used=[BlendModel(model=m, trust_weight=w, trust_weight_percent=w * 100, init_time=T0, points=1)
                         for m, w in weights.items()],
            excluded_models=[], forecast=blend_forecasts(series, weights),
        )


class FailingPerformance:
    async def verification_series(self, *args):
        raise RuntimeError("ERA5 down")


@pytest.mark.asyncio
async def test_service_falls_back_to_disagreement_only_when_history_fails():
    result = await UncertaintyService(FakeBlend(), FailingPerformance()).get_uncertainty("Mumbai", "temperature", 2, 1, 21)
    assert result.status == "ok"
    assert result.historical is None and result.thresholds is None
    assert result.explanation.startswith("Current uncertainty is estimated from disagreement")
    [p] = result.forecast
    assert p.model_spread == 4.0 and p.historical_lower is None
