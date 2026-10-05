"""Real historical data for the skill engine: ERA5 reference + archived Day-1/Day-2 forecasts.

* Archived forecasts: Open-Meteo Previous Runs API (`<variable>_previous_day<L>`), all four
  contributing models, all variables and both lead days in one request per model.
* Reference: ERA5 via the Open-Meteo Historical Weather API (published ~5 days behind real time).
* History starts on HISTORY_START, the first day for which all four models have archived forecasts
  (ECMWF AIFS archive begins 2025-02-18; probed against the live API).

Protection for the free API: several locations per request, date chunks, a small concurrency limit,
exponential backoff with Retry-After on HTTP 429/5xx, an on-disk cache that is refreshed
incrementally (only the most recent days are re-downloaded), and a stale-cache fallback when the
refresh fails. Nothing is ever filled in: missing or implausible values stay missing.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.config import OPEN_METEO_ARCHIVE_URL, OPEN_METEO_PREVIOUS_RUNS_URL, SKILL_CACHE_DIR
from app.services.skill.stats import plausible
from app.services.skill.walkforward import Dataset

HISTORY_START = date(2025, 2, 18)
LEAD_DAYS = (1, 2)
CHUNK_DAYS = 120
REFRESH_OVERLAP_DAYS = 10     # ERA5 and late archive entries fill in; re-download this many recent days
MAX_LOCATIONS_PER_REQUEST = 20
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 6

# TrustCast variable -> Open-Meteo hourly variable
OM_VARIABLES = {
    "temperature": "temperature_2m",
    "precipitation": "precipitation",
    "wind_speed": "wind_speed_10m",
    "humidity": "relative_humidity_2m",
}
REFERENCE_VARIABLES = ("temperature", "precipitation", "wind_speed")
# Units are requested explicitly so the reference and every model are guaranteed to match TrustCast units.
UNITS = {"temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"}


class DataUnavailableError(RuntimeError):
    pass


@dataclass
class ModelSource:
    name: str
    om_model: str


class RateLimitedClient:
    """Shared HTTP access with a concurrency cap, minimum spacing and backoff."""

    def __init__(self, concurrency: int = 2, min_interval_s: float = 0.25) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._min_interval = min_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()
        self.requests = 0
        self.retries = 0

    async def get_json(self, client: httpx.AsyncClient, url: str, params: dict) -> Any:
        async with self._sem:
            for attempt in range(MAX_RETRIES):
                async with self._lock:
                    wait = self._last + self._min_interval - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._last = time.monotonic()
                self.requests += 1
                response = await client.get(url, params=params)
                if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES - 1:
                    self.retries += 1
                    retry_after = response.headers.get("retry-after")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2.0 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
        raise DataUnavailableError("Upstream request failed after retries")


default_client = RateLimitedClient()


def _chunks(start: date, end: date) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        stop = min(end, cur + timedelta(days=CHUNK_DAYS - 1))
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def _as_list(payload: Any) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _parse(block: dict, field_map: dict[str, str], quality: dict[str, int]) -> dict[str, dict[str, float]]:
    """field_map: response field -> TrustCast variable. Returns variable -> 'YYYY-MM-DDTHH' -> value."""
    hourly = block.get("hourly") or {}
    times = hourly.get("time") or []
    out: dict[str, dict[str, float]] = {}
    seen: set[str] = set()
    for idx, raw_t in enumerate(times):
        key = raw_t[:13]
        if key in seen:
            quality["duplicate_timestamps"] = quality.get("duplicate_timestamps", 0) + 1
            continue
        seen.add(key)
        for field_name, variable in field_map.items():
            values = hourly.get(field_name)
            if not isinstance(values, list) or idx >= len(values):
                continue
            v = values[idx]
            if v is None:
                quality["missing_values"] = quality.get("missing_values", 0) + 1
                continue
            if not plausible(variable.split("@")[0], v):
                quality["rejected_implausible"] = quality.get("rejected_implausible", 0) + 1
                continue
            out.setdefault(variable, {})[key] = float(v)
    return out


async def fetch_raw(
    locations: list[dict], models: list[ModelSource], start: date, end: date,
    client: RateLimitedClient = default_client,
) -> list[dict]:
    """Download reference + archived forecasts for many locations. One raw dict per location."""
    results = [{"obs": {}, "fc": {}, "quality": {}} for _ in locations]
    model_fields = {
        f"{om}_previous_day{lead}": f"{var}@{lead}"
        for lead in LEAD_DAYS for var, om in OM_VARIABLES.items()
    }
    ref_fields = {OM_VARIABLES[v]: v for v in REFERENCE_VARIABLES}
    async with httpx.AsyncClient(timeout=120.0) as http:
        for b0 in range(0, len(locations), MAX_LOCATIONS_PER_REQUEST):
            batch = locations[b0:b0 + MAX_LOCATIONS_PER_REQUEST]
            lat = ",".join(f"{loc['latitude']:.4f}" for loc in batch)
            lon = ",".join(f"{loc['longitude']:.4f}" for loc in batch)
            for c0, c1 in _chunks(start, end):
                common = {"latitude": lat, "longitude": lon, "start_date": c0.isoformat(), "end_date": c1.isoformat(), "timezone": "GMT"} | UNITS
                ref = await client.get_json(http, OPEN_METEO_ARCHIVE_URL, common | {"hourly": ",".join(ref_fields), "models": "era5"})
                for idx, block in enumerate(_as_list(ref)):
                    r = results[b0 + idx]
                    for var, series in _parse(block, ref_fields, r["quality"]).items():
                        r["obs"].setdefault(var, {}).update(series)
                for model in models:
                    payload = await client.get_json(http, OPEN_METEO_PREVIOUS_RUNS_URL, common | {"hourly": ",".join(model_fields), "models": model.om_model})
                    for idx, block in enumerate(_as_list(payload)):
                        r = results[b0 + idx]
                        for key, series in _parse(block, model_fields, r["quality"]).items():
                            r["fc"].setdefault(model.name, {}).setdefault(key, {}).update(series)
    return results


def to_dataset(raw: dict, models: list[str]) -> Dataset:
    def parse_t(s: str) -> datetime:
        return datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]))

    observed = {v: {parse_t(t): x for t, x in series.items()} for v, series in raw["obs"].items()}
    forecast: dict[int, dict[str, dict[str, dict[datetime, float]]]] = {lead: {} for lead in LEAD_DAYS}
    for model, fields in raw["fc"].items():
        for key, series in fields.items():
            var, lead = key.split("@")
            forecast[int(lead)].setdefault(model, {})[var] = {parse_t(t): x for t, x in series.items()}
    return Dataset(
        models=models, observed=observed, forecast=forecast,
        sources={
            "reference": "ERA5 reanalysis (Open-Meteo Historical Weather API)",
            "forecasts": "Archived Day-1/Day-2 forecasts (Open-Meteo Previous Runs API)",
        },
        quality=dict(raw.get("quality", {})),
    )


def _cache_path(location: dict) -> Path:
    return Path(SKILL_CACHE_DIR) / "history" / f"{location['latitude']:.4f}_{location['longitude']:.4f}.json"


async def load_history(location: dict, models: list[ModelSource], client: RateLimitedClient = default_client) -> tuple[Dataset, dict]:
    """History from HISTORY_START to yesterday for one point; incremental refresh with stale fallback."""
    path = _cache_path(location)
    today = datetime.now(UTC).date()
    end = today - timedelta(days=1)
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    names = [m.name for m in models]
    info = {"cache": "miss", "stale": False}
    if cached and cached.get("fetched_on") == today.isoformat() and cached.get("models") == names:
        info["cache"] = "hit"
        return to_dataset(cached, names), info | {"fetched_at": cached.get("fetched_at")}
    start = HISTORY_START
    if cached and cached.get("models") == names and cached.get("end"):
        start = max(HISTORY_START, date.fromisoformat(cached["end"]) - timedelta(days=REFRESH_OVERLAP_DAYS))
        info["cache"] = "incremental"
    try:
        [fresh] = await fetch_raw([location], models, start, end, client)
    except Exception as exc:
        if cached:
            info.update(cache="stale", stale=True, reason=str(exc))
            return to_dataset(cached, names), info | {"fetched_at": cached.get("fetched_at")}
        raise DataUnavailableError(f"Historical data could not be downloaded: {exc}") from exc
    merged = cached if (cached and info["cache"] == "incremental") else {"obs": {}, "fc": {}, "quality": {}}
    for var, series in fresh["obs"].items():
        merged["obs"].setdefault(var, {}).update(series)
    for model, fields in fresh["fc"].items():
        for key, series in fields.items():
            merged["fc"].setdefault(model, {}).setdefault(key, {}).update(series)
    for k, v in fresh["quality"].items():
        merged["quality"][k] = merged["quality"].get(k, 0) + v
    merged.update(models=names, start=HISTORY_START.isoformat(), end=end.isoformat(),
                  fetched_on=today.isoformat(), fetched_at=datetime.now(UTC).isoformat(timespec="seconds"))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged), encoding="utf-8")
    tmp.replace(path)
    return to_dataset(merged, names), info | {"fetched_at": merged["fetched_at"]}
