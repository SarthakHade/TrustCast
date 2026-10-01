"""Orchestration layer for Step 2 forecast-provider adapters."""

import asyncio
from datetime import UTC, datetime

from app.data.locations import DEMO_LOCATIONS
from app.schemas.weather import (
    AllModelsForecastResponse,
    DemoLocation,
    ModelDescriptor,
    ProviderForecast,
)
from app.services.weather.aicon_provider import AICONProvider
from app.services.weather.aigefs_provider import AIGEFSProvider
from app.services.weather.cache import InMemoryTTLCache
from app.services.weather.ecmwf_aifs_provider import ECMWFAIFSProvider
from app.services.weather.ecmwf_ifs_provider import ECMWFIFSProvider
from app.services.weather.forecast_provider import (
    ForecastProvider,
    ProviderDataError,
    ProviderUnavailableError,
    ProviderWaitingError,
)
from app.services.weather.gfs_provider import GFSProvider
from app.services.weather.graphcast_provider import GraphCastProvider, PanguProvider
from app.services.weather.icon_provider import ICONProvider
from app.services.weather.ncum_provider import NCUMProvider


class WeatherService:
    """Coordinates provider adapters; it does not score, blend, or alter forecasts."""

    def __init__(self, providers: list[ForecastProvider] | None = None) -> None:
        # Registry: core models first, then optional ones. Whether a model is LIVE is decided per
        # request from what its real source returns, never from this list.
        active_providers = providers or [
            ECMWFIFSProvider(),
            GFSProvider(),
            ECMWFAIFSProvider(),
            NCUMProvider(),
            AICONProvider(),
            AIGEFSProvider(),
            ICONProvider(),
            GraphCastProvider(),
            PanguProvider(),
        ]
        self.providers = {provider.get_model_name().casefold(): provider for provider in active_providers}
        self.cache = InMemoryTTLCache()
        self.probe_cache = InMemoryTTLCache()

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
        d = provider.descriptor

        def status_only(status: str, error: str | None, provenance: dict | None = None) -> ProviderForecast:
            return ProviderForecast(
                model=d.name, model_type=d.model_type, provider=d.provider, status=status,
                source=d.source, source_url=d.source_url, source_type=d.source_type,
                tier=d.tier, error=error, provenance=provenance or {},
                retrieved_at=datetime.now(UTC),
            )

        if provider.get_status() != "live":
            # Never fetch forecast values for non-live models. Real-but-not-ingestible sources
            # (NCUM-G, AICON) are probed so the UI can show what the official source publishes.
            provenance = None
            if provider.get_status() in ("unavailable", "waiting"):
                try:
                    provenance = await self.probe_cache.get_or_set(
                        f"probe:{d.name}", provider.probe, cache_if=lambda r: r is not None
                    )
                except Exception as exc:  # the official source itself could not be reached
                    provenance = {"official_source_reachable": False, "probe_error": type(exc).__name__}
            return status_only(provider.get_status(), d.note, provenance)

        cache_key = f"{d.name}:{latitude:.4f}:{longitude:.4f}:{forecast_days}"
        try:
            forecast = await self.cache.get_or_set(
                cache_key,
                lambda: provider.get_forecast(latitude, longitude, forecast_days),
            )
            return forecast.model_copy(deep=True)
        except ProviderWaitingError as exc:
            return status_only("waiting", str(exc))
        except (ProviderDataError, ProviderUnavailableError, ValueError) as exc:
            return status_only("error", str(exc))
        except Exception:
            # Do not expose implementation details or let one provider break the all-models call.
            return status_only("error", "Provider request failed unexpectedly.")


weather_service = WeatherService()
