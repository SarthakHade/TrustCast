"""ECMWF AIFS provider adapter."""

from app.schemas.weather import ModelDescriptor
from app.services.weather.open_meteo_provider import OpenMeteoSingleRunProvider


class ECMWFAIFSProvider(OpenMeteoSingleRunProvider):
    def __init__(self) -> None:
        super().__init__(
            ModelDescriptor(
                name="ECMWF AIFS",
                model_type="AI weather model",
                provider="ECMWF",
                status="live",
                source="Open-Meteo Single Runs API (ECMWF AIFS Single Open Data)",
            ),
            source_model="ecmwf_aifs025_single",
        )
