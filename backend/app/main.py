"""
TrustCast Backend - Main Application

FastAPI application with CORS enabled for frontend communication.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.api.routes import router

app = FastAPI(
    title="TrustCast API",
    description="Hybrid AI–NWP Multi-Model Forecast Blending System",
    version="0.1.0",
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "TrustCast API is running"}
