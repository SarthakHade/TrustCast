"""Offline / scheduled spatial precomputation for TrustCast (run daily, e.g. from cron or Task Scheduler):

    python backend/scripts/spatial_precompute.py            # full run (~10 minutes, rate limited)
    python backend/scripts/spatial_precompute.py --limit 10 # quick partial run for testing

Pipeline per grid cell (real data only):
    historical archive + ERA5 (last SPATIAL_DAYS days)  ->  walk-forward verification
    -> bias correction + constrained stacking (live weights, Day 1 / Day 2)  ->  regional skill
    -> pooled regime weights across cells  ->  current forecasts  ->  TrustCast risk per cell

Outputs (read by the API; the browser never calls Open-Meteo for the map):
    backend/data/spatial/weights_<variable>_d<lead>.json
    backend/data/spatial/risk_latest.json
    backend/data/spatial/manifest.json

Rate limiting: 20 cells per request, one request at a time, >= 10 s apart, exponential backoff on
HTTP 429/5xx, and every downloaded batch is cached so an interrupted run resumes without
re-downloading. Cells whose data cannot be downloaded are written as unavailable, never filled in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

from app.config import OPEN_METEO_FORECAST_URL, SKILL_CACHE_DIR, SPATIAL_DATA_DIR  # noqa: E402
from app.data.risk_thresholds import RISK_RULES  # noqa: E402
from app.services.risk_service import Sample, accumulate_24h, assess  # noqa: E402
from app.services.skill import dataset as ds  # noqa: E402
from app.services.skill.regime import REGIME_LABEL, SEASON_LABEL, classify_day, season_of  # noqa: E402
from app.services.skill.spatial import pooled_weights  # noqa: E402
from app.services.skill.walkforward import WalkForward, summarise  # noqa: E402

SPATIAL_DAYS = 56
BATCH = 20
MIN_INTERVAL_S = 10.0
MIN_SKILL_HOURS = 72
BALANCED_MARGIN = 0.05  # top weight must beat the runner-up by this much to call a model dominant
VARIABLES = {"temperature": "°C", "precipitation": "mm/h", "wind_speed": "km/h"}
MODELS = [
    ds.ModelSource("ECMWF IFS", "ecmwf_ifs025"),
    ds.ModelSource("NOAA GFS", "gfs_global"),
    ds.ModelSource("ECMWF AIFS", "ecmwf_aifs025_single"),
    ds.ModelSource("DWD ICON", "icon_global"),
]
LEVEL_ORDER = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


async def download(cells: list[dict], today: date, client: ds.RateLimitedClient, cache: Path) -> tuple[list[dict | None], list[dict | None]]:
    """Historical raw data and current forecasts per cell (None where a batch failed)."""
    start, end = today - timedelta(days=SPATIAL_DAYS), today - timedelta(days=1)
    history: list[dict | None] = [None] * len(cells)
    current: list[dict | None] = [None] * len(cells)
    cache.mkdir(parents=True, exist_ok=True)
    fields = ["temperature_2m", "precipitation", "wind_speed_10m", "relative_humidity_2m"]
    async with httpx.AsyncClient(timeout=120.0) as http:
        for b0 in range(0, len(cells), BATCH):
            batch = cells[b0:b0 + BATCH]
            tag = f"{today}_{batch[0]['id']}_{len(batch)}"
            hist_file, fc_file = cache / f"hist_{tag}.json", cache / f"fc_{tag}.json"
            try:
                if hist_file.exists():
                    raw = json.loads(hist_file.read_text())
                else:
                    raw = await ds.fetch_raw(batch, MODELS, start, end, client)
                    hist_file.write_text(json.dumps(raw))
                for i, r in enumerate(raw):
                    history[b0 + i] = r
            except Exception as exc:  # leave this batch unavailable
                log(f"history batch {b0} failed: {exc}")
            try:
                if fc_file.exists():
                    fc = json.loads(fc_file.read_text())
                else:
                    payload = await client.get_json(http, OPEN_METEO_FORECAST_URL, {
                        "latitude": ",".join(f"{c['latitude']:.4f}" for c in batch),
                        "longitude": ",".join(f"{c['longitude']:.4f}" for c in batch),
                        "hourly": ",".join(fields), "models": ",".join(m.om_model for m in MODELS),
                        "forecast_days": 3, "timezone": "GMT", **ds.UNITS,
                    })
                    fc = payload if isinstance(payload, list) else [payload]
                    fc_file.write_text(json.dumps(fc))
                for i, block in enumerate(fc):
                    current[b0 + i] = block
            except Exception as exc:
                log(f"forecast batch {b0} failed: {exc}")
            log(f"downloaded cells {b0}–{b0 + len(batch) - 1} (requests {client.requests}, retries {client.retries})")
    return history, current


def dominant(weights: dict[str, float]) -> str:
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < BALANCED_MARGIN:
        return "Balanced"
    return ranked[0][0]


def parse_current(block: dict) -> dict[str, dict[str, dict[datetime, float]]]:
    """model -> variable -> time -> value from a multi-model Open-Meteo forecast response."""
    hourly = block.get("hourly") or {}
    times = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in hourly.get("time", [])]
    names = {"temperature_2m": "temperature", "precipitation": "precipitation", "wind_speed_10m": "wind_speed", "relative_humidity_2m": "humidity"}
    out: dict[str, dict[str, dict[datetime, float]]] = {}
    for m in MODELS:
        for om, var in names.items():
            values = hourly.get(f"{om}_{m.om_model}") or []
            for t, v in zip(times, values):
                if v is not None and ds.plausible(var, v):
                    out.setdefault(m.name, {}).setdefault(var, {})[t] = float(v)
    return out


def forecast_regimes(current: dict) -> dict[date, str]:
    per_day: dict[date, dict[str, dict[int, list[float]]]] = {}
    for fields in current.values():
        for var, series in fields.items():
            for t, v in series.items():
                per_day.setdefault(t.date(), {}).setdefault(var, {}).setdefault(t.hour, []).append(v)
    out = {}
    for d, fields in per_day.items():
        mean = {v: [sum(x) / len(x) for x in hours.values()] for v, hours in fields.items()}
        out[d] = classify_day(d, mean.get("temperature", []), mean.get("precipitation", []), mean.get("wind_speed", []), mean.get("humidity", []))
    return out


def cell_risk(current: dict, fits: dict, now: datetime, regimes: dict[date, str]) -> dict:
    """Apply each variable's live fits to the current forecasts and run the TrustCast risk rules."""
    names = [m.name for m in MODELS]
    hour = now.replace(minute=0, second=0, microsecond=0)
    samples_by_var: dict[str, list[Sample]] = {}
    for variable in VARIABLES:
        clip = variable in ("precipitation", "wind_speed")
        times = sorted({t for m in names for t in current.get(m, {}).get(variable, {}) if t >= hour})
        samples = []
        for t in times:
            lead = 1 if t - now < timedelta(hours=48) else 2
            fit = fits.get((variable, lead, regimes.get(t.date(), "UNKNOWN"))) or fits.get((variable, lead, "NORMAL"))
            if not fit:
                continue
            corrected = {}
            for k, m in enumerate(names):
                v = current.get(m, {}).get(variable, {}).get(t)
                if v is not None:
                    corrected[m] = fit["bias"].apply(k, t.hour, v, clip)
            usable = {m: fit["weights"][m] for m in corrected if fit["weights"].get(m, 0) > 0}
            total = sum(usable.values())
            if total <= 0:
                continue
            value = sum(w * corrected[m] for m, w in usable.items()) / total
            samples.append(Sample(t, value, min(corrected.values()), max(corrected.values()), "model range", corrected))
        samples_by_var[variable] = samples
    out = {}
    for rule in RISK_RULES:
        data = samples_by_var.get(rule.variable) or []
        indicator = assess(rule, accumulate_24h(data) if rule.aggregation == "sum_24h" else data)
        out[rule.risk_type] = {
            "level": indicator.level, "status": indicator.status,
            "value": indicator.forecast_value, "unit": rule.unit, "peak_time": indicator.peak_time.isoformat() if indicator.peak_time else None,
            "models_exceeding": indicator.models_exceeding, "models_total": indicator.models_total,
        }
    return out


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="only the first N cells (testing)")
    args = parser.parse_args()
    started = time.time()
    now = datetime.now(UTC)
    today = now.date()
    out_dir = Path(SPATIAL_DATA_DIR)
    grid = json.loads((out_dir / "grid_cells.json").read_text())
    cells = grid["cells"][: args.limit or None]
    log(f"{len(cells)} cells, {SPATIAL_DAYS} days of history")
    client = ds.RateLimitedClient(concurrency=1, min_interval_s=MIN_INTERVAL_S)
    history, current_raw = await download(cells, today, client, Path(SKILL_CACHE_DIR) / "spatial")

    names = [m.name for m in MODELS]
    results = {(v, lead): [] for v in VARIABLES for lead in ds.LEAD_DAYS}
    moments = {(v, lead): [] for v in VARIABLES for lead in ds.LEAD_DAYS}
    risk_cells = []
    for idx, cell in enumerate(cells):
        base = {k: cell[k] for k in ("id", "latitude", "longitude", "south", "north", "west", "east", "land_fraction")}
        raw, cur = history[idx], current_raw[idx]
        if raw is None:
            for key in results:
                results[key].append(base | {"status": "unavailable", "reason": "history download failed"})
            risk_cells.append(base | {"status": "unavailable"})
            continue
        data = ds.to_dataset(raw, names)
        current = parse_current(cur) if cur else {}
        regimes = forecast_regimes(current) if current else {}
        wanted = sorted(set(regimes.values()) | {"NORMAL"})
        fits = {}
        for variable in VARIABLES:
            for lead in ds.LEAD_DAYS:
                wf = WalkForward(data, variable, lead)
                target = today + timedelta(days=lead)
                res = wf.run(extra_targets=[(target, r) for r in wanted])
                rep = summarise(res, names, variable)
                live = res["live"].get((target, regimes.get(target, "NORMAL"))) or res["live"].get((target, "NORMAL"))
                for (t, regime), f in res["live"].items():
                    if f.get("status") == "ok":
                        fits[(variable, lead, regime)] = f
                m = rep["metrics"]
                enough = rep["common_hours"] >= MIN_SKILL_HOURS
                record = base | {
                    "status": "ok" if live and live.get("status") == "ok" else "insufficient_data",
                    "evaluation_days": rep["evaluation_days"], "common_hours": rep["common_hours"],
                    "period_start": rep["period_start"], "period_end": rep["period_end"],
                    "skill": {
                        "trustcast_rmse": m["trustcast"]["rmse"], "equal_rmse": m["equal"]["rmse"], "best_single_rmse": m["best_single"]["rmse"],
                        "skill_vs_equal": m["trustcast"]["skill_vs_equal"] if enough else None,
                        "skill_vs_best_single": m["trustcast"]["skill_vs_best_single"] if enough else None,
                        "model_rmse": {n: m[f"model:{n}"]["rmse"] for n in names},
                    },
                    "regime": regimes.get(target, "UNKNOWN"), "season": season_of(target),
                    "coverage": {"observed_hours": len(data.observed.get(variable, {})), "missing_values": data.quality.get("missing_values", 0)},
                }
                if live and live.get("status") == "ok":
                    w = live["weights"]
                    record["live"] = {
                        "variant": live["variant"], "level": live["level"], "weights": w,
                        "dominant": dominant(w), "training_end": live["training_end"],
                        "bias_correction": live["bias"].summary(names),
                    }
                    moments[(variable, lead)].append(wf.regime_moments(date.fromisoformat(live["training_end"])))
                results[(variable, lead)].append(record)
        risk_cells.append(base | ({"status": "ok", "risks": cell_risk(current, fits, now, regimes)} if current else {"status": "unavailable"}))
        if idx % 20 == 0:
            log(f"computed cell {idx + 1}/{len(cells)}")

    generated = datetime.now(UTC).isoformat(timespec="seconds")
    common = {"generated_at": generated, "resolution_deg": grid["resolution_deg"], "history_days": SPATIAL_DAYS,
              "mask_source": grid["mask_source"], "models": names,
              "reference": "ERA5 (Open-Meteo Historical Weather API)", "forecasts": "Open-Meteo Previous Runs + Forecast APIs"}
    for (variable, lead), cells_out in results.items():
        pooled = pooled_weights(moments[(variable, lead)], names)
        (out_dir / f"weights_{variable}_d{lead}.json").write_text(json.dumps(common | {
            "variable": variable, "unit": VARIABLES[variable], "lead_day": lead,
            "pooled": {k: v | {"label": REGIME_LABEL.get(k, "All regimes")} for k, v in pooled.items()},
            "cells": cells_out,
        }), encoding="utf-8")
    (out_dir / "risk_latest.json").write_text(json.dumps(common | {
        "issued_at": now.isoformat(timespec="seconds"), "horizon_hours": 72,
        "note": "TrustCast forecast-based risk indicator per grid cell — not an official warning.",
        "season": SEASON_LABEL[season_of(today)], "cells": risk_cells,
    }), encoding="utf-8")
    manifest = common | {"cells": len(cells), "ok_cells": sum(r is not None for r in history),
                         "requests": client.requests, "retries": client.retries, "duration_s": round(time.time() - started)}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"done: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
