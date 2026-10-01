"""Step 4 Trust Engine: turn Step 3 verification metrics into explainable model weights.

Deterministic by construction (no randomness, no per-model constants):

    historical_skill_i = 1 / (RMSE_i over the full window + ε)   ("historical inverse error")
    recent_skill_i     = 1 / (RMSE_i over the most recent days + ε) ("recent inverse error")
    trust_score_i      = 0.7 · historical_skill_i + 0.3 · recent_skill_i
    weight_i           = trust_score_i / Σ_j trust_score_j      (eligible models only)

The response field names keep `historical_skill` / `recent_skill` for API compatibility; they are
inverse-error quantities, not standardized meteorological skill scores.

If the recent-window evaluation is unavailable, trust_score_i = historical_skill_i.
Lead time is handled by scoring the archived forecasts at the requested lead day.
"""

from app.schemas.performance import ModelPerformance, PerformanceResponse
from app.schemas.trust import ModelTrust, TrustResponse
from app.services.performance_service import PerformanceService, performance_service

EPSILON = 0.05
HISTORICAL_WEIGHT = 0.7
RECENT_WEIGHT = 0.3
RECENT_DAYS = 7
MIN_SAMPLES = 24
METHOD = "Performance-based normalized trust scoring (inverse RMSE, historical + recent)"
FORMULA = [
    f"historical_inverse_error = 1 / (RMSE_historical + {EPSILON})",
    f"recent_inverse_error = 1 / (RMSE_last_{RECENT_DAYS}_days + {EPSILON})",
    f"trust_score = {HISTORICAL_WEIGHT} × historical_inverse_error + {RECENT_WEIGHT} × recent_inverse_error",
    "weight = trust_score / Σ trust_score (available models only)",
]


def percentages_summing_to_100(weights: list[float]) -> list[float]:
    """Round to 0.1% with the largest-remainder method so the display sums to exactly 100."""
    tenths = [w * 1000 for w in weights]
    floors = [int(t) for t in tenths]
    remaining = 1000 - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (tenths[i] - floors[i], -i), reverse=True)
    for i in order[:remaining]:
        floors[i] += 1
    return [f / 10 for f in floors]


def _explain(row: ModelTrust, eligible: list[ModelTrust], unit: str) -> list[str]:
    """Build reasons purely from the metrics; no model names are special-cased."""
    ranked = sorted(eligible, key=lambda r: r.weight or 0, reverse=True)
    best = ranked[0]
    reasons: list[str] = []
    if len(eligible) == 1:
        reasons.append("Only one model has sufficient evaluation data")
    elif row is best:
        reasons.append(f"Highest trust: lowest combined historical + recent error (RMSE {row.historical_rmse:.2f} {unit})")
    elif row.historical_rmse <= best.historical_rmse:
        reasons.append(
            f"Historical RMSE {row.historical_rmse:.2f} {unit} is as good as {best.model} "
            f"({best.historical_rmse:.2f}), but its recent error is higher"
        )
    else:
        extra = (row.historical_rmse / best.historical_rmse - 1) * 100 if best.historical_rmse else 0
        label = "Moderate" if row is not ranked[-1] else "Lower"
        reasons.append(
            f"{label} historical performance: RMSE {row.historical_rmse:.2f} {unit}, "
            f"{extra:.0f}% higher than {best.model}"
        )
    if row.recent_rmse is not None and row.historical_rmse:
        change = row.recent_rmse / row.historical_rmse - 1
        if change <= -0.1:
            reasons.append(f"Improving: last-{RECENT_DAYS}-day RMSE is {abs(change) * 100:.0f}% below its full-period average")
        elif change >= 0.1:
            reasons.append(f"Degrading: last-{RECENT_DAYS}-day RMSE is {change * 100:.0f}% above its full-period average")
        else:
            reasons.append("Stable: recent error is in line with its full-period average")
    if row.bias is not None and row.historical_rmse and abs(row.bias) >= 0.5 * row.historical_rmse:
        direction = "high" if row.bias > 0 else "low"
        reasons.append(f"Systematic bias: tends to forecast {direction} by {abs(row.bias):.2f} {unit}")
    return reasons


def compute_trust(
    historical: PerformanceResponse, recent: PerformanceResponse | None
) -> TrustResponse:
    recent_by_model = {m.model: m for m in recent.models} if recent else {}
    rows: list[ModelTrust] = []
    for perf in historical.models:
        rows.append(_score_model(perf, recent_by_model.get(perf.model)))

    eligible = [r for r in rows if r.included]
    status, message = "ok", None
    if not eligible:
        status, message = "insufficient_data", "Insufficient historical data to calculate trust."
    else:
        total = sum(r.trust_score or 0 for r in eligible)
        for r in eligible:
            r.weight = round((r.trust_score or 0) / total, 6)
        for r, pct in zip(eligible, percentages_summing_to_100([r.weight or 0 for r in eligible])):
            r.weight_percent = pct
        for r in eligible:
            r.reasons = _explain(r, eligible, historical.unit)
        if len(eligible) == 1:
            status, message = "single_model", "Only one model has sufficient evaluation data."

    return TrustResponse(
        location=historical.location,
        variable=historical.variable,
        unit=historical.unit,
        lead_day=historical.lead_day,
        status=status,
        message=message,
        historical_period_start=historical.period_start,
        historical_period_end=historical.period_end,
        historical_days=_days(historical),
        recent_days=_days(recent) if recent else None,
        method=METHOD,
        formula=FORMULA if recent else [FORMULA[0], "trust_score = historical_inverse_error", FORMULA[3]],
        models=rows,
    )


def _score_model(perf: ModelPerformance, recent: ModelPerformance | None) -> ModelTrust:
    row = ModelTrust(
        model=perf.model,
        model_type=perf.model_type,
        status=perf.status,
        included=False,
        historical_rmse=perf.rmse,
        bias=perf.bias,
        samples=perf.samples,
    )
    if perf.rmse is None or perf.samples < MIN_SAMPLES:
        if perf.status == "error":
            row.reasons = ["Excluded: archived data source temporarily unavailable; retried on next request"]
        elif perf.status == "live" and perf.samples == 0:
            row.reasons = ["Forecast available · reliability not yet calibrated (no archived forecasts to verify); not weighted"]
        elif perf.status == "live":
            row.reasons = [f"Excluded: fewer than {MIN_SAMPLES} verified samples"]
        else:
            row.reasons = ["Excluded: no forecast/verification data connected"]
        return row

    row.included = True
    row.historical_skill = round(1 / (perf.rmse + EPSILON), 4)
    if recent is not None and recent.rmse is not None and recent.samples >= MIN_SAMPLES:
        row.recent_rmse = recent.rmse
        row.recent_skill = round(1 / (recent.rmse + EPSILON), 4)
        row.trust_score = round(
            HISTORICAL_WEIGHT * row.historical_skill + RECENT_WEIGHT * row.recent_skill, 4
        )
    else:
        row.trust_score = row.historical_skill
    return row


def _days(perf: PerformanceResponse) -> int:
    if not perf.period_start or not perf.period_end:
        return 0
    return round((perf.period_end - perf.period_start).total_seconds() / 86400)


class TrustEngine:
    def __init__(self, performance: PerformanceService = performance_service) -> None:
        self.performance = performance

    async def get_trust(
        self, location: str, variable: str, days: int, lead_day: int
    ) -> TrustResponse:
        historical = await self.performance.evaluate(location, variable, days, lead_day)
        recent = None
        if days > RECENT_DAYS:
            try:
                recent = await self.performance.evaluate(location, variable, RECENT_DAYS, lead_day)
            except Exception:
                recent = None  # fall back to historical-only trust; never invent recent data
        return compute_trust(historical, recent)


trust_engine = TrustEngine()
