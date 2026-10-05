"""Spatial grid lookup, regional pooling + fallback hierarchy, adaptive blend application and AIGEFS
ensemble exceedance. TEST FIXTURES only (no network)."""

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.services.blend_service import adaptive_blend
from app.services.skill import service as skill_service_module
from app.services.skill import spatial
from app.services.skill.ensemble import guidance_from_payload
from app.services.skill.stats import check_weights
from app.services.skill.walkforward import BiasParams, MIN_REGIME_HOURS

CELLS = [
    {"id": "a", "latitude": 18.75, "longitude": 72.75, "south": 18.0, "north": 19.5, "west": 72.0, "east": 73.5},
    {"id": "b", "latitude": 17.25, "longitude": 74.25, "south": 16.5, "north": 18.0, "west": 73.5, "east": 75.0},
]


# ---------------------------------------------------------------- J spatial cell lookup

def test_point_maps_to_the_cell_that_contains_it_not_a_preset_city():
    assert spatial.cell_for(19.076, 72.8777, CELLS)["id"] == "a"       # Mumbai
    assert spatial.cell_for(16.69117, 74.46054, CELLS)["id"] == "b"    # Ichalkaranji: its own cell
    assert spatial.cell_for(18.9, 72.5, CELLS)["id"] == "a"            # same cell, shared regional weights
    assert spatial.cell_for(19.6, 72.8, CELLS)["id"] == "a"            # just outside: nearest within one cell
    assert spatial.cell_for(30.0, 90.0, CELLS) is None                 # far away: no substitute


def test_committed_grid_is_valid():
    grid = spatial.grid()
    assert grid and grid["resolution_deg"] == 1.5 and len(grid["cells"]) > 100
    ids = [c["id"] for c in grid["cells"]]
    assert len(ids) == len(set(ids))
    assert all(c["north"] - c["south"] == pytest.approx(1.5) for c in grid["cells"])


# ---------------------------------------------------------------- K pooled spatial weights

def test_pooled_weights_are_valid_and_skip_sparse_regimes():
    c1 = [[1.0, 0.2], [0.2, 4.0]]
    c2 = [[2.0, 0.1], [0.1, 3.0]]
    pooled = spatial.pooled_weights([{"ALL": (c1, 200), "HEATWAVE": (c1, 10)}, {"ALL": (c2, 100)}], ["X", "Y"])
    assert set(pooled) == {"ALL"}  # 10 h of heatwave < MIN_REGIME_HOURS
    check_weights(pooled["ALL"]["weights"])
    assert pooled["ALL"]["weights"]["X"] > pooled["ALL"]["weights"]["Y"]
    assert pooled["ALL"]["hours"] == 300 and pooled["ALL"]["cells"] == 2
    assert MIN_REGIME_HOURS > 10


def _load_script():
    path = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "spatial_precompute.py"
    spec = importlib.util.spec_from_file_location("spatial_precompute", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["spatial_precompute"] = module
    spec.loader.exec_module(module)
    return module


def test_dominant_model_requires_a_clear_margin():
    script = _load_script()
    assert script.dominant({"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}) == "A"
    assert script.dominant({"A": 0.26, "B": 0.25, "C": 0.25, "D": 0.24}) == "Balanced"


def test_regional_pool_fills_the_regime_fallback_and_the_stacking_fallback(monkeypatch):
    pooled = {"HEATWAVE": {"weights": {"A": 0.7, "B": 0.3}, "hours": 500, "cells": 12},
              "ALL": {"weights": {"A": 0.5, "B": 0.5}, "hours": 9000, "cells": 160}}
    monkeypatch.setattr(spatial, "weights", lambda variable, lead: {"pooled": pooled})
    block = {"fits": {
        "HEATWAVE": {"variant": "bc_regime", "level": "location (only 0 h of heatwave history)", "weights": {"A": 0.5, "B": 0.5}, "samples": 10},
        "NORMAL": {"variant": "bc_stack", "level": "fallback: previous TrustCast weights", "weights": {"A": 0.9, "B": 0.1}, "samples": 0},
        "ACTIVE_MONSOON": {"variant": "bc_stack", "level": "location", "weights": {"A": 0.2, "B": 0.8}, "samples": 500},
    }}
    skill_service_module.apply_regional_pool(block, "temperature", 1)
    assert block["fits"]["HEATWAVE"]["weights"] == {"A": 0.7, "B": 0.3}
    assert block["fits"]["HEATWAVE"]["level"].startswith("regime (regional pool")
    assert block["fits"]["NORMAL"]["level"].startswith("regional pool (all regimes")
    assert block["fits"]["ACTIVE_MONSOON"]["weights"] == {"A": 0.2, "B": 0.8}  # location level kept


# ---------------------------------------------------------------- adaptive blend application

def test_adaptive_blend_applies_bias_and_weights_and_renormalises():
    issued = datetime(2026, 10, 5, 0, tzinfo=UTC)
    t1, t2 = issued + timedelta(hours=3), issued + timedelta(hours=60)
    bias = BiasParams("additive", hod=[[1.0, -1.0] for _ in range(24)], mode="hour-of-day")
    fit = {"weights": {"A": 0.75, "B": 0.25}, "bias": bias}
    live = {"leads": {1: {"fits": {"NORMAL": fit}, "models": ["A", "B"]}, 2: {"fits": {"NORMAL": fit}, "models": ["A", "B"]}}}
    series = {"A": {t1: 31.0, t2: 30.0}, "B": {t1: 27.0, t2: None}}
    points = adaptive_blend(series, live, {}, "temperature", {"A": 0.5, "B": 0.5}, issued)
    p1, p2 = points
    assert p1.corrected == {"A": 30.0, "B": 28.0}
    assert p1.blended_value == pytest.approx(0.75 * 30 + 0.25 * 28)
    assert p1.lead_day == 1 and p2.lead_day == 2
    assert p2.blended_value == pytest.approx(29.0) and p2.renormalized and p2.effective_weights == {"A": 1.0}


# ---------------------------------------------------------------- N AIGEFS exceedance

def _ensemble_payload(init: datetime, totals: list[float], members: int = 31):
    """TEST FIXTURE: each member's 24 h total spread evenly over 24 hourly values after the run."""
    times = [init + timedelta(hours=h) for h in range(0, 49)]
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for m in range(members):
        key = "precipitation" if m == 0 else f"precipitation_member{m:02d}"
        hourly[key] = [0.0] + [totals[m] / 24] * 24 + [0.0] * 24
        tkey = "temperature_2m" if m == 0 else f"temperature_2m_member{m:02d}"
        hourly[tkey] = [30.0 + (m % 12) for _ in times]
        wkey = "wind_speed_10m" if m == 0 else f"wind_speed_10m_member{m:02d}"
        hourly[wkey] = [10.0 for _ in times]
    return {"last_run_initialisation_time": int(init.timestamp())}, {"hourly": hourly}


def test_ensemble_exceedance_counts_real_members():
    init = datetime(2026, 10, 5, 0, tzinfo=UTC)
    totals = [100.0] * 18 + [10.0] * 13  # 18 of 31 members exceed 64.5 mm, none exceed 115.6 mm
    meta, payload = _ensemble_payload(init, totals)
    out = guidance_from_payload(meta, payload, init + timedelta(hours=6))
    rain = out["risks"]["HEAVY_RAIN"]
    elevated, high = rain["thresholds"]
    assert (elevated["members_exceeding"], elevated["members_valid"]) == (18, 31)
    assert elevated["probability"] == pytest.approx(18 / 31)
    assert high["members_exceeding"] == 0
    assert rain["member_percentiles"]["p50"] == pytest.approx(100.0)
    heat = out["risks"]["HEAT"]["thresholds"][0]  # members 30..41 °C at native steps; >= 35 °C: m%12 >= 5
    assert heat["members_exceeding"] == sum(1 for m in range(31) if 30 + m % 12 >= 35)
    assert out["verification"].startswith("unavailable")


def test_stale_run_or_too_few_members_is_unavailable():
    init = datetime(2026, 10, 1, 0, tzinfo=UTC)
    meta, payload = _ensemble_payload(init, [10.0] * 31)
    assert guidance_from_payload(meta, payload, init + timedelta(hours=48))["status"] == "unavailable"
    meta, payload = _ensemble_payload(init, [10.0] * 5, members=5)
    out = guidance_from_payload(meta, payload, init + timedelta(hours=6))
    assert out["risks"]["HEAVY_RAIN"]["status"] == "unavailable"


def test_missing_member_values_are_not_counted():
    init = datetime(2026, 10, 5, 0, tzinfo=UTC)
    meta, payload = _ensemble_payload(init, [100.0] * 31)
    payload["hourly"]["precipitation_member03"][5] = None  # one member incomplete in the first window
    rain = guidance_from_payload(meta, payload, init + timedelta(hours=6))["risks"]["HEAVY_RAIN"]
    assert rain["thresholds"][0]["members_valid"] in (30, 31)
    first_window_members = 30 if rain["valid_time"] == (init + timedelta(hours=24)).isoformat() else 31
    assert rain["thresholds"][0]["members_valid"] == first_window_members
    assert date.fromisoformat(rain["valid_time"][:10]) >= init.date()
