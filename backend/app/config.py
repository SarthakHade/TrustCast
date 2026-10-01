"""
TrustCast Backend Configuration

Loads settings from environment variables with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Server
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# CORS - allow frontend dev server
FRONTEND_PORT = os.getenv("FRONTEND_PORT", "5173")
CORS_ORIGINS = [
    f"http://localhost:{FRONTEND_PORT}",
    f"http://127.0.0.1:{FRONTEND_PORT}",
]

# Step 2 weather ingestion (no key required for the selected public source)
OPEN_METEO_SINGLE_RUNS_URL = os.getenv(
    "OPEN_METEO_SINGLE_RUNS_URL", "https://single-runs-api.open-meteo.com/v1/forecast"
)
WEATHER_CACHE_TTL_SECONDS = int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "600"))
# NOAA AIGEFS (AI ensemble) via the Open-Meteo Ensemble API + its run metadata
OPEN_METEO_ENSEMBLE_URL = os.getenv("OPEN_METEO_ENSEMBLE_URL", "https://ensemble-api.open-meteo.com/v1/ensemble")
OPEN_METEO_ENSEMBLE_META_URL = os.getenv(
    "OPEN_METEO_ENSEMBLE_META_URL", "https://ensemble-api.open-meteo.com/data/{model}/static/meta.json"
)
# Official sources checked for models that cannot be ingested as point data yet
DWD_AICON_RUNS_URL = os.getenv("DWD_AICON_RUNS_URL", "https://opendata.dwd.de/weather/nwp/v1/m/aicon/p/T_2M/r/")
NCMRWF_API_URL = os.getenv("NCMRWF_API_URL", "https://nwp.ncmrwf.gov.in/apis/api/v1")

# Step 3 historical verification: archived forecasts vs ERA5 reanalysis (no key required)
OPEN_METEO_PREVIOUS_RUNS_URL = os.getenv(
    "OPEN_METEO_PREVIOUS_RUNS_URL", "https://previous-runs-api.open-meteo.com/v1/forecast"
)
OPEN_METEO_ARCHIVE_URL = os.getenv(
    "OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive"
)
PERFORMANCE_CACHE_TTL_SECONDS = int(os.getenv("PERFORMANCE_CACHE_TTL_SECONDS", "21600"))

# Project metadata
PROJECT_INFO = {
    "project": "TrustCast",
    "problem_statement": "SIH26081",
    "title": "Hybrid AI–NWP Multi-Model Forecast Blending System",
    "team": "VisionCrafters",
    "stage": "risk_detection",
}
