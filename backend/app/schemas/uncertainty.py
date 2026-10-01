"""Pydantic schemas for the Step 6 Uncertainty Engine."""

from datetime import datetime
from typing import Literal

from app.schemas.blend import ExcludedModel
from app.schemas.weather import WeatherSchema

UncertaintyStatus = Literal["ok", "limited_data", "insufficient_data"]
DisagreementLevel = Literal["LOW", "MEDIUM", "HIGH", "LIMITED_DATA"]


class UncertaintyPoint(WeatherSchema):
    valid_time: datetime
    status: UncertaintyStatus
    blended_value: float | None
    models_used: list[str]
    model_min: float | None = None
    model_max: float | None = None
    model_mean: float | None = None
    model_spread: float | None = None
    weighted_std: float | None = None
    disagreement_level: DisagreementLevel | None = None
    historical_lower: float | None = None
    historical_upper: float | None = None
    # Real ensemble member spread (std) at this valid time, per ensemble source (e.g. NOAA AIGEFS).
    ensemble_spread: dict[str, float] = {}


class DisagreementThresholds(WeatherSchema):
    """LOW ≤ low_max < MEDIUM ≤ medium_max < HIGH, from historical hourly model spreads."""

    low_max: float
    medium_max: float
    samples: int
    source: str


class HistoricalError(WeatherSchema):
    """Errors of the TrustCast blend itself (current weights applied to archived forecasts)."""

    samples: int
    rmse: float
    mae: float
    bias: float
    error_p10: float
    error_p90: float
    coverage: float
    period_start: datetime
    period_end: datetime
    note: str


class UncertaintyResponse(WeatherSchema):
    location: str
    variable: str
    unit: str
    forecast_days: int
    lead_day: int
    status: UncertaintyStatus
    message: str | None = None
    explanation: str
    formula: list[str]
    thresholds: DisagreementThresholds | None
    historical: HistoricalError | None
    models_used: list[str]
    excluded_models: list[ExcludedModel]
    forecast: list[UncertaintyPoint]
    ensemble_sources: dict[str, int] = {}  # ensemble source -> member count
