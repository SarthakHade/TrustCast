# TrustCast

**Hybrid AI–NWP Multi-Model Forecast Blending System**

> Problem Statement: **SIH26081** | Team: **VisionCrafters** | Smart India Hackathon 2026

---

## 1. Project Overview

TrustCast is a hybrid system that blends forecasts from multiple Numerical Weather Prediction (NWP) models using AI-driven trust scoring. The system dynamically weights each model based on historical performance, producing more accurate and reliable weather forecasts with quantified uncertainty.

## 2. Current Architecture (Step 7 - Risk Indicators)

```
trustcast/
├── frontend/          # React + Vite + TypeScript + Tailwind CSS
├── backend/           # FastAPI + Python
│   └── app/
│       ├── main.py    # Application entry point
│       ├── config.py  # Environment configuration
│       ├── api/       # API route handlers
│       ├── schemas/   # Pydantic API and normalized forecast models
│       ├── services/  # Weather provider adapters and cache
│       └── utils/     # Helper functions (future)
├── ml/                # ML pipeline modules (future)
├── data/              # Raw and processed data
├── tests/             # Backend tests
├── docs/              # Documentation
├── .env.example       # Environment variable template
└── .gitignore
```

## 3. Frontend Setup

```bash
cd trustcast/frontend
npm install
npm run dev
```

Frontend runs at: **http://localhost:5173**

## 4. Backend Setup

```bash
cd trustcast
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Backend runs at: **http://localhost:8000**

API docs available at: **http://localhost:8000/docs**

## 5. Running Both

Open two terminals:

**Terminal 1 (Backend):**
```bash
cd trustcast
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 (Frontend):**
```bash
cd trustcast/frontend
npm run dev
```

## 6. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check — returns `{"status": "ok", "service": "trustcast-backend"}` |
| GET | `/api/info` | Project metadata — returns project name, team, stage |
| GET | `/api/weather/models` | Five planned models with truthful integration status |
| GET | `/api/weather/locations` | Supported demo locations and coordinates |
| GET | `/api/weather/forecast` | Normalized data for one selected model |
| GET | `/api/weather/all-models` | Isolated results from every configured provider |
| GET | `/api/performance` | Step 3 historical verification: MAE, RMSE, bias, correlation, relative reliability per model (`location`, `variable`=temperature/precipitation, `days`=7-30, `lead_day`=1/2) |
| GET | `/api/blend` | Step 5 trust-weighted blended forecast aligned by valid time (`location`, `variable`, `forecast_days`=1-7, `lead_day`, `days`) |
| GET | `/api/uncertainty` | Step 6 model disagreement + TrustCast historical error range around the blend (same parameters as `/api/blend`) |
| GET | `/api/risks` | Step 7 forecast-based risk indicators: heavy rain, heat, cold, high wind (`location`, `forecast_days`, `lead_day`, `days`) |
| GET | `/api/trust` | Step 4 Trust Engine: deterministic model weights from Step 3 metrics, with generated reasons (same parameters as `/api/performance`) |

### Step 2 data sources — model lineup

A model is **LIVE** only when its real current run was retrieved and validated on this request; otherwise it is `waiting` (run not published yet), `unavailable` (official source checked, no point data), `error`, or `inactive` (optional, not running). Non-live models are automatically excluded from verification, trust, blend, uncertainty and risk; weights renormalise over the valid models, per variable.

| Model | Tier | Source actually used | Status today | Variables |
|-------|------|----------------------|--------------|-----------|
| ECMWF IFS | core | Open-Meteo Single Runs API `ecmwf_ifs025` (true run time) | live, verified, weighted | T2m, rain, 10 m wind, RH |
| NOAA GFS | core | Open-Meteo Single Runs API `gfs_global` | live, verified, weighted | T2m, rain, 10 m wind, RH |
| ECMWF AIFS | core | Open-Meteo Single Runs API `ecmwf_aifs025_single` | live, verified, weighted | T2m, rain, 10 m wind, RH |
| DWD ICON | optional | Open-Meteo Single Runs API `icon_global` | live, verified, weighted | T2m, rain, 10 m wind, RH |
| NOAA AIGEFS | core | Open-Meteo Ensemble API `ncep_aigefs025` + run metadata (`last_run_initialisation_time`) | live, **not weighted**: no archived forecasts to verify | T2m, 10 m wind (31 members, 6-hourly native steps; ensemble spread used for uncertainty) |
| NCMRWF NCUM-G | core | Official NCMRWF API `nwp.ncmrwf.gov.in/apis/api/v1` (checked each refresh) | unavailable: chart products only, no machine-readable point data | — |
| DWD AICON | core | DWD open data `opendata.dwd.de/weather/nwp/v1/m/aicon/` run listing (checked each refresh) | unavailable: GRIB2 on native icosahedral grid, CCSDS-compressed; no point-extraction toolchain | — |
| GraphCast, Pangu-Weather | optional | — | inactive (never fetched) | — |

No forecast value is ever generated for a model; NCUM-G/AICON cards show only what the official source publishes (provenance), never values. Every live record carries model, provider, run (init) time, valid time, lead time, retrieval time, source and grid point.

### Step 3 historical verification

`/api/performance` scores archived forecasts, never today's forecast against today's weather:

- **Forecasts:** [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) `<variable>_previous_day{1,2}`, the value each model forecast ~24h/48h before the valid hour (IFS, GFS, AIFS).
- **Observations:** ERA5 reanalysis via the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (`models=era5`, ~5-day publication lag). The window ends at the latest published ERA5 hour.
- **Metrics:** error = forecast − observed per hour. MAE = mean(|e|), RMSE = √mean(e²), Bias = mean(e), plus Pearson correlation.
- **Relative Reliability Score:** inverse MAE normalized across the scored models, `(1/(MAE+0.01)) / Σ(1/(MAE+0.01))`. It is a relative ranking of the evaluated models, not a standardized meteorological skill score, and it is valid only for the given location, variable, lead time and evaluation period. These are not blending weights; Step 4 builds those.
- NCUM and GraphCast/Pangu are listed with null metrics and never scored. If a source is down, the endpoint returns HTTP 502 and the UI shows an error. No synthetic fallback exists.

### Step 4 Trust Engine

`/api/trust` turns Step 3 verification metrics into model weights. The weights come from measured error; there are no random or hard-coded values:

```text
historical_skill = 1 / (RMSE over the full window + 0.05)
recent_skill     = 1 / (RMSE over the last 7 days + 0.05)
trust_score      = 0.7 × historical_skill + 0.3 × recent_skill
weight           = trust_score / Σ trust_score   (available models only)
```

- Both RMSE values come from the same real archived-forecast vs ERA5 data (one fetch, two windows).
- Lead time is taken into account because models are scored at the selected lead day (Day 1 or Day 2).
- Models with no data, or fewer than 24 verified samples, get no weight and are left out of the denominator. With one eligible model it gets 100% and a warning; with none, the status is `insufficient_data`.
- Each model's reasons (rank, recent trend, systematic bias) are generated from its metrics.
- Percentages use largest-remainder rounding, so they always sum to exactly 100.0%.

### Step 5 trust-weighted blending

`/api/blend` combines the live Step 2 forecasts (`weather_service.get_all_models`) with the Step 4 weights (`trust_engine.get_trust`). Both are reused from their existing services and caches.

```text
w_eff_i(t) = trust_weight_i / Σ trust_weight_j   (models with a value at valid_time t)
blend(t)   = Σ w_eff_i(t) × forecast_i(t)
```

- Forecasts are aligned by `valid_time`, so values from different timestamps are never mixed.
- A model with no value at an hour is excluded for that hour, never treated as zero, and the remaining weights are renormalized (`renormalized: true`).
- An hour with no available model returns `status: insufficient_data` and `blended_value: null`.
- A model needs both a live forecast and a Trust Engine weight to take part. NCUM and GraphCast/Pangu are listed under `excluded_models`.
- Values are returned at full precision; the UI rounds them for display only.

### Step 6 Uncertainty Engine

`/api/uncertainty` reuses the Step 5 blend (weights and aligned forecasts) and the Step 3 archived data. It reports two components that are kept separate:

- **Model disagreement** at each valid time: `spread = max − min` and trust-weighted `std = √Σ w_eff·(f − blend)²`. The level (LOW/MEDIUM/HIGH) compares the spread with the 33rd/67th percentiles of the same models' hourly spreads over the Step 3 window, so the thresholds come from data. With a single model, the level is `LIMITED_DATA` and no disagreement is invented.
- **Historical error range:** the current trust weights are applied to the archived forecasts (same lead day) and compared with ERA5, giving `error = blend − observed`. The forecast range is `[blend − P90(error), blend − P10(error)]`. It covered 80% of past hours in-sample; it is labelled as an empirical error range, not a calibrated probability. The precipitation range is clipped at 0.
- If the historical data is unavailable, only model disagreement is shown, and the explanation text says so. No confidence percentage is shown anywhere.

### Step 7 Extreme weather & risk indicators

`/api/risks` applies transparent threshold rules to the Step 5 blend and the Step 6 uncertainty for every variable (temperature, precipitation, and wind speed, which is now also verified in Steps 3–6). Only future hours are assessed.

| Risk | Value checked | ELEVATED | HIGH |
|------|---------------|----------|------|
| Heavy rainfall | 24 h accumulated TrustCast precipitation (mm) | ≥ 64.5 | ≥ 115.6 |
| Heat | hourly TrustCast 2 m temperature (°C) | ≥ 35 | ≥ 40 |
| Cold | hourly TrustCast 2 m temperature (°C) | ≤ 10 | ≤ 4 |
| High wind | hourly TrustCast 10 m wind (km/h) | ≥ 41 | ≥ 62 |

- The thresholds live only in `backend/app/data/risk_thresholds.py`. They are demo thresholds: the rain cut-offs follow IMD's heavy / very-heavy rainfall categories and the wind cut-offs are demo risk thresholds referenced to published meteorological categories (≈22 kt / 34 kt). None of these are official IMD warning thresholds, and the output is **not an official warning**.
- `check_threshold_with_uncertainty` compares the Step 6 range with each threshold and returns `CLEARLY_BELOW`, `THRESHOLD_CROSSED` or `CLEARLY_ABOVE`. For 24 h rain, the range is the min–max of each model's own 24 h total.
- Model consensus is `k / n`: the number of contributing models whose own forecast crosses the threshold. It is never shown as a percentage.
- A variable that can't be loaded gives `data_unavailable` for its risks; no data at all gives `insufficient_data`.

### Frontend structure

The dashboard is a single page that tells the story in six sections: 01 forecasts, 02 verification, 03 trust, 04 blend, 05 uncertainty, 06 risk, followed by a "Prototype limitations" drawer.

- `frontend/src/App.tsx`: state and the sequential API pipeline (Steps 2 → 7)
- `frontend/src/types.ts`: API response types (they mirror the FastAPI schemas)
- `frontend/src/lib.ts`: formatting, palette, monotone curve smoothing (never overshoots the real hourly values), and a width hook for responsive charts
- `frontend/src/components/`: `Hero`, `Sources`, `Verification`, `TrustEngine`, `Blend`, `Uncertainty`, `Risk`, `Limitations`, shared `ui` primitives and `charts`

No chart or UI library is used; all visuals are Tailwind CSS and inline SVG.

## 7. Running Tests

```bash
cd trustcast
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

## 8. Planned Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| **Step 1** | Project foundation, backend API, frontend scaffold | ✅ Complete |
| **Step 2** | Real model-data ingestion and normalization | ✅ Complete |
| **Step 3** | Historical forecast verification (vs ERA5 reanalysis) | ✅ Complete |
| **Step 4** | Trust Engine — dynamic model weighting | ✅ Complete |
| **Step 5** | Multi-model forecast blending | ✅ Complete |
| **Step 6** | Uncertainty quantification | ✅ Complete |
| **Step 7** | Extreme event detection (forecast-based risk indicators) | ✅ Complete |
| **Step 8** | Dashboard redesign (responsive, story-driven) and final polish | ✅ Complete |

---

**SIH 2026 — Team VisionCrafters**
