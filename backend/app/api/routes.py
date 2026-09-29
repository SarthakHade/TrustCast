"""TrustCast API routes for the foundation and Step 2 ingestion layer."""

from fastapi import APIRouter, HTTPException, Query
from app.config import PROJECT_INFO
from app.schemas.weather import (
    AllModelsForecastResponse,
    DemoLocation,
    ModelListResponse,
    ProviderForecast,
)
from app.services.weather.weather_service import weather_service

router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "trustcast-backend"}


@router.get("/info")
async def project_info():
    """Return project metadata."""
    return PROJECT_INFO


@router.get("/weather/models", response_model=ModelListResponse)
async def weather_models():
    """List all planned model adapters and their current integration status."""
    return ModelListResponse(models=weather_service.list_models())


@router.get("/weather/locations", response_model=list[DemoLocation])
async def weather_locations():
    """Return the centrally configured Step 2 demo locations."""
    return weather_service.list_locations()


@router.get("/weather/forecast", response_model=ProviderForecast)
async def weather_forecast(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    model: str = Query(min_length=1),
    forecast_days: int = Query(default=2, ge=1, le=7),
):
    """Fetch normalized data for one selected forecast model."""
    try:
        return await weather_service.get_forecast(model, latitude, longitude, forecast_days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/weather/all-models", response_model=AllModelsForecastResponse)
async def weather_all_models(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    forecast_days: int = Query(default=2, ge=1, le=7),
):
    """Fetch every configured provider while isolating individual provider failures."""
    return await weather_service.get_all_models(latitude, longitude, forecast_days)
