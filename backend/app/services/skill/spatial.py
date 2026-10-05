"""Spatial grid store: reads the precomputed regional weights / skill / risk produced offline by
backend/scripts/spatial_precompute.py, looks up the cell for a coordinate, and pools regime weights
across cells for the live hierarchy. The browser only ever reads these prepared files.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import SPATIAL_DATA_DIR
from app.services.skill.stats import check_weights, stacking_weights
from app.services.skill.walkforward import DEFAULT_RIDGE, MIN_REGIME_HOURS

_cache: dict[str, tuple[float, float, Any]] = {}  # path -> (mtime, read time, data)


def _read(name: str) -> Any | None:
    path = Path(SPATIAL_DATA_DIR) / name
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _cache[str(path)] = (mtime, time.monotonic(), data)
    return data


def grid() -> dict | None:
    return _read("grid_cells.json")


def weights(variable: str, lead_day: int) -> dict | None:
    return _read(f"weights_{variable}_d{lead_day}.json")


def risk() -> dict | None:
    return _read("risk_latest.json")


def cell_for(latitude: float, longitude: float, cells: list[dict]) -> dict | None:
    """The grid cell containing the point; if none (point outside the grid), the nearest centre within one cell."""
    for c in cells:
        if c["south"] <= latitude < c["north"] and c["west"] <= longitude < c["east"]:
            return c
    if not cells:
        return None
    best = min(cells, key=lambda c: (c["latitude"] - latitude) ** 2 + (c["longitude"] - longitude) ** 2)
    size = best["north"] - best["south"]
    if abs(best["latitude"] - latitude) <= size and abs(best["longitude"] - longitude) <= size:
        return best
    return None


def pooled_weights(moments: list[dict[str, tuple[list[list[float]], int]]], models: list[str]) -> dict[str, dict]:
    """Regime-wise regional weights: sample-weighted mean of per-cell bias-corrected error moments,
    then the same constrained ridge stacking. Regimes with too few pooled hours are omitted."""
    out = {}
    keys = {k for m in moments for k in m}
    k = len(models)
    for key in sorted(keys):
        total = 0
        acc = [[0.0] * k for _ in range(k)]
        cells = 0
        for m in moments:
            if key not in m:
                continue
            c, n = m[key]
            if not n:
                continue
            cells += 1
            total += n
            for i in range(k):
                for j in range(k):
                    acc[i][j] += c[i][j] * n
        if total < MIN_REGIME_HOURS:
            continue
        w = stacking_weights([[v / total for v in row] for row in acc], DEFAULT_RIDGE)
        if w is None:
            continue
        check_weights(w, f"pooled {key}")
        out[key] = {"weights": dict(zip(models, w)), "hours": total, "cells": cells}
    return out
