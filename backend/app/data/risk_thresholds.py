"""Step 7 risk thresholds: the ONLY place these numbers live. Edit here to change them.

These are DEMO thresholds for a forecast-based risk indicator. They are NOT official
warnings and are not an IMD warning system. Reference points used when choosing them:
  * Heavy rain: IMD's 24-hour rainfall intensity categories ("heavy" 64.5 mm, "very heavy"
    115.6 mm) are used as the ELEVATED / HIGH cut-offs for the 24-hour accumulated total.
  * High wind: 10 m sustained wind; 41 km/h (≈22 kt, Beaufort "strong breeze") and 62 km/h
    (≈34 kt, Beaufort "gale") are published meteorological category boundaries.
  * Heat / cold: round demo values for hourly 2 m air temperature (not heat-wave / cold-wave criteria,
    which also depend on station climatology).

Units match the Step 2 source exactly (Open-Meteo): temperature °C, precipitation mm per hour
(summed to a 24 h total here), wind speed km/h. No unit conversion is required.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RiskRule:
    risk_type: str
    title: str
    variable: str  # TrustCast variable used by Steps 3-6
    unit: str
    direction: Literal["above", "below"]  # risk when the value is above / below the threshold
    elevated: float
    high: float
    aggregation: Literal["hourly", "sum_24h"]
    basis: str


RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        risk_type="HEAVY_RAIN",
        title="Heavy Rainfall",
        variable="precipitation",
        unit="mm",
        direction="above",
        elevated=64.5,
        high=115.6,
        aggregation="sum_24h",
        basis="24-hour accumulated TrustCast precipitation; cut-offs follow IMD 'heavy' / 'very heavy' categories",
    ),
    RiskRule(
        risk_type="HEAT",
        title="Heat Risk Indicator",
        variable="temperature",
        unit="°C",
        direction="above",
        elevated=35.0,
        high=40.0,
        aggregation="hourly",
        basis="Hourly 2 m temperature (demo thresholds)",
    ),
    RiskRule(
        risk_type="COLD",
        title="Cold Risk Indicator",
        variable="temperature",
        unit="°C",
        direction="below",
        elevated=10.0,
        high=4.0,
        aggregation="hourly",
        basis="Hourly 2 m temperature (demo thresholds)",
    ),
    RiskRule(
        risk_type="HIGH_WIND",
        title="High Wind",
        variable="wind_speed",
        unit="km/h",
        direction="above",
        elevated=41.0,
        high=62.0,
        aggregation="hourly",
        basis="Hourly 10 m sustained wind; demo risk thresholds referenced to published meteorological categories",
    ),
)
