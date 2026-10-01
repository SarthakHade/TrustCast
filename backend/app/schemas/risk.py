"""Pydantic schemas for the Step 7 forecast-based risk indicators."""

from datetime import datetime
from typing import Literal

from app.schemas.weather import WeatherSchema

RiskLevel = Literal["NORMAL", "ELEVATED", "HIGH"]
RangePosition = Literal["CLEARLY_BELOW", "THRESHOLD_CROSSED", "CLEARLY_ABOVE"]


class ThresholdCheck(WeatherSchema):
    level: RiskLevel
    threshold: float
    position: RangePosition
    models_exceeding: int
    models_total: int


class RiskTimelinePoint(WeatherSchema):
    valid_time: datetime
    level: RiskLevel
    value: float


class RiskIndicator(WeatherSchema):
    risk_type: str
    title: str
    variable: str
    unit: str
    status: Literal["ok", "data_unavailable"]
    reason: str | None = None
    direction: Literal["above", "below"]
    thresholds: dict[str, float]
    aggregation: str
    basis: str
    level: RiskLevel | None = None
    peak_time: datetime | None = None
    window_start: datetime | None = None
    accumulation_hours: int | None = None
    forecast_value: float | None = None
    lower: float | None = None
    upper: float | None = None
    range_source: str | None = None
    key_threshold: float | None = None
    range_position: RangePosition | None = None
    threshold_crossing: bool = False
    models_exceeding: int = 0
    models_total: int = 0
    model_consensus: str | None = None
    checks: list[ThresholdCheck] = []
    messages: list[str] = []
    timeline: list[RiskTimelinePoint] = []


class RiskResponse(WeatherSchema):
    location: str
    forecast_days: int
    lead_day: int
    status: Literal["ok", "insufficient_data"]
    message: str | None = None
    horizon_start: datetime | None
    horizon_end: datetime | None
    source_label: str
    disclaimer: str
    risks: list[RiskIndicator]
