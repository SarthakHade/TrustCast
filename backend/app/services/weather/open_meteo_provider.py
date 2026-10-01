"""Adapter for real model-specific point forecasts from Open-Meteo."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import OPEN_METEO_SINGLE_RUNS_URL
from app.schemas.weather import ForecastRecord, ModelDescriptor, ProviderForecast
from app.services.weather.forecast_provider import (
    ForecastProvider,
    ProviderDataError,
    ProviderWaitingError,
)

HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
)


class OpenMeteoSingleRunProvider(ForecastProvider):
    """Fetch a known model run, retaining the true run initialization time."""

    availability_delay_hours = 7
    run_interval_hours = 6

    def __init__(self, descriptor: ModelDescriptor, source_model: str) -> None:
        self.descriptor = descriptor.model_copy(update={
            "source_type": "live_api",
            "is_live": True,
            "variables": descriptor.variables or ["temperature", "precipitation", "wind_speed", "humidity"],
        })
        self.source_model = source_model

    def _candidate_runs(self, now: datetime | None = None) -> list[datetime]:
        """Try recent completed 00/06/12/18 UTC model runs, newest first."""
        current = (now or datetime.now(UTC)).astimezone(UTC)
        eligible = current - timedelta(hours=self.availability_delay_hours)
        rounded_hour = eligible.hour - (eligible.hour % self.run_interval_hours)
        latest = eligible.replace(hour=rounded_hour, minute=0, second=0, microsecond=0)
        return [latest - timedelta(hours=self.run_interval_hours * index) for index in range(5)]

    async def get_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> ProviderForecast:
        errors: list[str] = []
        not_published = 0
        async with httpx.AsyncClient(timeout=20.0) as client:
            for init_time in self._candidate_runs():
                params = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "hourly": ",".join(HOURLY_VARIABLES),
                    "forecast_days": forecast_days,
                    "models": self.source_model,
                    "timeformat": "iso8601",
                    "run": init_time.strftime("%Y-%m-%dT%H:%M"),
                }
                try:
                    response = await client.get(OPEN_METEO_SINGLE_RUNS_URL, params=params)
                    if response.status_code == 400 and "not available" in response.text:
                        not_published += 1  # this run is not published yet; try an older one
                    response.raise_for_status()
                    payload = response.json()
                    return self.normalize_payload(payload, init_time)
                except (httpx.HTTPError, ValueError, ProviderDataError) as exc:
                    errors.append(str(exc))

        if not_published == len(self._candidate_runs()):
            raise ProviderWaitingError(
                f"No recent {self.descriptor.name} run is published yet (checked the last "
                f"{not_published} cycles); retried on the next refresh."
            )
        raise ProviderDataError(
            "No usable recent model run was returned by Open-Meteo. "
            f"Last error: {errors[-1] if errors else 'unknown error'}"
        )

    def normalize_payload(self, payload: Any, init_time: datetime) -> ProviderForecast:
        """Validate and normalize an Open-Meteo response without fabricating values."""
        if not isinstance(payload, dict):
            raise ProviderDataError("Provider response must be a JSON object")

        source_latitude = self._required_number(payload, "latitude")
        source_longitude = self._required_number(payload, "longitude")
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict):
            raise ProviderDataError("Provider response is missing the hourly forecast object")

        raw_times = hourly.get("time")
        if not isinstance(raw_times, list) or not raw_times:
            raise ProviderDataError("Provider response is missing hourly timestamps")

        times = [self._parse_timestamp(value) for value in raw_times]
        variable_series = {
            "temperature": self._optional_series(hourly, "temperature_2m", len(times)),
            "precipitation": self._optional_series(hourly, "precipitation", len(times)),
            "wind_speed": self._optional_series(hourly, "wind_speed_10m", len(times)),
            "humidity": self._optional_series(hourly, "relative_humidity_2m", len(times)),
        }

        records: list[ForecastRecord] = []
        for index, valid_time in enumerate(times):
            lead_seconds = (valid_time - init_time).total_seconds()
            if lead_seconds < 0 or lead_seconds % 3600 != 0:
                raise ProviderDataError("Forecast valid time is not aligned with its run time")

            precipitation = variable_series["precipitation"][index]
            wind_speed = variable_series["wind_speed"][index]
            humidity = variable_series["humidity"][index]
            if precipitation is not None and precipitation < 0:
                raise ProviderDataError("Provider response has negative precipitation")
            if wind_speed is not None and wind_speed < 0:
                raise ProviderDataError("Provider response has negative wind speed")
            if humidity is not None and not 0 <= humidity <= 100:
                raise ProviderDataError("Provider response has humidity outside 0-100")

            records.append(
                ForecastRecord(
                    model=self.descriptor.name,
                    model_type=self.descriptor.model_type,
                    provider=self.descriptor.provider,
                    latitude=source_latitude,
                    longitude=source_longitude,
                    init_time=init_time,
                    valid_time=valid_time,
                    lead_time_hours=int(lead_seconds // 3600),
                    temperature=variable_series["temperature"][index],
                    precipitation=precipitation,
                    wind_speed=wind_speed,
                    humidity=humidity,
                )
            )

        variables = [
            name for name in ("temperature", "precipitation", "wind_speed", "humidity")
            if any(value is not None for value in variable_series[name])
        ]
        return ProviderForecast(
            model=self.descriptor.name,
            model_type=self.descriptor.model_type,
            provider=self.descriptor.provider,
            status="live",
            source=self.descriptor.source,
            source_url=self.descriptor.source_url,
            init_time=init_time,
            forecast=records,
            source_type="live_api",
            is_live=True,
            tier=self.descriptor.tier,
            retrieved_at=datetime.now(UTC),
            variables=variables,
            provenance={
                "api": "Open-Meteo Single Runs API",
                "source_model": self.source_model,
                "run": init_time.isoformat(),
                "grid_latitude": source_latitude,
                "grid_longitude": source_longitude,
            },
        )

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if not isinstance(value, str):
            raise ProviderDataError("Forecast timestamp must be an ISO 8601 string")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=UTC)
        except ValueError as exc:
            raise ProviderDataError("Forecast timestamp is not valid ISO 8601") from exc

    @staticmethod
    def _required_number(payload: dict[str, Any], field_name: str) -> float:
        value = payload.get(field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProviderDataError(f"Provider response has invalid {field_name}")
        return float(value)

    @staticmethod
    def _optional_series(
        hourly: dict[str, Any], field_name: str, expected_length: int
    ) -> list[float | None]:
        values = hourly.get(field_name)
        if values is None:
            return [None] * expected_length
        if not isinstance(values, list) or len(values) != expected_length:
            raise ProviderDataError(f"Provider response has invalid {field_name} series")

        normalized: list[float | None] = []
        for value in values:
            if value is None:
                normalized.append(None)
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderDataError(f"Provider response has non-numeric {field_name} value")
            else:
                normalized.append(float(value))
        return normalized
