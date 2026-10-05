"""TrustCast API routes: foundation, Step 2 ingestion, Step 3 performance, Step 4 trust, Step 5 blending, Step 6 uncertainty and Step 7 risk."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.services.geocoding_service import GeocodingError, geocoding_service
from app.services.location_service import LocationInput
from app.services.performance_service import performance_service
from app.services.risk_service import risk_service
from app.services.skill.dataset import DataUnavailableError
from app.services.skill.ensemble import ensemble_guidance
from app.services.skill import spatial
from app.services.skill.service import skill_service
from app.services.trust_engine import trust_engine
from app.services.uncertainty_service import uncertainty_service
from app.services.weather.forecast_provider import ProviderDataError
from app.services.weather.weather_service import weather_service

router = APIRouter(prefix="/api")


def selected_location(
    location: str = Query(default="Mumbai", min_length=1, description="Preset city name (used when no coordinates are given)"),
    latitude: float | None = Query(default=None, ge=-90, le=90, description="Selected point latitude (e.g. from /api/locations/search)"),
    longitude: float | None = Query(default=None, ge=-180, le=180, description="Selected point longitude"),
    name: str | None = Query(default=None, max_length=200, description="Display name for the selected point"),
) -> LocationInput:
    """Selected coordinates take priority and are used exactly; there is no fallback to a preset city."""
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Provide both latitude and longitude, or neither")
    if latitude is not None and longitude is not None:
        return {"name": name or f"{latitude:.4f}, {longitude:.4f}", "latitude": latitude, "longitude": longitude}
    return location


@router.get("/locations/search")
async def search_locations(q: str = Query(min_length=2, max_length=100, description="City, town or area name")):
    """Real location search in India via the free Open-Meteo Geocoding API (cached; no invented results)."""
    try:
        return {"query": q, "source": "Open-Meteo Geocoding API (GeoNames)", "results": await geocoding_service.search(q)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeocodingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
    location: LocationInput = Depends(selected_location),
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
    location: LocationInput = Depends(selected_location),
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
    location: LocationInput = Depends(selected_location),
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
    location: LocationInput = Depends(selected_location),
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
    location: LocationInput = Depends(selected_location),
    forecast_days: int = Query(default=2, ge=1, le=7),
    lead_day: int = Query(default=1, ge=1, le=2),
    days: int = Query(default=21, ge=7, le=30),
):
    """Step 7: forecast-based risk indicators (heavy rain, heat, cold, high wind); not official warnings."""
    try:
        return await risk_service.get_risks(location, forecast_days, lead_day, days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/skill")
async def forecast_skill(
    location: LocationInput = Depends(selected_location),
    variable: str = Query(default="temperature"),
    lead_day: int = Query(default=1, ge=1, le=2),
):
    """Walk-forward (out-of-sample) evaluation of TrustCast against the equal-weight mean, the best
    single model and each model, with bias-correction / adaptive-weighting gains, season and regime
    breakdowns and (for rain) 24 h event verification. First call per location downloads history."""
    try:
        return await skill_service.report(location, variable, lead_day)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DataUnavailableError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Historical data unavailable: {exc}") from exc


@router.get("/ensemble")
async def ensemble_extremes(
    location: LocationInput = Depends(selected_location),
    forecast_days: int = Query(default=2, ge=1, le=7),
):
    """NOAA AIGEFS ensemble exceedance probabilities for the risk thresholds (member counts from the
    latest real run; not verified or calibrated, because no archived AIGEFS forecasts exist)."""
    from app.services.location_service import resolve_location

    try:
        place = resolve_location(location)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return await ensemble_guidance(place["latitude"], place["longitude"], forecast_days)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AIGEFS ensemble unavailable: {exc}") from exc


SPATIAL_UNAVAILABLE = "Spatial results have not been precomputed yet. Run: python backend/scripts/spatial_precompute.py"


@router.get("/spatial/map")
async def spatial_map(variable: str = Query(default="temperature"), lead_day: int = Query(default=1, ge=1, le=2)):
    """Precomputed regional skill and adaptive weights per grid cell (read from disk; no live API calls)."""
    data = spatial.weights(variable, lead_day)
    return data if data is not None else {"status": "unavailable", "reason": SPATIAL_UNAVAILABLE, "cells": []}


@router.get("/spatial/risk")
async def spatial_risk():
    """Precomputed TrustCast risk indicator per grid cell (forecast-based; not an official warning)."""
    data = spatial.risk()
    return data if data is not None else {"status": "unavailable", "reason": SPATIAL_UNAVAILABLE, "cells": []}


@router.get("/spatial/cell")
async def spatial_cell(
    location: LocationInput = Depends(selected_location),
    variable: str = Query(default="temperature"),
    lead_day: int = Query(default=1, ge=1, le=2),
):
    """The grid cell that contains the selected point, with its regional weights, skill and risk."""
    from app.services.location_service import resolve_location

    try:
        place = resolve_location(location)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    grid = spatial.grid()
    cell = spatial.cell_for(place["latitude"], place["longitude"], grid["cells"] if grid else [])
    if cell is None:
        return {"status": "outside_grid", "location": place}
    weights = spatial.weights(variable, lead_day) or {}
    risk = spatial.risk() or {}
    return {
        "status": "ok", "location": place, "cell": cell,
        "weights": next((c for c in weights.get("cells", []) if c["id"] == cell["id"]), None),
        "risk": next((c for c in risk.get("cells", []) if c["id"] == cell["id"]), None),
        "generated_at": weights.get("generated_at"),
    }
