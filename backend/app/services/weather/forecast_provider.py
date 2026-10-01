"""Common contract implemented by every forecast provider adapter."""

from abc import ABC, abstractmethod

from app.schemas.weather import ModelDescriptor, Provenance, ProviderForecast


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

    async def probe(self) -> Provenance | None:
        """Optional: check the official source of a non-ingested model and describe what it publishes.

        Used for models whose source is real but cannot be turned into point values (no forecast
        values are ever produced here). Returns None when the provider has nothing to report.
        """
        return None


class ProviderDataError(RuntimeError):
    """A live source returned an invalid or unusable response."""


class ProviderUnavailableError(RuntimeError):
    """A provider has no configured public point-forecast endpoint yet."""


class ProviderWaitingError(ProviderDataError):
    """The source is reachable but the expected model run has not been published yet."""
