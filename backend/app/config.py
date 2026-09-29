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

# Project metadata
PROJECT_INFO = {
    "project": "TrustCast",
    "problem_statement": "SIH26081",
    "title": "Hybrid AI–NWP Multi-Model Forecast Blending System",
    "team": "VisionCrafters",
    "stage": "foundation",
}
