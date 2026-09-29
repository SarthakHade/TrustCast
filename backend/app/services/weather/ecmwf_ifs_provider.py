"""ECMWF IFS provider adapter."""

from app.schemas.weather import ModelDescriptor
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider


class ECMWFIFSProvider(OpenMeteoSingleRunProvider):
    def __init__(self) -> None:
        super().__init__(
            ModelDescriptor(
                name="ECMWF IFS",
                model_type="Physics NWP",
                provider="ECMWF",
                status="live",
                source="Open-Meteo Single Runs API (ECMWF IFS Open Data)",
            ),
            source_model="ecmwf_ifs025",
        )
