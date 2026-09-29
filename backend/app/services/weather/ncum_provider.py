"""NCUM adapter placeholder until an official public point endpoint is available."""

from app.schemas.weather import ModelDescriptor, ProviderForecast
from app.services.weather.forecast_provider import ForecastProvider, ProviderUnavailableError


class NCUMProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="NCUM",
        model_type="Physics NWP",
        provider="NCMRWF / MoES",
        status="data_unavailable",
        note="No official public NCUM point-forecast endpoint is configured for this demo.",
    )

    async def get_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> ProviderForecast:
        raise ProviderUnavailableError(self.descriptor.note or "NCUM data is unavailable")
