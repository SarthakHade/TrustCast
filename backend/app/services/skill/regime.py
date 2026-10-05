"""IMD seasons and a transparent, rule-based daily weather regime.

The regime of a day is classified from the *forecast* fields (mean of the contributing models at the
lead time being verified), never from observations, so it is known at forecast issue time and can be
used both in walk-forward training and in live inference without leakage.

These are simple threshold rules, not a full meteorological regime classifier:

    STRONG_WIND     daily max 10 m wind >= 41 km/h
    HEATWAVE        daily max 2 m temperature >= 40 °C (absolute plains criterion; no climatology
                    departure is available, so IMD's departure-based criteria are not applied)
    ACTIVE_MONSOON  June–September, daily rain >= 15.6 mm and mean RH >= 80 %
    CONVECTIVE      outside June–September, daily rain >= 15.6 mm
    FOG_PRONE       November–February, min temperature <= 12 °C, max RH >= 95 %, min wind <= 7 km/h
    MONSOON_BREAK   June–September, daily rain < 2.5 mm
    NORMAL          none of the above

Priority follows the order above (the first matching rule wins).
"""

from __future__ import annotations

from datetime import date

SEASONS = {
    1: "WINTER", 2: "WINTER",
    3: "PRE_MONSOON", 4: "PRE_MONSOON", 5: "PRE_MONSOON",
    6: "MONSOON", 7: "MONSOON", 8: "MONSOON", 9: "MONSOON",
    10: "POST_MONSOON", 11: "POST_MONSOON", 12: "POST_MONSOON",
}
SEASON_LABEL = {
    "WINTER": "Winter (Jan–Feb)",
    "PRE_MONSOON": "Pre-monsoon (Mar–May)",
    "MONSOON": "Monsoon (Jun–Sep)",
    "POST_MONSOON": "Post-monsoon (Oct–Dec)",
}
REGIME_LABEL = {
    "STRONG_WIND": "Strong wind",
    "HEATWAVE": "Heatwave",
    "ACTIVE_MONSOON": "Active monsoon",
    "CONVECTIVE": "Heavy-rain / convective",
    "FOG_PRONE": "Fog-prone winter",
    "MONSOON_BREAK": "Monsoon break",
    "NORMAL": "Normal",
    "UNKNOWN": "Unknown (insufficient forecast data)",
}
MIN_HOURS_FOR_REGIME = 18


def season_of(day: date) -> str:
    return SEASONS[day.month]


def classify_day(
    day: date,
    temperature: list[float],
    precipitation: list[float],
    wind: list[float],
    humidity: list[float],
) -> str:
    """Regime of one day from hourly forecast values (already filtered to valid numbers)."""
    if min(len(temperature), len(precipitation), len(wind)) < MIN_HOURS_FOR_REGIME:
        return "UNKNOWN"
    monsoon_months = 6 <= day.month <= 9
    rain = sum(precipitation)
    mean_rh = sum(humidity) / len(humidity) if humidity else None
    if max(wind) >= 41.0:
        return "STRONG_WIND"
    if max(temperature) >= 40.0:
        return "HEATWAVE"
    if monsoon_months and rain >= 15.6 and mean_rh is not None and mean_rh >= 80.0:
        return "ACTIVE_MONSOON"
    if not monsoon_months and rain >= 15.6:
        return "CONVECTIVE"
    if day.month in (11, 12, 1, 2) and humidity and min(temperature) <= 12.0 and max(humidity) >= 95.0 and min(wind) <= 7.0:
        return "FOG_PRONE"
    if monsoon_months and rain < 2.5:
        return "MONSOON_BREAK"
    return "NORMAL"
