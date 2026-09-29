"""Common contract implemented by every forecast provider adapter."""

from abc import ABC, abstractmethod

from app.schemas.weather import ModelDescriptor, ProviderForecast


class ForecastProvider(ABC):
    """A source adapter that returns data in TrustCast's normalized format."""

    descriptor: ModelDescriptor

    def get_model_name(self) -> str:
        return self.descriptor.name

    def get_status(self) -> str:
        return self.descriptor.status

    @abstractmethod
    async def get_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> ProviderForecast:
        """Fetch and normalize a point forecast without applying any blending."""


class ProviderDataError(RuntimeError):
    """A live source returned an invalid or unusable response."""


class ProviderUnavailableError(RuntimeError):
    """A provider has no configured public point-forecast endpoint yet."""
