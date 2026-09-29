"""Orchestration layer for Step 2 forecast-provider adapters."""

import asyncio

from app.data.locations import DEMO_LOCATIONS
from app.schemas.weather import (
    AllModelsForecastResponse,
    DemoLocation,
    ModelDescriptor,
    ProviderForecast,
)
from app.services.weather.cache import InMemoryTTLCache
from app.services.weather.ecmwf_aifs_provider import ECMWFAIFSProvider
from app.services.weather.ecmwf_ifs_provider import ECMWFIFSProvider
from app.services.weather.forecast_provider import (
    ForecastProvider,
    ProviderDataError,
    ProviderUnavailableError,
)
from app.services.weather.gfs_provider import GFSProvider
from app.services.weather.graphcast_provider import GraphCastProvider
from app.services.weather.ncum_provider import NCUMProvider


class WeatherService:
    """Coordinates provider adapters; it does not score, blend, or alter forecasts."""

    def __init__(self, providers: list[ForecastProvider] | None = None) -> None:
        active_providers = providers or [
            ECMWFIFSProvider(),
            GFSProvider(),
            NCUMProvider(),
            ECMWFAIFSProvider(),
            GraphCastProvider(),
        ]
        self.providers = {provider.get_model_name().casefold(): provider for provider in active_providers}
        self.cache = InMemoryTTLCache()

    def list_models(self) -> list[ModelDescriptor]:
        return [provider.descriptor for provider in self.providers.values()]

    def list_locations(self) -> list[DemoLocation]:
        return [DemoLocation(**location) for location in DEMO_LOCATIONS]

    async def get_forecast(
        self, model: str, latitude: float, longitude: float, forecast_days: int
    ) -> ProviderForecast:
        provider = self.providers.get(model.casefold())
        if provider is None:
            available_models = ", ".join(item.get_model_name() for item in self.providers.values())
            raise KeyError(f"Unknown model '{model}'. Use one of: {available_models}")
        return await self._get_provider_forecast(provider, latitude, longitude, forecast_days)

    async def get_all_models(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> AllModelsForecastResponse:
        results = await asyncio.gather(
            *[
                self._get_provider_forecast(provider, latitude, longitude, forecast_days)
                for provider in self.providers.values()
            ]
        )
        return AllModelsForecastResponse(
            latitude=latitude,
            longitude=longitude,
            forecast_days=forecast_days,
            results=results,
        )

    async def _get_provider_forecast(
        self,
        provider: ForecastProvider,
        latitude: float,
        longitude: float,
        forecast_days: int,
    ) -> ProviderForecast:
        if provider.get_status() != "live":
            return ProviderForecast(
                model=provider.get_model_name(),
                model_type=provider.descriptor.model_type,
                provider=provider.descriptor.provider,
                status=provider.get_status(),
                source=provider.descriptor.source,
                error=provider.descriptor.note,
            )

        cache_key = (
            f"{provider.get_model_name()}:{latitude:.4f}:{longitude:.4f}:{forecast_days}"
        )
        try:
            forecast = await self.cache.get_or_set(
                cache_key,
                lambda: provider.get_forecast(latitude, longitude, forecast_days),
            )
            return forecast.model_copy(deep=True)
        except (ProviderDataError, ProviderUnavailableError, ValueError) as exc:
            return ProviderForecast(
                model=provider.get_model_name(),
                model_type=provider.descriptor.model_type,
                provider=provider.descriptor.provider,
                status="error",
                source=provider.descriptor.source,
                error=str(exc),
            )
        except Exception:
            # Do not expose implementation details or let one provider break the all-models call.
            return ProviderForecast(
                model=provider.get_model_name(),
                model_type=provider.descriptor.model_type,
                provider=provider.descriptor.provider,
                status="error",
                source=provider.descriptor.source,
                error="Provider request failed unexpectedly.",
            )


weather_service = WeatherService()
