"""NOAA GFS provider adapter."""

from app.schemas.weather import ModelDescriptor
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider


class GFSProvider(OpenMeteoSingleRunProvider):
    def __init__(self) -> None:
        super().__init__(
            ModelDescriptor(
                name="NOAA GFS",
                model_type="Physics NWP",
                provider="NCEP / NOAA",
                status="live",
                source="Open-Meteo Single Runs API (NCEP GFS Global)",
            ),
            source_model="gfs_global",
        )
