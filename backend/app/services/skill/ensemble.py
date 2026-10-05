"""NOAA AIGEFS ensemble guidance for extreme events: real member counts, never invented.

    P(event) = (members exceeding the threshold) / (members with complete data)

Data semantics (checked against the live Open-Meteo Ensemble API): AIGEFS is 6-hourly. For
precipitation Open-Meteo spreads each 6-hour amount evenly over its six hourly values (rounded to
0.1 mm), so the sum of 24 consecutive hourly values is the member's 24-hour total (rounding error
<= ~1 mm). Temperature and wind are taken only at native steps (00/06/12/18 UTC); intermediate hours
are interpolation and are ignored. Native steps can miss the afternoon temperature maximum, so heat
probabilities are conservative.

There are no archived AIGEFS forecasts, so these probabilities cannot be verified or calibrated
(no Brier score / reliability). They are labelled as ensemble exceedance probabilities, not as the
chance that an event will definitely happen.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import OPEN_METEO_ENSEMBLE_META_URL, OPEN_METEO_ENSEMBLE_URL
from app.data.risk_thresholds import RISK_RULES
from app.services.skill.stats import quantile
from app.services.weather.cache import InMemoryTTLCache

SOURCE_MODEL = "ncep_aigefs025"
NATIVE_STEP_HOURS = 6
MAX_RUN_AGE_HOURS = 36
MIN_MEMBERS = 20
OM_FIELD = {"precipitation": "precipitation", "temperature": "temperature_2m", "wind_speed": "wind_speed_10m"}
CAVEATS = [
    "Ensemble exceedance probabilities are member counts from the latest NOAA AIGEFS run; they are not verified or calibrated (no archived AIGEFS forecasts exist).",
    "Rain uses 24-hour member totals; temperature and wind use native 6-hourly steps only, which can miss the daily extreme.",
    "The 99th percentile is not reported: 31 members cannot resolve it.",
]

_cache = InMemoryTTLCache(ttl_seconds=1800)


def _members(hourly: dict[str, Any], base: str) -> list[list[float | None]]:
    out = []
    for key, series in hourly.items():
        if (key == base or key.startswith(f"{base}_member")) and isinstance(series, list):
            out.append([v if isinstance(v, (int, float)) and not isinstance(v, bool) else None for v in series])
    return out


def _summary(values: list[float]) -> dict[str, float | None]:
    return {"p50": quantile(values, 0.5), "p75": quantile(values, 0.75), "p90": quantile(values, 0.9), "max": max(values) if values else None}


def guidance_from_payload(meta: Any, payload: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(meta, dict) or not isinstance(meta.get("last_run_initialisation_time"), int):
        return {"status": "unavailable", "reason": "AIGEFS run metadata unavailable"}
    init = datetime.fromtimestamp(meta["last_run_initialisation_time"], UTC)
    if now - init > timedelta(hours=MAX_RUN_AGE_HOURS):
        return {"status": "unavailable", "reason": f"Latest AIGEFS run ({init.isoformat()}) is older than {MAX_RUN_AGE_HOURS} h"}
    hourly = (payload or {}).get("hourly") if isinstance(payload, dict) else None
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        return {"status": "unavailable", "reason": "AIGEFS response has no hourly data"}
    times = [datetime.fromisoformat(str(t)).replace(tzinfo=UTC) for t in hourly["time"]]
    risks: dict[str, Any] = {}
    max_members = 0
    for rule in RISK_RULES:
        members = _members(hourly, OM_FIELD[rule.variable])
        max_members = max(max_members, len(members))
        windows = []  # (end_time, member values)
        if rule.aggregation == "sum_24h":
            for idx, end in enumerate(times):
                if end.hour % NATIVE_STEP_HOURS or end < init + timedelta(hours=24) or idx < 23:
                    continue
                totals = []
                for series in members:
                    chunk = series[idx - 23: idx + 1]
                    if len(chunk) == 24 and all(v is not None for v in chunk):
                        totals.append(sum(chunk))
                windows.append((end, totals))
        else:
            for idx, t in enumerate(times):
                if t.hour % NATIVE_STEP_HOURS or t <= init:
                    continue
                windows.append((t, [s[idx] for s in members if s[idx] is not None]))
        windows = [(t, v) for t, v in windows if len(v) >= MIN_MEMBERS]
        if not windows:
            risks[rule.risk_type] = {"status": "unavailable", "reason": f"Fewer than {MIN_MEMBERS} complete members"}
            continue

        def exceed(values, thr):
            return sum(v >= thr if rule.direction == "above" else v <= thr for v in values)

        # The window/time with the highest chance of crossing the elevated, then the high threshold;
        # ties go to the most extreme ensemble median, then the earliest time.
        def rank(w):
            median = quantile(w[1], 0.5)
            return (exceed(w[1], rule.elevated) / len(w[1]), exceed(w[1], rule.high) / len(w[1]),
                    median if rule.direction == "above" else -median, -w[0].timestamp())

        end, values = max(windows, key=rank)
        thresholds = []
        for level, thr in (("ELEVATED", rule.elevated), ("HIGH", rule.high)):
            n = exceed(values, thr)
            thresholds.append({"level": level, "threshold": thr, "members_exceeding": n, "members_valid": len(values), "probability": n / len(values)})
        risks[rule.risk_type] = {
            "status": "ok", "variable": rule.variable, "unit": rule.unit, "direction": rule.direction,
            "aggregation": rule.aggregation,
            "valid_time": end.isoformat(),
            "window_start": (end - timedelta(hours=24)).isoformat() if rule.aggregation == "sum_24h" else None,
            "thresholds": thresholds,
            "member_percentiles": _summary(values),
        }
    return {
        "status": "ok" if any(r.get("status") == "ok" for r in risks.values()) else "unavailable",
        "source": "NOAA AIGEFS 0.25° via Open-Meteo Ensemble API",
        "run": init.isoformat(),
        "members": max_members,
        "risks": risks,
        "caveats": CAVEATS,
        "verification": "unavailable (no archived AIGEFS forecasts)",
    }


async def ensemble_guidance(latitude: float, longitude: float, forecast_days: int) -> dict[str, Any]:
    days = max(2, min(forecast_days + 1, 7))

    async def fetch():
        async with httpx.AsyncClient(timeout=30.0) as client:
            meta = await client.get(OPEN_METEO_ENSEMBLE_META_URL.format(model=SOURCE_MODEL))
            meta.raise_for_status()
            data = await client.get(OPEN_METEO_ENSEMBLE_URL, params={
                "latitude": latitude, "longitude": longitude, "hourly": ",".join(OM_FIELD.values()),
                "forecast_days": days, "models": SOURCE_MODEL, "timezone": "GMT",
                "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
            })
            data.raise_for_status()
        return guidance_from_payload(meta.json(), data.json(), datetime.now(UTC))

    key = f"{latitude:.4f}:{longitude:.4f}:{days}"
    return await _cache.get_or_set(key, fetch, cache_if=lambda r: r.get("status") == "ok")
