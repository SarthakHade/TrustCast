"""Step 5: trust-weighted multi-model forecast blending.

For every valid_time t:
    available(t)   = models with a live forecast value at t AND a Step 4 trust weight
    w_eff_i(t)     = w_i / Σ_{j ∈ available(t)} w_j
    blend(t)       = Σ_{i ∈ available(t)} w_eff_i(t) · forecast_i(t)
Missing values are never treated as zero; if no model is available, the point is
reported as insufficient_data instead of a number.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.services.location_service import LocationInput, resolve_location
from app.schemas.blend import BlendModel, BlendPoint, BlendResponse, ExcludedModel
from app.services.trust_engine import TrustEngine, trust_engine
from app.services.weather.weather_service import WeatherService, weather_service

if TYPE_CHECKING:
    from app.services.skill.service import SkillService

ADAPTIVE_METHOD = "Bias-corrected adaptive stacking (walk-forward selected), trust-weighted fallback"
ADAPTIVE_FORMULA = [
    "corrected_i(t) = forecast_i(t) − bias_i(hour)   (temperature, wind; rain: ratio_i × forecast_i)",
    "blend(t) = Σ w_i · corrected_i(t) / Σ w_i over models with a value at t",
    "w ≥ 0, Σw = 1, trained only on data available before the forecast was issued",
]
CLIP_ZERO = {"precipitation", "wind_speed"}

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


def lead_day_for(valid_time: datetime, issued: datetime) -> int:
    """Archive lead day whose verification applies to this valid time (Day 1 < 48 h, else Day 2)."""
    return 1 if valid_time - issued < timedelta(hours=48) else 2


def adaptive_blend(
    series: dict[str, Series], live: dict[str, Any], regimes: dict, variable: str,
    fallback_weights: dict[str, float], issued: datetime,
) -> list[BlendPoint]:
    """Apply the walk-forward-trained bias corrections and weights per valid time."""
    clip = variable in CLIP_ZERO
    times = sorted({t for m in series for t in series[m]})
    points: list[BlendPoint] = []
    for t in times:
        lead = lead_day_for(t, issued)
        regime = regimes.get(t.astimezone(UTC).date(), "UNKNOWN")
        block = live["leads"][lead]
        fit = block["fits"].get(regime) or block["fits"].get("NORMAL")
        contributors = {
            m: float(series[m][t]) for m in series
            if series[m].get(t) is not None and math.isfinite(series[m][t])
        }
        if not contributors:
            points.append(BlendPoint(valid_time=t, status="insufficient_data", blended_value=None,
                                     contributors={}, effective_weights={}, renormalized=False))
            continue
        if fit is None:
            [point] = blend_forecasts({m: {t: v} for m, v in contributors.items()}, fallback_weights)
            points.append(point)
            continue
        models = block["models"]
        corrected = {}
        for m, v in contributors.items():
            if m in models:
                corrected[m] = fit["bias"].apply(models.index(m), t.hour, v, clip)
        usable = {m: fit["weights"][m] for m in corrected if fit["weights"].get(m, 0) > 0}
        total = sum(usable.values())
        if total <= 0:
            points.append(BlendPoint(valid_time=t, status="insufficient_data", blended_value=None,
                                     contributors=contributors, effective_weights={}, renormalized=False))
            continue
        effective = {m: w / total for m, w in usable.items()}
        points.append(BlendPoint(
            valid_time=t, status="ok",
            blended_value=sum(effective[m] * corrected[m] for m in effective),
            contributors=contributors, corrected=corrected, effective_weights=effective,
            renormalized=len(effective) < sum(1 for w in fit["weights"].values() if w > 0),
            lead_day=lead, regime=regime,
        ))
    return points


def describe_live(live: dict[str, Any], regimes: dict) -> dict[str, Any]:
    """JSON-safe summary of the adaptive configuration (no internal objects)."""
    leads = {}
    for lead, block in (live.get("leads") or {}).items():
        leads[str(lead)] = {
            "oos": block.get("oos"),
            "fits": {
                regime: {
                    "variant": f["variant"], "level": f["level"], "note": f.get("note") or None,
                    "weights": f["weights"], "samples": f["samples"], "training_end": f["training_end"],
                    "bias_correction": {"kind": f["bias"].kind, "mode": f["bias"].mode, "per_model": f["bias"].summary(block["models"])},
                }
                for regime, f in block.get("fits", {}).items()
            },
        }
    return {
        "status": live.get("status"), "message": live.get("message"), "issued": live.get("issued"),
        "regimes": {d.isoformat(): r for d, r in sorted(regimes.items())}, "leads": leads,
        "data": live.get("data"),
    }


class BlendService:
    def __init__(
        self, weather: WeatherService = weather_service, trust: TrustEngine = trust_engine,
        skill: "SkillService | None" = None,
    ) -> None:
        self.weather = weather
        self.trust = trust
        self.skill = skill

    async def get_blend(
        self, location_input: LocationInput, variable: str, forecast_days: int, lead_day: int, days: int
    ) -> BlendResponse:
        location = resolve_location(location_input)  # the selected coordinates, never a substitute city
        if variable not in FORECAST_FIELDS:
            raise KeyError(f"Unknown variable '{variable}'. Use one of: {', '.join(FORECAST_FIELDS)}")

        # Step 4 weights first (raises on unknown input or source failure), then Step 2 forecasts.
        trust = await self.trust.get_trust(location, variable, days, lead_day)
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

        trust_weights = {m.model: m.trust_weight for m in used}
        points = blend_forecasts(series, trust_weights)
        method, formula, adaptive = METHOD, FORMULA, None
        if self.skill is not None and series:
            try:
                regimes = await self.skill.forecast_regimes(location["latitude"], location["longitude"], forecast_days)
                live = await self.skill.live(location, variable, regimes)
            except Exception as exc:  # the trust-weighted blend stays available
                live, regimes = {"status": "unavailable", "message": f"Adaptive model unavailable: {exc}"}, {}
            adaptive = describe_live(live, regimes)
            if live.get("status") == "adaptive":
                points = adaptive_blend(series, live, regimes, variable, trust_weights, datetime.now(UTC))
                method, formula = ADAPTIVE_METHOD, ADAPTIVE_FORMULA
                day1 = [p for p in points if p.status == "ok" and p.lead_day == 1]
                first = max(day1, key=lambda p: len(p.effective_weights), default=None)
                if first is not None:
                    for m in used:  # report the weights actually applied to the first forecast day
                        m.trust_weight = first.effective_weights.get(m.model, 0.0)
                        m.trust_weight_percent = round(m.trust_weight * 100, 1)
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
            method=method,
            formula=formula,
            models_used=used,
            excluded_models=excluded,
            forecast=points,
            adaptive=adaptive,
        )


def _default_blend_service() -> BlendService:
    from app.services.skill.service import skill_service

    return BlendService(skill=skill_service)


blend_service = _default_blend_service()
