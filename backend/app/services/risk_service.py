"""Step 7: forecast-based risk indicators on top of the Step 5 blend and Step 6 uncertainty.

Deterministic threshold rules (thresholds live only in app/data/risk_thresholds.py):

  value(t)       = TrustCast blended forecast (Step 5); for heavy rain, the sum of blended
                   hourly precipitation over the trailing 24 h (future hours only)
  level(t)       = HIGH if value crosses `high`, ELEVATED if it crosses `elevated`, else NORMAL
                   ("crosses" = ≥ for above-rules, ≤ for below-rules)
  range(t)       = Step 6 historical error range (hourly rules); for 24 h rain totals, the
                   min–max of each model's own 24 h total (model disagreement range)
  position       = CLEARLY_BELOW if upper < threshold, CLEARLY_ABOVE if lower ≥ threshold,
                   otherwise THRESHOLD_CROSSED
  consensus      = number of contributing models whose own value crosses the threshold

The summary for each risk describes the worst hour of the horizon (max value, or min for cold).
No probabilities, no scores, no invented values: missing variables → data_unavailable.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.data.risk_thresholds import RISK_RULES, RiskRule
from app.schemas.risk import RiskIndicator, RiskResponse, RiskTimelinePoint, ThresholdCheck
from app.services.blend_service import BlendService, blend_service
from app.services.uncertainty_service import UncertaintyService, uncertainty_service

SOURCE_LABEL = "Based on current TrustCast forecast"
DISCLAIMER = "Forecast-based risk indicator using demo thresholds — not an official warning."
WINDOW_HOURS = 24


@dataclass
class Sample:
    """One value the rules are applied to (an hour, or a 24 h window ending at `valid_time`)."""

    valid_time: datetime
    value: float
    lower: float
    upper: float
    range_source: str
    model_values: dict[str, float] = field(default_factory=dict)
    window_start: datetime | None = None
    hours: int = 1


def crosses(value: float, threshold: float, direction: str) -> bool:
    return value >= threshold if direction == "above" else value <= threshold


def risk_level(value: float, rule: RiskRule) -> str:
    if crosses(value, rule.high, rule.direction):
        return "HIGH"
    if crosses(value, rule.elevated, rule.direction):
        return "ELEVATED"
    return "NORMAL"


def check_threshold_with_uncertainty(
    forecast: float, lower: float | None, upper: float | None, threshold: float
) -> str:
    """Where the forecast range sits relative to a threshold (range collapses to the forecast if absent)."""
    lo = forecast if lower is None else min(lower, forecast)
    hi = forecast if upper is None else max(upper, forecast)
    if hi < threshold:
        return "CLEARLY_BELOW"
    if lo >= threshold:
        return "CLEARLY_ABOVE"
    return "THRESHOLD_CROSSED"


def hourly_samples(blend_points: list, uncertainty_points: list) -> list[Sample]:
    """Join Step 5 contributors with the Step 6 range for each valid time."""
    ranges = {u.valid_time: u for u in uncertainty_points}
    samples = []
    for p in blend_points:
        u = ranges.get(p.valid_time)
        if p.status != "ok" or p.blended_value is None or u is None:
            continue
        if u.historical_lower is not None and u.historical_upper is not None:
            lower, upper, source = u.historical_lower, u.historical_upper, "Step 6 historical error range"
        else:
            lower, upper, source = u.model_min, u.model_max, "Step 6 model disagreement range"
        samples.append(Sample(p.valid_time, p.blended_value, lower, upper, source, dict(p.contributors)))
    return samples


def accumulate_24h(hourly: list[Sample]) -> list[Sample]:
    """Trailing sums over up to 24 consecutive samples; range = min–max of per-model totals."""
    result = []
    for i, end in enumerate(hourly):
        window = [s for s in hourly[: i + 1] if s.valid_time > end.valid_time - timedelta(hours=WINDOW_HOURS)]
        total = sum(s.value for s in window)
        models = set.intersection(*(set(s.model_values) for s in window)) if window else set()
        model_totals = {m: sum(s.model_values[m] for s in window) for m in sorted(models)}
        values = list(model_totals.values()) or [total]
        result.append(Sample(
            valid_time=end.valid_time,
            value=total,
            lower=min(values),
            upper=max(values),
            range_source="model disagreement range of 24 h totals",
            model_values=model_totals,
            window_start=window[0].valid_time - timedelta(hours=1),
            hours=len(window),
        ))
    return result


def assess(rule: RiskRule, samples: list[Sample]) -> RiskIndicator:
    base = dict(
        risk_type=rule.risk_type, title=rule.title, variable=rule.variable, unit=rule.unit,
        direction=rule.direction, thresholds={"ELEVATED": rule.elevated, "HIGH": rule.high},
        aggregation=rule.aggregation, basis=rule.basis,
    )
    if not samples:
        return RiskIndicator(**base, status="data_unavailable", reason="No forecast values for this variable.")

    pick = max if rule.direction == "above" else min
    # Worst value; on ties prefer the longer accumulation window, then the earliest hour.
    peak = pick(samples, key=lambda s: (s.value, s.hours if rule.direction == "above" else -s.hours))
    level = risk_level(peak.value, rule)

    checks = []
    for name, threshold in (("ELEVATED", rule.elevated), ("HIGH", rule.high)):
        # Position is value-relative (below / crossed / above), so it is the same for both directions.
        position = check_threshold_with_uncertainty(peak.value, peak.lower, peak.upper, threshold)
        checks.append(ThresholdCheck(
            level=name, threshold=threshold, position=position,
            models_exceeding=sum(crosses(v, threshold, rule.direction) for v in peak.model_values.values()),
            models_total=len(peak.model_values),
        ))
    # Key threshold = the one defining the forecast level (ELEVATED for NORMAL/ELEVATED, HIGH for HIGH).
    # Escalation risk (range crossing HIGH while ELEVATED) still shows via `threshold_crossing` / `checks`.
    key = checks[1] if level == "HIGH" else checks[0]
    crossing = any(c.position == "THRESHOLD_CROSSED" for c in checks)

    verb = "exceeds" if rule.direction == "above" else "falls below"
    messages = []
    if level != "NORMAL":
        limit = rule.high if level == "HIGH" else rule.elevated
        messages.append(f"TrustCast forecast {verb} the configured {level.lower()} threshold ({limit:g} {rule.unit}).")
    elif key.position == "THRESHOLD_CROSSED":
        messages.append(f"Forecast uncertainty overlaps the {rule.elevated:g} {rule.unit} threshold; risk cannot be ruled out.")
    else:
        side = "below" if rule.direction == "above" else "above"
        messages.append(f"No threshold exceeded; the TrustCast forecast range stays {side} {rule.elevated:g} {rule.unit}.")
    if level != "NORMAL" and crossing:
        messages.append("Threshold crossed within forecast uncertainty.")
    if key.models_total:
        messages.append(f"{key.models_exceeding} of {key.models_total} contributing models {verb.replace('falls', 'fall').replace('exceeds', 'exceed')} {key.threshold:g} {rule.unit}.")

    return RiskIndicator(
        **base,
        status="ok",
        level=level,
        peak_time=peak.valid_time,
        window_start=peak.window_start,
        accumulation_hours=peak.hours if rule.aggregation == "sum_24h" else None,
        forecast_value=peak.value,
        lower=peak.lower,
        upper=peak.upper,
        range_source=peak.range_source,
        key_threshold=key.threshold,
        range_position=key.position,
        threshold_crossing=crossing,
        models_exceeding=key.models_exceeding,
        models_total=key.models_total,
        model_consensus=f"{key.models_exceeding}/{key.models_total}" if key.models_total else None,
        checks=checks,
        messages=messages,
        timeline=[RiskTimelinePoint(valid_time=s.valid_time, level=risk_level(s.value, rule), value=s.value) for s in samples],
    )


class RiskService:
    def __init__(
        self, blend: BlendService = blend_service, uncertainty: UncertaintyService = uncertainty_service
    ) -> None:
        self.blend = blend
        self.uncertainty = uncertainty

    async def get_risks(
        self, location: dict | str, forecast_days: int, lead_day: int, days: int, now: datetime | None = None
    ) -> RiskResponse:
        current_hour = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
        samples_by_variable: dict[str, list[Sample] | str] = {}
        resolved_location = location["name"] if isinstance(location, dict) and location.get("name") else str(location)
        coords: tuple[float | None, float | None] = (None, None)
        # Sequential on purpose: each variable's history is fetched once and cached (gentle on the free API).
        for variable in dict.fromkeys(rule.variable for rule in RISK_RULES):
            try:
                blend = await self.blend.get_blend(location, variable, forecast_days, lead_day, days)
                resolved_location = blend.location
                coords = (blend.latitude, blend.longitude)
                unc = await self.uncertainty.get_uncertainty(location, variable, forecast_days, lead_day, days)
            except KeyError:
                raise
            except Exception as exc:  # isolate one variable's failure from the others
                samples_by_variable[variable] = f"{variable} forecast unavailable: {exc}"
                continue
            samples = [s for s in hourly_samples(blend.forecast, unc.forecast) if s.valid_time >= current_hour]
            samples_by_variable[variable] = samples or f"No valid {variable} forecast values in the horizon."

        risks = []
        for rule in RISK_RULES:
            data = samples_by_variable[rule.variable]
            if isinstance(data, str):
                risks.append(assess(rule, []).model_copy(update={"reason": data}))
                continue
            risks.append(assess(rule, accumulate_24h(data) if rule.aggregation == "sum_24h" else data))

        usable = [r for r in risks if r.status == "ok"]
        times = [p.valid_time for r in usable for p in r.timeline]
        return RiskResponse(
            location=resolved_location,
            latitude=coords[0],
            longitude=coords[1],
            forecast_days=forecast_days,
            lead_day=lead_day,
            status="ok" if usable else "insufficient_data",
            message=None if usable else "Risk assessment unavailable because forecast data is unavailable.",
            horizon_start=min(times) if times else None,
            horizon_end=max(times) if times else None,
            source_label=SOURCE_LABEL,
            disclaimer=DISCLAIMER,
            risks=risks,
        )


risk_service = RiskService()
