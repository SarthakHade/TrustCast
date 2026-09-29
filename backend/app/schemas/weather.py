"""Pydantic schemas for normalized Step 2 forecast data."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProviderStatus = Literal["live", "adapter_ready", "data_unavailable", "error"]


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
    note: str | None = None


class ModelListResponse(WeatherSchema):
    models: list[ModelDescriptor]


class ProviderForecast(WeatherSchema):
    model: str
    model_type: str
    provider: str
    status: ProviderStatus
    source: str | None = None
    init_time: datetime | None = None
    forecast: list[ForecastRecord] = Field(default_factory=list)
    error: str | None = None


class AllModelsForecastResponse(WeatherSchema):
    latitude: float
    longitude: float
    forecast_days: int
    results: list[ProviderForecast]
