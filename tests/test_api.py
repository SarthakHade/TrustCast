"""
TrustCast Backend Tests

Tests for foundation API endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test GET /api/health returns ok status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "trustcast-backend"


@pytest.mark.asyncio
async def test_info_endpoint():
    """Test GET /api/info returns project metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/info")

    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "TrustCast"
    assert data["problem_statement"] == "SIH26081"
    assert data["title"] == "Hybrid AI–NWP Multi-Model Forecast Blending System"
    assert data["team"] == "VisionCrafters"
    assert data["stage"] == "foundation"
