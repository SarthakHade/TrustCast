"""Pydantic schemas for Step 3 historical model verification."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.weather import ProviderStatus, WeatherSchema

PerformanceVariable = Literal["temperature", "precipitation", "wind_speed"]
DataMode = Literal["real_archived_forecasts"]


class ModelPerformance(WeatherSchema):
    """Verification metrics for one model; metrics are null when the model has no data."""

    model: str
    model_type: str
    provider: str
    status: ProviderStatus
    samples: int = 0
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    correlation: float | None = None
    skill_score: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None
    # "archived_forecasts" = real archived forecasts scored against ERA5; None = not verified
    calibration: Literal["archived_forecasts"] | None = None


class PerformanceResponse(WeatherSchema):
    location: str
    latitude: float
    longitude: float
    variable: PerformanceVariable
    unit: str
    lead_day: int
    period_start: datetime | None
    period_end: datetime | None
    data_mode: DataMode
    forecast_source: str
    observation_source: str
    skill_method: str
    models: list[ModelPerformance]
