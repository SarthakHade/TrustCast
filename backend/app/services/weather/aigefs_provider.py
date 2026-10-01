"""NOAA AIGEFS (AI ensemble) provider adapter: real current runs via the Open-Meteo Ensemble API.

* Run (init) time comes from the API's own metadata (`last_run_initialisation_time`); it is not guessed.
* AIGEFS output is 6-hourly. Open-Meteo returns an hourly time axis, so only native 6-hourly
  valid times at or after the run time are kept (intermediate hours would be interpolation).
* Each record stores the ensemble mean (control + members), the member count and the member
  standard deviation, so ensemble spread is preserved rather than collapsed away.
* Precipitation is NOT ingested: for a 6-hourly model the meaning of Open-Meteo's hourly
  precipitation value (hour vs. redistributed 6-h amount) is not verified here, and mixing it
  into the hourly rainfall blend could be wrong.
* No archived AIGEFS forecasts are available for verification, so the Trust Engine cannot
  calibrate a reliability for it yet; it is shown live but is not weighted into the blend.
"""

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import OPEN_METEO_ENSEMBLE_META_URL, OPEN_METEO_ENSEMBLE_URL
from app.schemas.weather import ForecastRecord, ModelDescriptor, ProviderForecast
from app.services.weather.forecast_provider import (
    ForecastProvider,
    ProviderDataError,
    ProviderWaitingError,
)

SOURCE_MODEL = "ncep_aigefs025"
NATIVE_STEP_HOURS = 6
MAX_RUN_AGE_HOURS = 36
# TrustCast field -> Open-Meteo ensemble variable (precipitation deliberately excluded, see above)
ENSEMBLE_VARIABLES = {
    "temperature": "temperature_2m",
    "wind_speed": "wind_speed_10m",
    "humidity": "relative_humidity_2m",
}


def _member_values(hourly: dict[str, Any], base: str, index: int) -> list[float]:
    values = []
    for key, series in hourly.items():
        if key == base or key.startswith(f"{base}_member"):
            if isinstance(series, list) and index < len(series):
                value = series[index]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(float(value))
    return values


class AIGEFSProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="NOAA AIGEFS",
        model_type="AI ensemble",
        provider="NOAA / NCEP",
        status="live",
        source="Open-Meteo Ensemble API (NCEP AIGEFS 0.25°)",
        source_type="live_api",
        is_live=True,
        variables=["temperature", "wind_speed", "humidity"],
        note="Forecast available · reliability not yet calibrated (no archived AIGEFS forecasts to verify against ERA5).",
    )

    async def get_forecast(self, latitude: float, longitude: float, forecast_days: int) -> ProviderForecast:
        async with httpx.AsyncClient(timeout=30.0) as client:
            meta_response = await client.get(OPEN_METEO_ENSEMBLE_META_URL.format(model=SOURCE_MODEL))
            meta_response.raise_for_status()
            data_response = await client.get(
                OPEN_METEO_ENSEMBLE_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "hourly": ",".join(ENSEMBLE_VARIABLES.values()),
                    "forecast_days": forecast_days,
                    "models": SOURCE_MODEL,
                    "timeformat": "iso8601",
                    "timezone": "GMT",
                },
            )
            data_response.raise_for_status()
        return self.normalize(meta_response.json(), data_response.json(), datetime.now(UTC))

    def normalize(self, meta: Any, payload: Any, now: datetime) -> ProviderForecast:
        if not isinstance(meta, dict) or not isinstance(meta.get("last_run_initialisation_time"), int):
            raise ProviderDataError("AIGEFS metadata has no last_run_initialisation_time")
        init_time = datetime.fromtimestamp(meta["last_run_initialisation_time"], UTC)
        if now - init_time > timedelta(hours=MAX_RUN_AGE_HOURS):
            raise ProviderWaitingError(f"Latest published AIGEFS run ({init_time.isoformat()}) is older than {MAX_RUN_AGE_HOURS} h")
        if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
            raise ProviderDataError("AIGEFS response is missing the hourly object")
        hourly = payload["hourly"]
        times = hourly.get("time")
        if not isinstance(times, list) or not times:
            raise ProviderDataError("AIGEFS response is missing hourly timestamps")

        records: list[ForecastRecord] = []
        members_seen = 0
        for index, raw_time in enumerate(times):
            valid_time = datetime.fromisoformat(str(raw_time)).replace(tzinfo=UTC)
            if valid_time < init_time or valid_time.hour % NATIVE_STEP_HOURS:
                continue  # before this run, or an interpolated (non-native) hour
            values: dict[str, float | None] = {}
            spreads: dict[str, float | None] = {}
            for field, om_name in ENSEMBLE_VARIABLES.items():
                members = _member_values(hourly, om_name, index)
                values[field] = statistics.fmean(members) if members else None
                spreads[field] = statistics.pstdev(members) if len(members) >= 2 else None
                if field == "temperature":
                    members_seen = max(members_seen, len(members))
            if values["temperature"] is None:
                continue
            records.append(ForecastRecord(
                model=self.descriptor.name,
                model_type=self.descriptor.model_type,
                provider=self.descriptor.provider,
                latitude=float(payload.get("latitude", 0.0)),
                longitude=float(payload.get("longitude", 0.0)),
                init_time=init_time,
                valid_time=valid_time,
                lead_time_hours=int((valid_time - init_time).total_seconds() // 3600),
                temperature=values["temperature"],
                wind_speed=values["wind_speed"],
                humidity=None if values["humidity"] is None else min(100.0, max(0.0, values["humidity"])),
                ensemble_members=len(_member_values(hourly, "temperature_2m", index)),
                temperature_spread=spreads["temperature"],
                wind_speed_spread=spreads["wind_speed"],
            ))
        if not records:
            raise ProviderWaitingError(f"No AIGEFS values at or after the {init_time.isoformat()} run in the requested window yet")
        if members_seen < 2:
            raise ProviderDataError("AIGEFS response did not contain ensemble members")

        variables = [f for f in ("temperature", "wind_speed", "humidity") if any(getattr(r, f) is not None for r in records)]
        return ProviderForecast(
            model=self.descriptor.name,
            model_type=self.descriptor.model_type,
            provider=self.descriptor.provider,
            status="live",
            source=self.descriptor.source,
            init_time=init_time,
            forecast=records,
            source_type="live_api",
            is_live=True,
            retrieved_at=now,
            variables=variables,
            error=self.descriptor.note,
            provenance={
                "api": "Open-Meteo Ensemble API",
                "source_model": SOURCE_MODEL,
                "run": init_time.isoformat(),
                "run_published": datetime.fromtimestamp(meta["last_run_availability_time"], UTC).isoformat()
                if isinstance(meta.get("last_run_availability_time"), int) else None,
                "ensemble_members": members_seen,
                "native_step_hours": NATIVE_STEP_HOURS,
                "grid_latitude": payload.get("latitude"),
                "grid_longitude": payload.get("longitude"),
                "precipitation": "not ingested (6-hourly accumulation semantics not verified)",
            },
        )
