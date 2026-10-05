# TrustCast

**Hybrid AI–NWP Multi-Model Forecast Blending System**

> Problem Statement: **SIH26081** | Team: **VisionCrafters** | Smart India Hackathon 2026

---

## 1. Project Overview

TrustCast is a hybrid system that blends forecasts from multiple Numerical Weather Prediction (NWP) models using AI-driven trust scoring. The system dynamically weights each model based on historical performance, producing more accurate and reliable weather forecasts with quantified uncertainty.

## 2. Current Architecture (research prototype)

```
trustcast/
├── frontend/                 # React + Vite + TypeScript + Tailwind CSS (public dashboard + #/evaluation view)
├── backend/
│   ├── app/
│   │   ├── api/routes.py     # all HTTP endpoints
│   │   ├── services/
│   │   │   ├── weather/      # live model providers (Open-Meteo, AIGEFS, NCUM-G/AICON probes)
│   │   │   ├── performance_service.py, trust_engine.py, blend_service.py,
│   │   │   │   uncertainty_service.py, risk_service.py   # Steps 3–7
│   │   │   └── skill/        # scientific engine (see "Scientific engine" below)
│   │   │       ├── dataset.py      # ERA5 + archived forecasts, batching, backoff, disk cache
│   │   │       ├── walkforward.py  # rolling-origin validation, bias correction, stacking, events
│   │   │       ├── stats.py        # metrics, simplex-constrained QP, sanity checks
│   │   │       ├── regime.py       # IMD seasons + rule-based weather regimes
│   │   │       ├── ensemble.py     # NOAA AIGEFS exceedance probabilities
│   │   │       ├── spatial.py      # precomputed grid store, cell lookup, regional pooling
│   │   │       └── service.py      # /api/skill report + live adaptive parameters
│   │   └── data/                   # presets, risk thresholds
│   ├── data/spatial/         # grid_cells.json (committed) + precomputed weights/risk (generated)
│   ├── data/cache/           # downloaded history (generated, git-ignored)
│   └── scripts/
│       ├── build_grid.py           # one-off: 1.5° India computation grid
│       └── spatial_precompute.py   # daily: regional verification, weights, pooled regimes, risk
└── tests/                    # backend tests (pytest); frontend tests live in frontend/src (Vitest)
```

Pipeline:

```
historical archive + ERA5 → walk-forward verification → bias correction → regime/season detection
→ constrained stacking → regional pooling (offline) → cached parameters → live forecast → fast inference
→ uncertainty (out-of-sample errors) → risk + AIGEFS ensemble guidance
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

**Spatial precomputation (offline, ~10 minutes, rate limited):**
```bash
cd trustcast
.venv\Scripts\python.exe backend\scripts\spatial_precompute.py
```
It writes `backend/data/spatial/weights_<variable>_d<lead>.json`, `risk_latest.json` and `manifest.json`.
Re-running the same day resumes from cached downloads. For daily operation schedule it, for example with
Windows Task Scheduler or cron (`30 6 * * * cd /path/to/trustcast && .venv/bin/python backend/scripts/spatial_precompute.py`).
**No scheduler is configured by this repository**; until the script is run, the regional map shows "not precomputed yet".

## 6. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check — returns `{"status": "ok", "service": "trustcast-backend"}` |
| GET | `/api/info` | Project metadata — returns project name, team, stage |
| GET | `/api/weather/models` | Five planned models with truthful integration status |
| GET | `/api/weather/locations` | Preset cities (suggestions; still usable by name) |
| GET | `/api/locations/search` | Real location search in India via the Open-Meteo Geocoding API |
| GET | `/api/weather/forecast` | Normalized data for one selected model |
| GET | `/api/weather/all-models` | Isolated results from every configured provider |
| GET | `/api/performance` | Step 3 historical verification: MAE, RMSE, bias, correlation, relative reliability per model (`location`, `variable`=temperature/precipitation, `days`=7-30, `lead_day`=1/2) |
| GET | `/api/blend` | Step 5 trust-weighted blended forecast aligned by valid time (`location`, `variable`, `forecast_days`=1-7, `lead_day`, `days`) |
| GET | `/api/uncertainty` | Step 6 model disagreement + TrustCast historical error range around the blend (same parameters as `/api/blend`) |
| GET | `/api/risks` | Step 7 forecast-based risk indicators: heavy rain, heat, cold, high wind (`location`, `forecast_days`, `lead_day`, `days`) |
| GET | `/api/trust` | Step 4 Trust Engine: deterministic model weights from Step 3 metrics, with generated reasons (same parameters as `/api/performance`) |
| GET | `/api/skill` | Walk-forward (out-of-sample) evaluation: TrustCast vs equal-weight mean, best single model and each model; skill scores with 90% bootstrap intervals; bias-correction and adaptive-weighting gains; season/regime breakdowns; rain POD/FAR/CSI (`latitude`, `longitude`, `variable`, `lead_day`) |
| GET | `/api/ensemble` | NOAA AIGEFS ensemble exceedance probabilities for the risk thresholds (member counts; not calibrated) |
| GET | `/api/spatial/map` | Precomputed regional skill and adaptive weights per 1.5° cell (`variable`, `lead_day`) |
| GET | `/api/spatial/risk` | Precomputed TrustCast risk indicator per cell |
| GET | `/api/spatial/cell` | The grid cell containing a point, with its regional weights, skill and risk |

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

### Location search (any Indian city, town or locality)

- `GET /api/locations/search?q=<text>` calls the free **Open-Meteo Geocoding API** (GeoNames data, `countryCode=IN`, no API key) and returns real places with the API's own coordinates and admin hierarchy (`admin1`…`admin4`). No local location database is used; queries are cached in memory for 24 h, and the UI debounces typing (350 ms, at least 2 characters). No match returns an empty list ("No locations found"), and nothing is substituted.
- The selected point becomes the forecast context. Every pipeline endpoint (`/api/performance`, `/api/trust`, `/api/blend`, `/api/uncertainty`, `/api/risks`) accepts `latitude`, `longitude` and `name`, which take priority over `location=<preset>`. There is no fallback to a preset city, and caches are keyed by coordinates.
- Verification and trust are computed at the selected coordinates (Open-Meteo Previous Runs + ERA5 accept any point). Both are gridded (~0.25°), so nearby localities in the same grid cells get identical verification.
- Each live model card shows the requested point, the model grid point the source used, and their real Haversine distance; it is flagged when more than 10 km.
- The five preset cities remain as suggestions and as `location=<name>` for backward compatibility.

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

### Scientific engine (research prototype)

All results are computed from real data; where data are missing the engine reports "unavailable" instead of filling in values.

**Data.** Archived Day-1 and Day-2 forecasts of the four contributing models (Open-Meteo Previous Runs API) and ERA5 (Open-Meteo Historical Weather API) from **2025-02-18** — the first day all four models have archives (ECMWF AIFS) — to the latest ERA5 day (~5 days behind real time). Units are requested explicitly (°C, km/h, mm). Implausible values are rejected, duplicated timestamps are dropped, and both are counted in the report's data-quality block.

**Walk-forward validation.** For every target day *d* at lead *L*, parameters are trained on the 21 days ending at *d − L − 5* (the forecast is issued *L* days ahead and ERA5 is published ~5 days late). Nothing from later days is used; a test (`test_no_future_leakage…`) changes every later observation and checks that the forecast for *d* is unchanged.

**Methods compared on identical hours.** Each raw model · equal-weight mean · best single model (chosen on the training window) · previous TrustCast weights (0.7/0.3 inverse RMSE) · bias-corrected mean · bias-corrected stacking · + regime conditioning · + season conditioning · **TrustCast**, which uses whichever of the last five had the lowest out-of-sample RMSE over the previous 30 verifiable days (so the choice is also leakage-free).

**Bias correction.** Additive per model and hour of day for temperature and wind (overall mean when an hour has < 10 samples); multiplicative ratio of totals, bounded 0.5–2, for rain (zero-inflated, cannot be shifted). Wind and rain are clipped at 0.

**Adaptive constrained stacking.** With Σw = 1 the blend error is wᵀe, so its mean square is wᵀCw (C = second moments of the bias-corrected errors). TrustCast minimises wᵀCw + λ‖w − 1/K‖² subject to w ≥ 0, Σw = 1, solved exactly by enumerating active sets. λ ∈ {0.01, 0.1, 0.5, 2, 10} × trace(C)/K is chosen weekly on a time-ordered hold-out. With fewer than 120 complete hours the previous TrustCast weights are used and the fallback is recorded.

**Seasons and regimes.** IMD seasons (Jan–Feb, Mar–May, Jun–Sep, Oct–Dec). A transparent rule-based daily regime from the forecast fields (known at issue time): strong wind (max ≥ 41 km/h), heatwave (max ≥ 40 °C; absolute criterion, no climatology departure), active monsoon (Jun–Sep, ≥ 15.6 mm and RH ≥ 80 %), convective (outside Jun–Sep, ≥ 15.6 mm), fog-prone (Nov–Feb, min ≤ 12 °C, RH ≥ 95 %, wind ≤ 7 km/h), monsoon break (Jun–Sep, < 2.5 mm), normal. Regime weights need ≥ 72 past hours of that regime.

**Fallback hierarchy (live).** regime + location → regime (regional pool across grid cells) → location → regional pool (all regimes) → previous TrustCast weights. The regional pools are trained offline before the run, so they are used live but are not part of the walk-forward scores.

**Uncertainty.** The forecast range on the dashboard is the 10th–90th percentile of TrustCast's own out-of-sample errors over the last 60 verified days (per lead day).

**Rain events.** 24-hour totals on the IMD rainfall day (03–03 UTC), thresholds 2.5 / 15.6 / 64.5 mm. POD = H/(H+M), FAR = F/(H+F), CSI = H/(H+M+F); each is reported only when its denominator has ≥ 5 cases, otherwise N/A.

**Ensemble guidance.** NOAA AIGEFS (31 members): P = members exceeding / members with complete data, for each risk threshold. Rain uses 24-hour member totals (Open-Meteo spreads each 6-h amount evenly over its hours); temperature and wind use native 6-hourly steps only, which can miss the daily extreme. No archived AIGEFS forecasts exist, so these probabilities are **not verified or calibrated**; no Brier score, reliability diagram or CRPS is reported, and CRPS is never applied to deterministic forecasts.

**Spatial grid.** 167 cells of 1.5° over India (`build_grid.py`, Natural Earth mask used for computation only; no boundaries are drawn). `spatial_precompute.py` downloads the last 56 days for all cells in batches of 20 (≥ 10 s apart, backoff on 429/5xx, resumable cache), runs the same walk-forward per cell, stores the live weights, dominant model ("Balanced" when the top two weights differ by < 0.05), regional skill and per-cell risk. A selected location uses its own point history for its forecast; the grid provides regional pooling and the Evaluation map.

**Example (Mumbai, real data, 2025-03-16 → 2026-09-29, 563 out-of-sample days).** Temperature Day 1: TrustCast RMSE 0.62 °C vs equal-weight mean 1.01 °C (skill +38 %, 90 % interval +35 % to +41 %); most of the gain is bias correction (+31 %), stacking adds +11 %. Rain Day 1: skill vs equal-weight mean +2 % with an interval spanning zero (no significant improvement), +9 % vs the best single model. Numbers change as data are added; the Evaluation view always shows the current values.

### Frontend structure

The public dashboard (`/`) is a single page: location and forecast controls with the current TrustCast forecast, then six pipeline sections: 01 forecasts, 02 verification, 03 trust, 04 blend, 05 uncertainty, 06 risk. The forecasts section shows the four contributing models (ECMWF IFS, NOAA GFS, ECMWF AIFS, DWD ICON); NOAA AIGEFS (ensemble spread, uncertainty only) and NCUM-G (unavailable for machine-readable point forecasts) are listed there as additional sources. Technical material lives only in the separate Evaluation view (`#/evaluation`, linked from the header): model skill tables, baseline comparison with intervals, bias-correction/stacking gains, season and regime breakdowns, rain POD/FAR/CSI, the current adaptive configuration and the regional grid map (dominant model / skill vs equal weighting / risk).

- `frontend/src/App.tsx`: state and the sequential API pipeline (Steps 2 → 7)
- `frontend/src/types.ts`: API response types (they mirror the FastAPI schemas)
- `frontend/src/lib.ts`: formatting, palette, monotone curve smoothing (never overshoots the real hourly values), and a width hook for responsive charts
- `frontend/src/components/`: `Hero`, `LocationSearch`, `Sources`, `Verification`, `TrustEngine`, `Blend` (+ `ForecastTimeline`), `Uncertainty`, `Risk`, `RiskAlert`, `Intro`, `EvaluationView`, `SpatialMap`, shared `ui` primitives and `charts`

No chart or UI library is used; all visuals are Tailwind CSS and inline SVG.

### Known limitations

- ERA5 is a gridded reanalysis used as the historical reference, not direct station observations. It is produced by ECMWF, which may slightly favour the ECMWF models.
- The dashboard's "Model track record" labels still use the 21-day raw-model verification; the adaptive weights and the forecast range come from the walk-forward engine (out-of-sample).
- Weights are trained for Day-1 and Day-2 archive leads only; forecast hours beyond 48 h reuse the Day-2 parameters.
- The forecast range has a fixed width per lead day; it does not widen when models disagree more. Model agreement is shown separately.
- Regime rules are simple thresholds on forecast fields, not a full meteorological regime classification; rare regimes often fall back to location or regional weights.
- History starts 2025-02-18, so each season has been seen once or twice; seasonal results are noisy for short seasons.
- The spatial grid is coarse (1.5°, 56 days) and precomputed once per run; no scheduler is configured.
- AIGEFS ensemble probabilities are not calibrated (no archived ensemble forecasts); probabilistic skill cannot be verified.
- Heat and cold thresholds are demo thresholds, not local climatological criteria. The rain (64.5 / 115.6 mm per 24 h) and wind (41 / 62 km/h) cut-offs are referenced to published categories. Risk output is not an official warning.
- This is a research prototype validated on the available historical data; it is not an operational forecasting system.
- NCUM-G: NCMRWF's public sources publish chart products only, so no NCUM-G values are ingested, scored, weighted or blended. DWD AICON point extraction (native icosahedral GRIB2) is not enabled. NOAA AIGEFS has no archived forecasts, so it is not weighted; its ensemble spread is an additional uncertainty signal. GraphCast and Pangu-Weather are not running.
- Data-leakage check: walk-forward training ends L + 5 days before each target day (tested). Step 3 verification pairs each archived forecast, issued about 24 h (Day 1) or 48 h (Day 2) before its valid time, with the ERA5 value at that same valid time. Live forecasts keep their own run, lead and valid times and are blended only at matching valid times.

## 7. Running Tests

```bash
cd trustcast
.venv\Scripts\python.exe -m pytest -q        # backend: walk-forward, leakage, bias, stacking, events, spatial, ensemble, API
cd frontend
npm test                                      # frontend (Vitest): high-risk alert logic, Details accordion
npm run build && npm run lint
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
| **Step 9** | Walk-forward validation, baselines, bias correction, constrained stacking | ✅ Complete (research prototype) |
| **Step 10** | Regime + season conditioning, regional pooling, spatial grid + map | ✅ Complete (coarse 1.5° grid) |
| **Step 11** | AIGEFS ensemble exceedance guidance | ✅ Live; ⚠ not calibrated (no archive) |
| **Step 12** | NCUM-G ingestion | ❌ No machine-readable public point data |

---

**SIH 2026 — Team VisionCrafters**
