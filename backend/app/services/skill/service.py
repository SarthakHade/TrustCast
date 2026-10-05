"""Skill engine services: full walk-forward evaluation (/api/skill) and live adaptive parameters
(used by the blend, uncertainty and risk steps).

The user-facing forecast path never waits for a cold multi-month download: if a location's history
is not cached yet it is fetched in the background and the blend falls back to the previous
TrustCast weights (and says so) until it is ready.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, date, datetime, timedelta

from app.config import SKILL_CACHE_TTL_SECONDS
from app.services.location_service import LocationInput, location_key, resolve_location
from app.services.skill import dataset as ds
from app.services.skill import spatial
from app.services.skill.regime import REGIME_LABEL, SEASON_LABEL, classify_day, season_of
from app.services.skill.stats import quantile
from app.services.skill.walkforward import (
    BOOTSTRAP_RESAMPLES, CANDIDATES, ERA5_LAG_DAYS, MIN_REGIME_HOURS, MIN_STACK_HOURS,
    RIDGE_GRID, SELECT_WINDOW, TRAIN_DAYS, Dataset, WalkForward, summarise,
)
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider
from app.services.weather.weather_service import WeatherService, weather_service

log = logging.getLogger("trustcast.skill")

VARIABLES = {"temperature": "°C", "precipitation": "mm/h", "wind_speed": "km/h"}
LIVE_LOOKBACK_DAYS = 75          # evaluation days kept for live variant selection + OOS residuals
OOS_RESIDUAL_DAYS = 60
MIN_OOS_RESIDUALS = 48


class SkillService:
    def __init__(self, weather: WeatherService = weather_service) -> None:
        self.weather = weather
        self._datasets: dict[str, tuple[float, Dataset, dict]] = {}
        self._downloads: dict[str, asyncio.Task] = {}
        self._reports: dict[str, tuple[float, dict]] = {}
        self._live: dict[str, tuple[float, dict]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ models + data
    def model_sources(self) -> list[ds.ModelSource]:
        return [
            ds.ModelSource(p.get_model_name(), p.source_model)
            for p in self.weather.providers.values()
            if isinstance(p, OpenMeteoSingleRunProvider) and p.get_status() == "live"
        ]

    async def _download(self, location: dict) -> tuple[Dataset, dict]:
        data, info = await ds.load_history(location, self.model_sources())
        self._datasets[location_key(location)] = (time.monotonic(), data, info)
        return data, info

    def _start_download(self, location: dict) -> asyncio.Task:
        key = location_key(location)
        task = self._downloads.get(key)
        if task is None or task.done():
            task = asyncio.create_task(self._download(location))
            task.add_done_callback(lambda t: t.exception() and log.warning("history download failed: %s", t.exception()))
            self._downloads[key] = task
        return task

    async def dataset(self, location: dict, wait: bool) -> tuple[Dataset | None, dict]:
        key = location_key(location)
        cached = self._datasets.get(key)
        if cached and time.monotonic() - cached[0] < SKILL_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
        if wait:
            return await self._start_download(location)
        # Non-blocking path (live forecast): use any on-disk history now, refresh in the background.
        path = ds._cache_path(location)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                names = [m.name for m in self.model_sources()]
                if raw.get("models") == names:
                    data = ds.to_dataset(raw, names)
                    info = {"cache": "disk", "stale": raw.get("fetched_on") != datetime.now(UTC).date().isoformat(), "fetched_at": raw.get("fetched_at")}
                    # Keep it in memory either way; a stale copy is replaced when the refresh finishes.
                    self._datasets[key] = (time.monotonic(), data, info)
                    if info["stale"]:
                        self._start_download(location)
                    return data, info
            except (OSError, ValueError):
                pass
        self._start_download(location)
        return None, {"cache": "downloading"}

    # ------------------------------------------------------------ regimes of the live forecast
    async def forecast_regimes(self, latitude: float, longitude: float, forecast_days: int) -> dict[date, str]:
        """Rule-based regime of each forecast day from the contributing models' live forecasts."""
        names = {m.name for m in self.model_sources()}
        result = await self.weather.get_all_models(latitude, longitude, forecast_days)
        hourly: dict[date, dict[str, dict[int, list[float]]]] = {}
        for r in result.results:
            if r.model not in names or r.status != "live":
                continue
            for rec in r.forecast:
                day = rec.valid_time.astimezone(UTC).date()
                for field in ("temperature", "precipitation", "wind_speed", "humidity"):
                    v = getattr(rec, field)
                    if v is not None:
                        hourly.setdefault(day, {}).setdefault(field, {}).setdefault(rec.valid_time.hour, []).append(v)
        out = {}
        for day, fields in hourly.items():
            mean = {f: [sum(v) / len(v) for v in by_hour.values()] for f, by_hour in fields.items()}
            out[day] = classify_day(day, mean.get("temperature", []), mean.get("precipitation", []), mean.get("wind_speed", []), mean.get("humidity", []))
        return out

    # ------------------------------------------------------------ live adaptive parameters
    async def live(self, location_input: LocationInput, variable: str, regimes: dict[date, str]) -> dict:
        location = resolve_location(location_input)
        today = datetime.now(UTC).date()
        key = f"{location_key(location)}:{variable}:{today}:{sorted(set(regimes.values()))}"
        hit = self._live.get(key)
        if hit and time.monotonic() - hit[0] < SKILL_CACHE_TTL_SECONDS:
            return hit[1]
        data, info = await self.dataset(location, wait=False)
        if data is None:
            return {"status": "training", "message": "Adaptive model is being trained for this location; previous TrustCast weights are used meanwhile.", "data": info}
        wanted = sorted(set(regimes.values()) | {"NORMAL"})
        leads = {}
        loop = asyncio.get_running_loop()
        for lead in (1, 2):
            target = today + timedelta(days=lead)
            leads[lead] = await loop.run_in_executor(None, _live_for_lead, data, variable, lead, target, wanted, today)
        for lead, block in leads.items():
            apply_regional_pool(block, variable, lead)
        out = {
            "status": "adaptive" if all(l["fits"] for l in leads.values()) else "unavailable",
            "message": None,
            "issued": today.isoformat(),
            "leads": leads,
            "data": info,
        }
        if out["status"] != "adaptive":
            out["message"] = "Not enough verified history for the adaptive model; previous TrustCast weights are used."
        self._live[key] = (time.monotonic(), out)
        return out

    # ------------------------------------------------------------ full evaluation report
    async def report(self, location_input: LocationInput, variable: str, lead_day: int) -> dict:
        if variable not in VARIABLES:
            raise KeyError(f"Unknown variable '{variable}'. Use one of: {', '.join(VARIABLES)}")
        if lead_day not in ds.LEAD_DAYS:
            raise KeyError(f"lead_day must be one of {ds.LEAD_DAYS}")
        location = resolve_location(location_input)
        today = datetime.now(UTC).date()
        key = f"{location_key(location)}:{variable}:{lead_day}:{today}"
        hit = self._reports.get(key)
        if hit and time.monotonic() - hit[0] < SKILL_CACHE_TTL_SECONDS:
            return hit[1]
        data, info = await self.dataset(location, wait=True)
        loop = asyncio.get_running_loop()
        try:
            regimes = await self.forecast_regimes(location["latitude"], location["longitude"], 3)
        except Exception:
            regimes = {}
        target = today + timedelta(days=lead_day)
        report = await loop.run_in_executor(None, _full_report, data, variable, lead_day, target, regimes.get(target, "UNKNOWN"))
        report.update({
            "location": location["name"], "latitude": location["latitude"], "longitude": location["longitude"],
            "variable": variable, "unit": VARIABLES[variable], "lead_day": lead_day,
            "models": data.models, "sources": data.sources, "data_quality": data.quality | {"cache": info.get("cache"), "stale": info.get("stale", False)},
            "data_fetched_at": info.get("fetched_at"),
            "methodology": methodology(lead_day),
            "probabilistic": {
                "status": "unavailable",
                "reason": "No archived NOAA AIGEFS ensemble forecasts are available, so ensemble probabilities "
                          "cannot be verified (no Brier score, reliability diagram or CRPS). Deterministic forecasts "
                          "are never scored with probabilistic metrics.",
            },
        })
        self._reports[key] = (time.monotonic(), report)
        return report


def apply_regional_pool(block: dict, variable: str, lead: int) -> None:
    """Hierarchy step between location and default: regime weights pooled across grid cells.

    REGIME+LOCATION -> REGIME (regional pool) -> LOCATION -> REGIONAL (all regimes) -> previous weights.
    Only used live: the pool is trained on data before the precompute run, which is in the future for
    most walk-forward days, so it is not part of the out-of-sample evaluation.
    """
    store = spatial.weights(variable, lead) or {}
    pooled = store.get("pooled") or {}
    for regime, fit in block["fits"].items():
        level = fit.get("level", "")
        if fit.get("variant") == "bc_regime" and level.startswith("location (only") and regime in pooled:
            p = pooled[regime]
            fit.update(weights=p["weights"], level=f"regime (regional pool: {p['cells']} cells, {p['hours']} h)", samples=p["hours"])
        elif level.startswith("fallback") and "ALL" in pooled:
            p = pooled["ALL"]
            fit.update(weights=p["weights"], level=f"regional pool (all regimes, {p['cells']} cells)", samples=p["hours"])


def _live_for_lead(data: Dataset, variable: str, lead: int, target: date, regimes: list[str], today: date) -> dict:
    wf = WalkForward(data, variable, lead)
    result = wf.run(eval_from=today - timedelta(days=LIVE_LOOKBACK_DAYS), extra_targets=[(target, r) for r in regimes])
    fits = {r: f for (_, r), f in result["live"].items() if f.get("status") == "ok"}
    recent = result["days"][-OOS_RESIDUAL_DAYS:]
    residuals = [p["trustcast"] - y for d in recent for _, y, p in d["rows"] if y is not None and p.get("trustcast") is not None]
    oos = None
    if len(residuals) >= MIN_OOS_RESIDUALS:
        oos = {
            "samples": len(residuals),
            "p10": quantile(residuals, 0.1), "p90": quantile(residuals, 0.9),
            "rmse": (sum(e * e for e in residuals) / len(residuals)) ** 0.5,
            "mae": sum(abs(e) for e in residuals) / len(residuals),
            "bias": sum(residuals) / len(residuals),
            "period_start": recent[0]["day"].isoformat(), "period_end": recent[-1]["day"].isoformat(),
        }
    return {"fits": fits, "oos": oos, "models": wf.models}


def _full_report(data: Dataset, variable: str, lead: int, target: date, regime: str) -> dict:
    wf = WalkForward(data, variable, lead)
    regimes = sorted({regime, "NORMAL"})
    result = wf.run(extra_targets=[(target, r) for r in regimes])
    report = summarise(result, data.models, variable)
    live = result["live"].get((target, regime)) or result["live"].get((target, "NORMAL"))
    if live and live.get("status") == "ok":
        bias = live.pop("bias")
        live["bias_correction"] = {"kind": bias.kind, "mode": bias.mode, "per_model": bias.summary(data.models)}
    report["live"] = live
    report["live_target"] = {"date": target.isoformat(), "regime": regime, "regime_label": REGIME_LABEL.get(regime, regime),
                             "season": season_of(target), "season_label": SEASON_LABEL[season_of(target)]}
    report["training"] = {"window_days": TRAIN_DAYS, "gap_days": lead + ERA5_LAG_DAYS}
    return report


def methodology(lead: int) -> dict:
    return {
        "validation": "Rolling-origin (walk-forward) validation: every target day is forecast with parameters "
                      "trained only on data available before the forecast was issued.",
        "training_window_days": TRAIN_DAYS,
        "issue_gap_days": lead + ERA5_LAG_DAYS,
        "issue_gap_reason": f"Day-{lead} forecasts are issued {lead} day(s) ahead and ERA5 is published ~{ERA5_LAG_DAYS} days late.",
        "bias_correction": "Additive per model and hour of day (temperature, wind); multiplicative ratio of totals, bounded 0.5–2, for rain.",
        "stacking": f"Constrained ridge stacking: minimise wᵀCw + λ‖w − 1/K‖² with w ≥ 0, Σw = 1 (C = bias-corrected error second moments); "
                    f"λ chosen on a time-ordered hold-out from {list(RIDGE_GRID)} × trace(C)/K; needs ≥ {MIN_STACK_HOURS} complete hours, else previous TrustCast weights.",
        "regime": f"Rule-based weather regime from the forecast fields; regime-specific weights need ≥ {MIN_REGIME_HOURS} past hours of that regime, else location weights.",
        "season": "IMD seasons (Jan–Feb, Mar–May, Jun–Sep, Oct–Dec); season-specific weights use all past days of the same season.",
        "selection": f"TrustCast uses whichever of {list(CANDIDATES)} had the lowest out-of-sample RMSE over the previous {SELECT_WINDOW} verifiable days.",
        "skill_score": "1 − RMSE_TrustCast / RMSE_baseline on hours where every method has a value; "
                       f"90% interval from a {BOOTSTRAP_RESAMPLES}-resample day-block bootstrap.",
        "reference_caveat": "ERA5 is a reanalysis produced by ECMWF; it can favour ECMWF models and represents rain poorly at a point.",
    }


skill_service = SkillService()
