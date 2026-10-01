"""Step 6 Uncertainty Engine: model disagreement + TrustCast's own historical error.

Two separate, real components (never random, never a probability of correctness):

A) Model disagreement at each valid_time t (Step 2 forecasts, Step 5 effective weights):
       model_spread(t) = max_i f_i(t) − min_i f_i(t)
       weighted_std(t) = sqrt( Σ w_eff_i(t) · (f_i(t) − blend(t))² )
   Level LOW / MEDIUM / HIGH compares model_spread(t) with the 33rd / 67th percentiles of the
   hourly spreads the same models had over the Step 3 window (archived forecasts, same lead day).

B) Historical error range: the current Step 4 weights are applied to the Step 3 archived
   forecasts (same lead day) with the Step 5 blending function, and compared with ERA5:
       error = blend_hist − observed
   The 10th/90th percentiles of that error give an empirical 80% range:
       historical_lower(t) = blend(t) − error_p90
       historical_upper(t) = blend(t) − error_p10
   This covered ~80% of the past-window hours by construction (in-sample; the weights were
   derived from the same window). It is not a guaranteed future probability.
"""

import math
import statistics
from datetime import datetime

from app.schemas.blend import BlendPoint
from app.schemas.uncertainty import (
    DisagreementThresholds,
    HistoricalError,
    UncertaintyPoint,
    UncertaintyResponse,
)
from app.services.blend_service import FORECAST_FIELDS, BlendService, blend_forecasts, blend_service
from app.services.performance_service import PerformanceService, performance_service

MIN_HISTORY = 24
COVERAGE = 0.8
NON_NEGATIVE = {"precipitation", "wind_speed"}
FORMULA = [
    "model_spread(t) = max_i f_i(t) − min_i f_i(t)",
    "weighted_std(t) = √ Σ w_eff_i(t) · (f_i(t) − blend(t))²",
    "level: LOW ≤ P33 < MEDIUM ≤ P67 < HIGH of historical hourly model spreads",
    "historical range(t) = [blend(t) − P90(error), blend(t) − P10(error)], error = past blend − ERA5",
]

Series = dict[datetime, float | None]


def disagreement_stats(
    contributors: dict[str, float], weights: dict[str, float], blended: float
) -> dict[str, float]:
    """Spread statistics for one timestamp; `weights` must be the effective (summing to 1) ones."""
    values = list(contributors.values())
    variance = sum(weights[m] * (v - blended) ** 2 for m, v in contributors.items())
    return {
        "model_min": min(values),
        "model_max": max(values),
        "model_mean": statistics.fmean(values),
        "model_spread": max(values) - min(values),
        "weighted_std": math.sqrt(variance),
    }


def spread_thresholds(series: dict[str, Series], models: list[str]) -> DisagreementThresholds | None:
    """P33 / P67 of historical hourly spreads, using hours where at least two models have data."""
    times = sorted({t for m in models if m in series for t in series[m]})
    spreads = []
    for t in times:
        values = [series[m][t] for m in models if m in series and series[m].get(t) is not None]
        if len(values) >= 2:
            spreads.append(max(values) - min(values))
    if len(spreads) < MIN_HISTORY:
        return None
    cuts = statistics.quantiles(spreads, n=100, method="inclusive")
    return DisagreementThresholds(
        low_max=cuts[32],
        medium_max=cuts[66],
        samples=len(spreads),
        source="33rd/67th percentiles of hourly model spread over the Step 3 verification window",
    )


def classify(spread: float, model_count: int, thresholds: DisagreementThresholds | None) -> str | None:
    if model_count < 2:
        return "LIMITED_DATA"
    if thresholds is None:
        return None
    if spread <= thresholds.low_max:
        return "LOW"
    if spread <= thresholds.medium_max:
        return "MEDIUM"
    return "HIGH"


def historical_blend_errors(
    observations: dict[datetime, float], series: dict[str, Series], weights: dict[str, float]
) -> list[float]:
    """Errors (blend − observed) of the current weights applied to archived forecasts."""
    return [
        p.blended_value - observations[p.valid_time]
        for p in blend_forecasts(series, weights)
        if p.status == "ok" and p.valid_time in observations
    ]


def historical_error_summary(
    errors: list[float], period: list[datetime], note: str
) -> HistoricalError | None:
    if len(errors) < MIN_HISTORY or not period:
        return None
    cuts = statistics.quantiles(errors, n=100, method="inclusive")
    return HistoricalError(
        samples=len(errors),
        rmse=math.sqrt(statistics.fmean(e * e for e in errors)),
        mae=statistics.fmean(abs(e) for e in errors),
        bias=statistics.fmean(errors),
        error_p10=cuts[9],
        error_p90=cuts[89],
        coverage=COVERAGE,
        period_start=min(period),
        period_end=max(period),
        note=note,
    )


def compute_points(
    points: list[BlendPoint],
    thresholds: DisagreementThresholds | None,
    historical: HistoricalError | None,
    non_negative: bool,
) -> list[UncertaintyPoint]:
    result = []
    for p in points:
        if p.status != "ok" or p.blended_value is None:
            result.append(UncertaintyPoint(
                valid_time=p.valid_time, status="insufficient_data", blended_value=None, models_used=[],
            ))
            continue
        stats = disagreement_stats(p.contributors, p.effective_weights, p.blended_value)
        count = len(p.contributors)
        lower = upper = None
        if historical is not None:
            lower = p.blended_value - historical.error_p90
            upper = p.blended_value - historical.error_p10
            if non_negative:
                lower, upper = max(lower, 0.0), max(upper, 0.0)
        result.append(UncertaintyPoint(
            valid_time=p.valid_time,
            status="ok" if count >= 2 else "limited_data",
            blended_value=p.blended_value,
            models_used=sorted(p.contributors),
            disagreement_level=classify(stats["model_spread"], count, thresholds),
            historical_lower=lower,
            historical_upper=upper,
            **stats,
        ))
    return result


class UncertaintyService:
    def __init__(
        self, blend: BlendService = blend_service, performance: PerformanceService = performance_service
    ) -> None:
        self.blend = blend
        self.performance = performance

    async def get_uncertainty(
        self, location: str, variable: str, forecast_days: int, lead_day: int, days: int
    ) -> UncertaintyResponse:
        blend = await self.blend.get_blend(location, variable, forecast_days, lead_day, days)
        weights = {m.model: m.trust_weight for m in blend.models_used}
        models = list(weights)

        thresholds = historical = None
        history_note = None
        try:
            observations, series = await self.performance.verification_series(
                blend.location, variable, days, lead_day
            )
            thresholds = spread_thresholds(series, models)
            errors = historical_blend_errors(observations, series, weights)
            historical = historical_error_summary(
                errors,
                sorted(observations),
                f"Current trust weights applied to Day-{lead_day} archived forecasts vs ERA5. "
                f"The range covered {int(COVERAGE * 100)}% of those past hours (in-sample); "
                "it is an empirical error range, not a calibrated probability.",
            )
        except Exception as exc:  # disagreement remains available without history
            history_note = f"Historical error unavailable: {exc}"

        points = compute_points(blend.forecast, thresholds, historical, variable in NON_NEGATIVE)
        ensemble_sources = await self._attach_ensemble_spread(blend, variable, forecast_days, points)
        usable = [p for p in points if p.status != "insufficient_data"]
        if not usable:
            status = "insufficient_data"
            message = "Uncertainty cannot be calculated because no valid model forecasts are available."
        elif all(p.status == "limited_data" for p in usable):
            status = "limited_data"
            message = "Only one model is currently available; model disagreement cannot be estimated."
        else:
            status, message = "ok", None
        if history_note:
            message = f"{message} {history_note}" if message else history_note

        explanation = (
            "TrustCast uncertainty reflects disagreement among the contributing forecast models "
            "and their historical error characteristics."
            if historical is not None
            else "Current uncertainty is estimated from disagreement among the contributing forecast models."
        )
        return UncertaintyResponse(
            location=blend.location,
            variable=variable,
            unit=blend.unit,
            forecast_days=forecast_days,
            lead_day=lead_day,
            status=status,
            message=message,
            explanation=explanation,
            formula=FORMULA,
            thresholds=thresholds,
            historical=historical,
            models_used=models,
            excluded_models=blend.excluded_models,
            forecast=points,
            ensemble_sources=ensemble_sources,
        )

    async def _attach_ensemble_spread(self, blend, variable: str, forecast_days: int, points: list[UncertaintyPoint]) -> dict[str, int]:
        """Add real ensemble member spread (e.g. NOAA AIGEFS) at the valid times where it exists."""
        field = f"{FORECAST_FIELDS[variable]}_spread"
        try:
            forecasts = await self.blend.weather.get_all_models(blend.latitude, blend.longitude, forecast_days)
        except Exception:
            return {}
        by_time = {p.valid_time: p for p in points}
        sources: dict[str, int] = {}
        for result in forecasts.results:
            if result.status != "live":
                continue
            for record in result.forecast:
                spread = getattr(record, field, None)
                if spread is None or record.ensemble_members is None:
                    continue
                sources[result.model] = max(sources.get(result.model, 0), record.ensemble_members)
                point = by_time.get(record.valid_time)
                if point is not None:
                    point.ensemble_spread[result.model] = spread
        return sources


uncertainty_service = UncertaintyService()
