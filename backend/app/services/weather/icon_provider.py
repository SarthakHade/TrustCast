"""DWD ICON (global) provider adapter: real model runs via the existing Open-Meteo single-run adapter."""

from app.schemas.weather import ModelDescriptor
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider


class ICONProvider(OpenMeteoSingleRunProvider):
    def __init__(self) -> None:
        super().__init__(
            ModelDescriptor(
                name="DWD ICON",
                model_type="Physics NWP",
                provider="DWD",
                status="live",
                source="Open-Meteo Single Runs API (DWD ICON Global)",
                tier="optional",
                variables=["temperature", "precipitation", "wind_speed", "humidity"],
            ),
            source_model="icon_global",
        )
