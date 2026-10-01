"""Pydantic schemas for normalized Step 2 forecast data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Model status, decided at request time from what the real source actually returned:
#   live         real current forecast retrieved and validated
#   waiting      source reachable but the expected model run is not published yet
#   unavailable  official source checked, but no machine-readable point forecast can be ingested
#   error        retrieval / validation failed this time
#   inactive     optional model with no inference pipeline or verified feed (never fetched)
# "adapter_ready" / "data_unavailable" are kept only for backward compatibility of the API contract.
ProviderStatus = Literal["live", "waiting", "unavailable", "error", "inactive", "adapter_ready", "data_unavailable"]
ModelTier = Literal["core", "optional"]
Provenance = dict[str, str | int | float | bool | None]


class WeatherSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class DemoLocation(WeatherSchema):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ForecastRecord(WeatherSchema):
    """One normalized model forecast value at one valid time."""

    model: str
    model_type: str
    provider: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    init_time: datetime
    valid_time: datetime
    lead_time_hours: int = Field(ge=0)
    temperature: float | None = None
    precipitation: float | None = Field(default=None, ge=0)
    wind_speed: float | None = Field(default=None, ge=0)
    humidity: float | None = Field(default=None, ge=0, le=100)
    # Ensemble sources only: number of members and member standard deviation per variable.
    ensemble_members: int | None = None
    temperature_spread: float | None = Field(default=None, ge=0)
    precipitation_spread: float | None = Field(default=None, ge=0)
    wind_speed_spread: float | None = Field(default=None, ge=0)

    @field_validator("valid_time")
    @classmethod
    def timestamp_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("valid_time must include a timezone")
        return value

    @field_validator("init_time")
    @classmethod
    def init_timestamp_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("init_time must include a timezone")
        return value


class ModelDescriptor(WeatherSchema):
    name: str
    model_type: str
    provider: str
    status: ProviderStatus
    source: str | None = None
    source_url: str | None = None
    note: str | None = None
    source_type: str | None = None  # "live_api" | "official_catalogue" | None (not connected)
    is_live: bool = False
    tier: ModelTier = "core"
    variables: list[str] = Field(default_factory=list)  # variables the source can provide


class ModelListResponse(WeatherSchema):
    models: list[ModelDescriptor]


class ProviderForecast(WeatherSchema):
    model: str
    model_type: str
    provider: str
    status: ProviderStatus
    source: str | None = None
    source_url: str | None = None
    init_time: datetime | None = None
    forecast: list[ForecastRecord] = Field(default_factory=list)
    error: str | None = None
    source_type: str | None = None
    is_live: bool = False
    tier: ModelTier = "core"
    retrieved_at: datetime | None = None
    variables: list[str] = Field(default_factory=list)  # variables actually retrieved (non-empty)
    provenance: Provenance = Field(default_factory=dict)


class AllModelsForecastResponse(WeatherSchema):
    latitude: float
    longitude: float
    forecast_days: int
    results: list[ProviderForecast]
