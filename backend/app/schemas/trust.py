"""Pydantic schemas for the Step 4 Trust Engine."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.weather import ProviderStatus, WeatherSchema

TrustStatus = Literal["ok", "single_model", "insufficient_data"]


class ModelTrust(WeatherSchema):
    """Trust Engine output for one model. Weight fields are null for excluded models."""

    model: str
    model_type: str
    status: ProviderStatus
    included: bool
    historical_rmse: float | None = None
    recent_rmse: float | None = None
    bias: float | None = None
    samples: int = 0
    historical_skill: float | None = None
    recent_skill: float | None = None
    trust_score: float | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    weight_percent: float | None = Field(default=None, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class TrustResponse(WeatherSchema):
    location: str
    latitude: float | None = None
    longitude: float | None = None
    variable: str
    unit: str
    lead_day: int
    status: TrustStatus
    message: str | None = None
    historical_period_start: datetime | None
    historical_period_end: datetime | None
    historical_days: int
    recent_days: int | None
    method: str
    formula: list[str]
    models: list[ModelTrust]
