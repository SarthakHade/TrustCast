"""GraphCast/Pangu-Weather adapter placeholder pending a verified public feed."""

from app.schemas.weather import ModelDescriptor, ProviderForecast
from app.services.weather.forecast_provider import ForecastProvider, ProviderUnavailableError


class GraphCastProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="GraphCast / Pangu-Weather",
        model_type="AI weather model",
        provider="Google DeepMind / Huawei",
        status="adapter_ready",
        note="Adapter is reserved; no verified public point-forecast endpoint is configured.",
    )

    async def get_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> ProviderForecast:
        raise ProviderUnavailableError(self.descriptor.note or "GraphCast data is unavailable")
