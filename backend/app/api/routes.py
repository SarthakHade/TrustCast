"""TrustCast API routes: foundation, Step 2 ingestion, Step 3 performance, Step 4 trust, Step 5 blending, Step 6 uncertainty and Step 7 risk."""

import httpx
from fastapi import APIRouter, HTTPException, Query
from app.config import PROJECT_INFO
from app.schemas.blend import BlendResponse
from app.schemas.performance import PerformanceResponse
from app.schemas.risk import RiskResponse
from app.schemas.trust import TrustResponse
from app.schemas.uncertainty import UncertaintyResponse
from app.schemas.weather import (
    AllModelsForecastResponse,
    DemoLocation,
    ModelListResponse,
    ProviderForecast,
)
from app.services.blend_service import blend_service
from app.services.performance_service import performance_service
from app.services.risk_service import risk_service
from app.services.trust_engine import trust_engine
from app.services.uncertainty_service import uncertainty_service
from app.services.weather.forecast_provider import ProviderDataError
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


@router.get("/performance", response_model=PerformanceResponse)
async def model_performance(
    location: str = Query(default="Mumbai", min_length=1),
    variable: str = Query(default="temperature"),
    days: int = Query(default=21, ge=7, le=30),
    lead_day: int = Query(default=1, ge=1, le=2),
):
    """Score archived model forecasts against ERA5 reanalysis (MAE, RMSE, bias, skill)."""
    try:
        return await performance_service.evaluate(location, variable, days, lead_day)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProviderDataError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Historical data source unavailable: {exc}"
        ) from exc


@router.get("/trust", response_model=TrustResponse)
async def model_trust(
    location: str = Query(default="Mumbai", min_length=1),
    variable: str = Query(default="temperature"),
    days: int = Query(default=21, ge=7, le=30),
    lead_day: int = Query(default=1, ge=1, le=2),
):
    """Step 4 Trust Engine: deterministic, explainable model weights from Step 3 metrics."""
    try:
        return await trust_engine.get_trust(location, variable, days, lead_day)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProviderDataError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Historical data source unavailable: {exc}"
        ) from exc


@router.get("/blend", response_model=BlendResponse)
async def blended_forecast(
    location: str = Query(default="Mumbai", min_length=1),
    variable: str = Query(default="temperature"),
    forecast_days: int = Query(default=2, ge=1, le=7),
    lead_day: int = Query(default=1, ge=1, le=2),
    days: int = Query(default=21, ge=7, le=30),
):
    """Step 5: blend live Step 2 forecasts with Step 4 trust weights, aligned by valid_time."""
    try:
        return await blend_service.get_blend(location, variable, forecast_days, lead_day, days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProviderDataError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Trust weights unavailable, cannot blend: {exc}"
        ) from exc


@router.get("/uncertainty", response_model=UncertaintyResponse)
async def forecast_uncertainty(
    location: str = Query(default="Mumbai", min_length=1),
    variable: str = Query(default="temperature"),
    forecast_days: int = Query(default=2, ge=1, le=7),
    lead_day: int = Query(default=1, ge=1, le=2),
    days: int = Query(default=21, ge=7, le=30),
):
    """Step 6: model disagreement + TrustCast historical error range around the Step 5 blend."""
    try:
        return await uncertainty_service.get_uncertainty(
            location, variable, forecast_days, lead_day, days
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ProviderDataError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Trust weights unavailable, cannot estimate uncertainty: {exc}"
        ) from exc


@router.get("/risks", response_model=RiskResponse)
async def forecast_risks(
    location: str = Query(default="Mumbai", min_length=1),
    forecast_days: int = Query(default=2, ge=1, le=7),
    lead_day: int = Query(default=1, ge=1, le=2),
    days: int = Query(default=21, ge=7, le=30),
):
    """Step 7: forecast-based risk indicators (heavy rain, heat, cold, high wind); not official warnings."""
    try:
        return await risk_service.get_risks(location, forecast_days, lead_day, days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
