"""Step 3: historical verification of archived model forecasts against ERA5 reanalysis.

For every hour in the evaluation window we pair:
  * the value a model forecast `lead_day` days earlier (Open-Meteo Previous Runs API), and
  * the ERA5 reanalysis value for that hour (Open-Meteo Historical Weather API).
Only hours where both values exist are scored. Nothing here is simulated.
"""

import asyncio
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config import (
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_PREVIOUS_RUNS_URL,
    PERFORMANCE_CACHE_TTL_SECONDS,
)
from app.data.locations import DEMO_LOCATIONS
from app.schemas.performance import ModelPerformance, PerformanceResponse
from app.services.weather.cache import InMemoryTTLCache
from app.services.weather.forecast_provider import ForecastProvider, ProviderDataError
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider
from app.services.weather.weather_service import WeatherService, weather_service

# TrustCast variable name -> (Open-Meteo hourly variable, unit)
VARIABLES = {
    "temperature": ("temperature_2m", "°C"),
    "precipitation": ("precipitation", "mm/h"),
    "wind_speed": ("wind_speed_10m", "km/h"),
}
ERA5_LAG_BUFFER_DAYS = 8  # ERA5 is published ~5 days behind real time
MAX_DAYS = 30  # raw data is fetched once for the longest window and trimmed per request
RETRY_STATUSES = {429, 500, 502, 503, 504}
SKILL_EPSILON = 0.01
# Relative reliability (normalized inverse MAE), not a standardized meteorological skill score.
SKILL_METHOD = "Inverse-MAE: reliability_i = (1 / (MAE_i + 0.01)) / Σ_j (1 / (MAE_j + 0.01))"

Series = dict[datetime, float]


def compute_metrics(pairs: list[tuple[float, float]]) -> dict[str, float | None]:
    """MAE, RMSE, bias and Pearson correlation for (forecast, observed) pairs."""
    if not pairs:
        return {"mae": None, "rmse": None, "bias": None, "correlation": None}
    errors = [forecast - observed for forecast, observed in pairs]
    correlation: float | None = None
    if len(pairs) >= 3:
        try:
            correlation = statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
        except statistics.StatisticsError:
            correlation = None  # one of the series is constant (e.g. no rain at all)
    return {
        "mae": statistics.fmean(abs(e) for e in errors),
        "rmse": math.sqrt(statistics.fmean(e * e for e in errors)),
        "bias": statistics.fmean(errors),
        "correlation": correlation,
    }


def compute_skill_scores(maes: dict[str, float]) -> dict[str, float]:
    """Normalize inverse MAE so the scores of all evaluated models sum to 1."""
    inverse = {model: 1.0 / (mae + SKILL_EPSILON) for model, mae in maes.items()}
    total = sum(inverse.values())
    return {model: value / total for model, value in inverse.items()} if total else {}


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _parse_hourly(payload: Any, field_name: str) -> Series:
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise ProviderDataError("Response is missing the hourly object")
    hourly = payload["hourly"]
    times, values = hourly.get("time"), hourly.get(field_name)
    if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
        raise ProviderDataError(f"Response has an invalid {field_name} series")
    series: Series = {}
    for raw_time, value in zip(times, values):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            series[datetime.fromisoformat(raw_time).replace(tzinfo=UTC)] = float(value)
    return series


async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> Any:
    """GET with a short backoff on rate limiting / transient server errors."""
    for attempt in range(3):
        response = await client.get(url, params=params)
        if response.status_code not in RETRY_STATUSES or attempt == 2:
            response.raise_for_status()
            return response.json()
        await asyncio.sleep(1.5 * (attempt + 1))


class PerformanceService:
    def __init__(self, weather: WeatherService = weather_service) -> None:
        self.weather = weather
        self.cache = InMemoryTTLCache(ttl_seconds=PERFORMANCE_CACHE_TTL_SECONDS)
        self.raw_cache = InMemoryTTLCache(ttl_seconds=PERFORMANCE_CACHE_TTL_SECONDS)

    @staticmethod
    def _resolve(location_name: str, variable: str) -> dict:
        location = next(
            (loc for loc in DEMO_LOCATIONS if loc["name"].casefold() == location_name.casefold()),
            None,
        )
        if location is None:
            names = ", ".join(loc["name"] for loc in DEMO_LOCATIONS)
            raise KeyError(f"Unknown location '{location_name}'. Use one of: {names}")
        if variable not in VARIABLES:
            raise KeyError(f"Unknown variable '{variable}'. Use one of: {', '.join(VARIABLES)}")
        return location

    async def evaluate(
        self, location_name: str, variable: str, days: int, lead_day: int
    ) -> PerformanceResponse:
        location = self._resolve(location_name, variable)
        key = f"{location['name']}:{variable}:{days}:{lead_day}:{date.today().isoformat()}"
        result = await self.cache.get_or_set(
            key,
            lambda: self._evaluate(location, variable, days, lead_day),
            cache_if=lambda r: all(m.status != "error" for m in r.models),
        )
        return result.model_copy(deep=True)

    async def _fetch_raw(
        self, location: dict, om_variable: str, lead_day: int, evaluable: list
    ) -> tuple[Series | BaseException, list[Series | BaseException]]:
        """Fetch the maximum window once; every `days` setting is trimmed from this.

        Partial results (any source failed) are not cached, so a transient error such as
        HTTP 429 is retried on the next request instead of sticking for hours.
        """

        async def fetch():
            async with httpx.AsyncClient(timeout=30.0) as client:
                observations, *forecasts = await asyncio.gather(
                    self._fetch_observations(client, location, om_variable),
                    *[
                        self._fetch_archived_forecast(client, p, location, om_variable, lead_day)
                        for p in evaluable
                    ],
                    return_exceptions=True,
                )
            return observations, forecasts

        key = f"raw:{location['name']}:{om_variable}:{lead_day}:{date.today().isoformat()}"
        return await self.raw_cache.get_or_set(
            key,
            fetch,
            cache_if=lambda r: not any(isinstance(x, BaseException) for x in [r[0], *r[1]]),
        )

    def _evaluable(self) -> list[OpenMeteoSingleRunProvider]:
        return [
            p for p in self.weather.providers.values()
            if isinstance(p, OpenMeteoSingleRunProvider) and p.get_status() == "live"
        ]

    async def _window_data(
        self, location: dict, variable: str, days: int, lead_day: int
    ) -> tuple[Series, list[Series | BaseException]]:
        """ERA5 observations for the most recent `days` published days + raw archived forecasts."""
        om_variable, _ = VARIABLES[variable]
        all_observations, forecasts = await self._fetch_raw(
            location, om_variable, lead_day, self._evaluable()
        )
        if isinstance(all_observations, BaseException):
            raise ProviderDataError(f"ERA5 observations could not be loaded: {all_observations}")
        if not all_observations:
            raise ProviderDataError("ERA5 returned no observations for this window")
        cutoff = max(all_observations) - timedelta(days=days) + timedelta(hours=1)
        return {t: v for t, v in all_observations.items() if t >= cutoff}, forecasts

    async def verification_series(
        self, location_name: str, variable: str, days: int, lead_day: int
    ) -> tuple[Series, dict[str, Series]]:
        """Real (observations, archived forecasts per model) for the evaluation window.

        Reuses the same cached raw data as `evaluate`; models whose source failed are omitted.
        """
        location = self._resolve(location_name, variable)
        observations, forecasts = await self._window_data(location, variable, days, lead_day)
        series = {
            provider.get_model_name(): {t: v for t, v in forecast.items() if t in observations}
            for provider, forecast in zip(self._evaluable(), forecasts)
            if not isinstance(forecast, BaseException)
        }
        return observations, series

    async def _evaluate(
        self, location: dict, variable: str, days: int, lead_day: int
    ) -> PerformanceResponse:
        om_variable, unit = VARIABLES[variable]
        providers = list(self.weather.providers.values())
        evaluable = self._evaluable()
        observations, forecasts = await self._window_data(location, variable, days, lead_day)
        window = sorted(observations)
        maes: dict[str, float] = {}
        rows: dict[str, ModelPerformance] = {}
        for provider, forecast in zip(evaluable, forecasts):
            base = self._row(provider)
            if isinstance(forecast, BaseException):
                base.status = "error"
                base.note = f"Archived forecast could not be loaded: {forecast}"
                rows[provider.get_model_name()] = base
                continue
            pairs = [(forecast[t], observations[t]) for t in window if t in forecast]
            metrics = compute_metrics(pairs)
            base.calibration = "archived_forecasts"
            base.samples = len(pairs)
            base.mae, base.rmse = _round(metrics["mae"]), _round(metrics["rmse"])
            base.bias, base.correlation = _round(metrics["bias"]), _round(metrics["correlation"])
            if metrics["mae"] is not None:
                maes[provider.get_model_name()] = metrics["mae"]
            rows[provider.get_model_name()] = base

        for name, score in compute_skill_scores(maes).items():
            rows[name].skill_score = round(score, 4)

        models = []
        for provider in providers:
            if provider.get_status() == "inactive":
                continue  # optional, not running: never scored, weighted or listed as a contributor
            if provider.get_model_name() in rows:
                models.append(rows[provider.get_model_name()])
            else:
                row = self._row(provider)
                row.note = provider.descriptor.note or "No archived forecast source is connected."
                models.append(row)

        return PerformanceResponse(
            location=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            variable=variable,
            unit=unit,
            lead_day=lead_day,
            period_start=window[0] if window else None,
            period_end=window[-1] if window else None,
            data_mode="real_archived_forecasts",
            forecast_source=(
                f"Open-Meteo Previous Runs API ({om_variable}_previous_day{lead_day}): "
                f"value forecast by the model run issued ~{24 * lead_day}h before each hour"
            ),
            observation_source="ERA5 reanalysis via Open-Meteo Historical Weather API (≈5-day publication lag)",
            skill_method=SKILL_METHOD,
            models=models,
        )

    @staticmethod
    def _row(provider: ForecastProvider) -> ModelPerformance:
        return ModelPerformance(
            model=provider.get_model_name(),
            model_type=provider.descriptor.model_type,
            provider=provider.descriptor.provider,
            status=provider.get_status(),
        )

    @staticmethod
    async def _fetch_observations(
        client: httpx.AsyncClient, location: dict, om_variable: str
    ) -> Series:
        today = datetime.now(UTC).date()
        payload = await _get_json(
            client,
            OPEN_METEO_ARCHIVE_URL,
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "start_date": (today - timedelta(days=MAX_DAYS + ERA5_LAG_BUFFER_DAYS)).isoformat(),
                "end_date": (today - timedelta(days=1)).isoformat(),
                "hourly": om_variable,
                "models": "era5",
                "timezone": "GMT",
            },
        )
        return _parse_hourly(payload, om_variable)

    @staticmethod
    async def _fetch_archived_forecast(
        client: httpx.AsyncClient,
        provider: OpenMeteoSingleRunProvider,
        location: dict,
        om_variable: str,
        lead_day: int,
    ) -> Series:
        field_name = f"{om_variable}_previous_day{lead_day}"
        payload = await _get_json(
            client,
            OPEN_METEO_PREVIOUS_RUNS_URL,
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "hourly": field_name,
                "past_days": MAX_DAYS + ERA5_LAG_BUFFER_DAYS,
                "forecast_days": 1,
                "models": provider.source_model,
                "timezone": "GMT",
            },
        )
        return _parse_hourly(payload, field_name)


performance_service = PerformanceService()
