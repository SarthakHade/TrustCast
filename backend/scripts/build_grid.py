"""Build the coarse India computation grid (run once; output is committed).

    python backend/scripts/build_grid.py [--resolution 1.5]

Cells are selected with Natural Earth country polygons (public domain, via the `world-atlas`
TopoJSON package). This is a computational mask only: TrustCast draws grid cells, not national
boundaries. Natural Earth depicts de facto boundaries, so cells in some areas may be absent; an
official product should use the Survey of India boundary instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

SOURCE = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"
INDIA_ID = "356"
BBOX = (6.0, 38.0, 67.0, 98.0)  # lat min, lat max, lon min, lon max
SAMPLES = 5                      # 5 x 5 test points per cell
OUT = Path(__file__).resolve().parents[1] / "data" / "spatial" / "grid_cells.json"


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def rings_for(geometry: dict, arcs: list) -> list[list[tuple[float, float]]]:
    def ring(indices):
        pts: list[tuple[float, float]] = []
        for i in indices:
            seg = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
            pts.extend(seg if not pts else seg[1:])
        return pts

    polys = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]]
    return [ring(r) for poly in polys for r in poly]


def inside(lon: float, lat: float, rings) -> bool:
    """Even-odd ray casting over all rings (holes handled)."""
    hit = False
    for pts in rings:
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolution", type=float, default=1.5)
    args = parser.parse_args()
    res = args.resolution
    topo = httpx.get(SOURCE, timeout=60).json()
    arcs = decode_arcs(topo)
    geom = next(g for g in topo["objects"]["countries"]["geometries"] if str(g.get("id")) == INDIA_ID)
    rings = rings_for(geom, arcs)
    cells = []
    lat0, lat1, lon0, lon1 = BBOX
    nlat, nlon = int((lat1 - lat0) / res), int((lon1 - lon0) / res)
    for i in range(nlat):
        for j in range(nlon):
            s, w = lat0 + i * res, lon0 + j * res
            pts = [(w + (a + 0.5) * res / SAMPLES, s + (b + 0.5) * res / SAMPLES) for a in range(SAMPLES) for b in range(SAMPLES)]
            frac = sum(inside(x, y, rings) for x, y in pts) / len(pts)
            if frac > 0:
                cells.append({
                    "id": f"{s + res / 2:.2f}_{w + res / 2:.2f}",
                    "latitude": round(s + res / 2, 4), "longitude": round(w + res / 2, 4),
                    "south": round(s, 4), "north": round(s + res, 4), "west": round(w, 4), "east": round(w + res, 4),
                    "land_fraction": round(frac, 2),
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "resolution_deg": res, "bbox": BBOX, "cells": cells,
        "mask_source": "Natural Earth 1:50m countries (public domain) via world-atlas@2; computational mask, not a boundary depiction",
    }, indent=1), encoding="utf-8")
    print(f"{len(cells)} cells at {res}° written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
