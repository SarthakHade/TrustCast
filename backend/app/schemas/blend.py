"""Pydantic schemas for Step 5 trust-weighted forecast blending."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.weather import ProviderStatus, WeatherSchema

BlendStatus = Literal["ok", "insufficient_data"]


class BlendPoint(WeatherSchema):
    """One blended value at one valid time. Values are full precision; round only for display."""

    valid_time: datetime
    status: BlendStatus
    blended_value: float | None
    contributors: dict[str, float]
    effective_weights: dict[str, float]
    renormalized: bool
    # Adaptive method only: bias-corrected model values actually blended, lead day and rule-based regime used.
    corrected: dict[str, float] = Field(default_factory=dict)
    lead_day: int | None = None
    regime: str | None = None


class BlendModel(WeatherSchema):
    model: str
    trust_weight: float
    trust_weight_percent: float | None
    init_time: datetime | None
    points: int


class ExcludedModel(WeatherSchema):
    model: str
    status: ProviderStatus
    reason: str


class BlendResponse(WeatherSchema):
    location: str
    latitude: float
    longitude: float
    variable: str
    unit: str
    forecast_days: int
    trust_lead_day: int
    status: BlendStatus
    message: str | None = None
    method: str
    formula: list[str]
    models_used: list[BlendModel]
    excluded_models: list[ExcludedModel]
    forecast: list[BlendPoint]
    # Adaptive (bias-corrected, stacked) configuration actually used, or why the previous weights were used.
    adaptive: dict[str, Any] | None = None
