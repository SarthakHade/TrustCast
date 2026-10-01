"""Tests for the Step 4 Trust Engine; pure calculations, no network."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.performance import ModelPerformance, PerformanceResponse
from app.services import trust_engine as trust
from app.services.trust_engine import compute_trust, percentages_summing_to_100


def model(name: str, rmse: float | None, status: str = "live", samples: int = 504, bias: float = 0.0):
    return ModelPerformance(
        model=name,
        model_type="Physics NWP",
        provider="test",
        status=status,
        samples=samples if rmse is not None else 0,
        mae=rmse,
        rmse=rmse,
        bias=bias if rmse is not None else None,
    )


def perf(models: list[ModelPerformance]) -> PerformanceResponse:
    return PerformanceResponse(
        location="Mumbai",
        latitude=19.076,
        longitude=72.8777,
        variable="temperature",
        unit="°C",
        lead_day=1,
        period_start=datetime(2026, 9, 4, tzinfo=UTC),
        period_end=datetime(2026, 9, 24, 23, tzinfo=UTC),
        data_mode="real_archived_forecasts",
        forecast_source="test",
        observation_source="test",
        skill_method="test",
        models=models,
    )


def weights(result):
    return {m.model: m for m in result.models if m.included}


def three_models():
    return perf([model("IFS", 1.1), model("GFS", 1.5), model("AIFS", 0.55)])


def test_lower_rmse_gets_higher_weight_and_weights_sum_to_one():
    result = compute_trust(three_models(), None)
    w = weights(result)
    assert result.status == "ok"
    assert w["AIFS"].weight > w["IFS"].weight > w["GFS"].weight
    assert sum(m.weight for m in w.values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(m.weight_percent for m in w.values()) == pytest.approx(100.0)
    assert "Highest trust" in w["AIFS"].reasons[0]


def test_weight_matches_inverse_rmse_formula():
    result = compute_trust(three_models(), None)
    inv = {name: 1 / (rmse + trust.EPSILON) for name, rmse in [("IFS", 1.1), ("GFS", 1.5), ("AIFS", 0.55)]}
    total = sum(inv.values())
    for name, m in weights(result).items():
        assert m.weight == pytest.approx(inv[name] / total, abs=1e-4)


def test_recent_performance_shifts_trust():
    historical = perf([model("IFS", 1.0), model("GFS", 1.0)])
    recent = perf([model("IFS", 0.5, samples=168), model("GFS", 2.0, samples=168)])
    w = weights(compute_trust(historical, recent))
    assert w["IFS"].weight > w["GFS"].weight
    assert any("Improving" in r for r in w["IFS"].reasons)
    assert any("Degrading" in r for r in w["GFS"].reasons)


def test_unavailable_model_gets_no_weight_and_is_not_in_denominator():
    data = perf([
        model("IFS", 1.0),
        model("GFS", 1.0),
        model("NCUM", None, status="data_unavailable"),
        model("GraphCast", None, status="adapter_ready"),
    ])
    result = compute_trust(data, None)
    by_name = {m.model: m for m in result.models}
    assert by_name["NCUM"].weight is None and not by_name["NCUM"].included
    assert by_name["GraphCast"].weight_percent is None
    assert by_name["IFS"].weight == pytest.approx(0.5)
    assert by_name["GFS"].weight_percent == 50.0


def test_same_input_gives_identical_output():
    assert compute_trust(three_models(), None) == compute_trust(three_models(), None)


def test_missing_performance_data_reports_insufficient_data():
    result = compute_trust(perf([model("NCUM", None, status="data_unavailable")]), None)
    assert result.status == "insufficient_data"
    assert result.message == "Insufficient historical data to calculate trust."
    assert all(m.weight is None for m in result.models)


def test_too_few_samples_excludes_model():
    result = compute_trust(perf([model("IFS", 1.0), model("GFS", 0.1, samples=5)]), None)
    by_name = {m.model: m for m in result.models}
    assert not by_name["GFS"].included
    assert result.status == "single_model"
    assert by_name["IFS"].weight_percent == 100.0


def test_zero_rmse_does_not_divide_by_zero():
    result = compute_trust(perf([model("IFS", 0.0), model("GFS", 1.0)]), None)
    w = weights(result)
    assert w["IFS"].weight > w["GFS"].weight
    assert sum(m.weight_percent for m in w.values()) == pytest.approx(100.0)


def test_percentages_always_sum_to_exactly_100():
    assert sum(percentages_summing_to_100([1 / 3, 1 / 3, 1 / 3])) == pytest.approx(100.0)
    assert sum(percentages_summing_to_100([0.4567, 0.3211, 0.2222])) == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_trust_endpoint_uses_performance_data(monkeypatch):
    async def fake_evaluate(location, variable, days, lead_day):
        return three_models()

    monkeypatch.setattr(trust.trust_engine.performance, "evaluate", fake_evaluate)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/trust")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert sum(m["weight_percent"] or 0 for m in data["models"]) == pytest.approx(100.0)
