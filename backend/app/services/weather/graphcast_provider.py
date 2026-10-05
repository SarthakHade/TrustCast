"""GraphCast and Pangu-Weather: OPTIONAL / NOT RUNNING.

No inference pipeline and no verified public point-forecast feed is connected. These adapters are
kept in the registry for future integration but are never fetched, scored, weighted, blended,
counted as available models, or used for uncertainty / risk.
"""

from app.schemas.weather import ModelDescriptor, ProviderForecast
from app.services.weather.forecast_provider import ForecastProvider, ProviderUnavailableError

NOT_RUNNING = "Not running: no inference pipeline or verified public point-forecast feed is connected."


class _InactiveProvider(ForecastProvider):
    async def get_forecast(self, latitude: float, longitude: float, forecast_days: int) -> ProviderForecast:
        raise ProviderUnavailableError(NOT_RUNNING)


class GraphCastProvider(_InactiveProvider):
    descriptor = ModelDescriptor(
        name="GraphCast",
        model_type="AI weather model",
        provider="Google DeepMind",
        status="inactive",
        tier="optional",
        note=NOT_RUNNING,
    )


class PanguProvider(_InactiveProvider):
    descriptor = ModelDescriptor(
        name="Pangu-Weather",
        model_type="AI weather model",
        provider="Huawei",
        status="inactive",
        tier="optional",
        note=NOT_RUNNING,
    )
