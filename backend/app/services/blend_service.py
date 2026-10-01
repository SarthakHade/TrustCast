"""Step 5: trust-weighted multi-model forecast blending.

For every valid_time t:
    available(t)   = models with a live forecast value at t AND a Step 4 trust weight
    w_eff_i(t)     = w_i / Σ_{j ∈ available(t)} w_j
    blend(t)       = Σ_{i ∈ available(t)} w_eff_i(t) · forecast_i(t)
Missing values are never treated as zero; if no model is available, the point is
reported as insufficient_data instead of a number.
"""

import math
from datetime import datetime

from app.data.locations import DEMO_LOCATIONS
from app.schemas.blend import BlendModel, BlendPoint, BlendResponse, ExcludedModel
from app.services.trust_engine import TrustEngine, trust_engine
from app.services.weather.weather_service import WeatherService, weather_service

METHOD = "Trust-weighted multi-model blending"
FORMULA = [
    "blend(t) = Σ w_eff_i(t) × forecast_i(t)",
    "w_eff_i(t) = trust_weight_i / Σ trust_weight_j over models with a value at t",
    "Missing values are excluded (never treated as 0) and the remaining weights are renormalized",
]
# TrustCast variable -> field on the Step 2 ForecastRecord
FORECAST_FIELDS = {"temperature": "temperature", "precipitation": "precipitation", "wind_speed": "wind_speed"}

Series = dict[datetime, float | None]


def blend_forecasts(series: dict[str, Series], weights: dict[str, float]) -> list[BlendPoint]:
    """Align forecasts by valid_time and compute the renormalized weighted sum per timestamp."""
    usable = {m: w for m, w in weights.items() if m in series and w is not None and w > 0}
    times = sorted({t for m in usable for t in series[m]})
    points: list[BlendPoint] = []
    for t in times:
        contributors = {
            m: float(series[m][t])
            for m in usable
            if series[m].get(t) is not None and math.isfinite(series[m][t])
        }
        total = sum(usable[m] for m in contributors)
        if not contributors or total <= 0:
            points.append(
                BlendPoint(
                    valid_time=t, status="insufficient_data", blended_value=None,
                    contributors={}, effective_weights={}, renormalized=False,
                )
            )
            continue
        effective = {m: usable[m] / total for m in contributors}
        points.append(
            BlendPoint(
                valid_time=t,
                status="ok",
                blended_value=sum(effective[m] * contributors[m] for m in contributors),
                contributors=contributors,
                effective_weights=effective,
                renormalized=len(contributors) < len(usable),
            )
        )
    return points


class BlendService:
    def __init__(
        self, weather: WeatherService = weather_service, trust: TrustEngine = trust_engine
    ) -> None:
        self.weather = weather
        self.trust = trust

    async def get_blend(
        self, location_name: str, variable: str, forecast_days: int, lead_day: int, days: int
    ) -> BlendResponse:
        location = next(
            (loc for loc in DEMO_LOCATIONS if loc["name"].casefold() == location_name.casefold()),
            None,
        )
        if location is None:
            names = ", ".join(loc["name"] for loc in DEMO_LOCATIONS)
            raise KeyError(f"Unknown location '{location_name}'. Use one of: {names}")
        if variable not in FORECAST_FIELDS:
            raise KeyError(f"Unknown variable '{variable}'. Use one of: {', '.join(FORECAST_FIELDS)}")

        # Step 4 weights first (raises on unknown input or source failure), then Step 2 forecasts.
        trust = await self.trust.get_trust(location["name"], variable, days, lead_day)
        forecasts = await self.weather.get_all_models(
            location["latitude"], location["longitude"], forecast_days
        )

        field = FORECAST_FIELDS[variable]
        trust_by_model = {m.model: m for m in trust.models}
        series: dict[str, Series] = {}
        used: list[BlendModel] = []
        excluded: list[ExcludedModel] = []
        for result in forecasts.results:
            if result.status == "inactive":
                continue  # optional models that are not running never count as contributors
            t = trust_by_model.get(result.model)
            # Only real, validated live forecasts with a Trust Engine weight contribute.
            has_forecast = result.status == "live" and result.forecast
            has_weight = t is not None and t.included and t.weight
            values = {r.valid_time: getattr(r, field) for r in result.forecast} if has_forecast else {}
            if has_forecast and not any(v is not None for v in values.values()):
                # Variable-specific availability: a live model without this variable is excluded for it.
                excluded.append(ExcludedModel(
                    model=result.model, status=result.status,
                    reason=f"No valid {variable.replace('_', ' ')} values from this model",
                ))
            elif has_forecast and has_weight:
                series[result.model] = values
                used.append(
                    BlendModel(
                        model=result.model,
                        trust_weight=t.weight,
                        trust_weight_percent=t.weight_percent,
                        init_time=result.init_time,
                        points=sum(v is not None for v in series[result.model].values()),
                    )
                )
            elif not has_forecast:
                excluded.append(ExcludedModel(
                    model=result.model, status=result.status,
                    reason=result.error or "No live forecast available",
                ))
            else:
                excluded.append(ExcludedModel(
                    model=result.model, status=result.status,
                    reason=(t.reasons[0] if t and t.reasons else "No Trust Engine weight available"),
                ))

        points = blend_forecasts(series, {m.model: m.trust_weight for m in used})
        ok = any(p.status == "ok" for p in points)
        return BlendResponse(
            location=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            variable=variable,
            unit=trust.unit,
            forecast_days=forecast_days,
            trust_lead_day=lead_day,
            status="ok" if ok else "insufficient_data",
            message=None if ok else "Blended forecast unavailable because insufficient model data is available.",
            method=METHOD,
            formula=FORMULA,
            models_used=used,
            excluded_models=excluded,
            forecast=points,
        )


blend_service = BlendService()
