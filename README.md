# TrustCast

**Hybrid AI–NWP Multi-Model Forecast Blending System**

> Problem Statement: **SIH26081** | Team: **VisionCrafters** | Smart India Hackathon 2026

---

## 1. Project Overview

TrustCast is a hybrid system that blends forecasts from multiple Numerical Weather Prediction (NWP) models using AI-driven trust scoring. The system dynamically weights each model based on historical performance, producing more accurate and reliable weather forecasts with quantified uncertainty.

## 2. Current Architecture (Foundation - Step 1)

```
trustcast/
├── frontend/          # React + Vite + TypeScript + Tailwind CSS
├── backend/           # FastAPI + Python
│   └── app/
│       ├── main.py    # Application entry point
│       ├── config.py  # Environment configuration
│       ├── api/       # API route handlers
│       ├── schemas/   # Pydantic models (future)
│       ├── services/  # Business logic (future)
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
cd trustcast/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend runs at: **http://localhost:8000**

API docs available at: **http://localhost:8000/docs**

## 5. Running Both

Open two terminals:

**Terminal 1 (Backend):**
```bash
cd trustcast/backend
uvicorn app.main:app --reload --port 8000
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

## 7. Running Tests

```bash
cd trustcast
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

## 8. Planned Implementation Phases

| Phase | Description | Status |
|-------|-------------|--------|
| **Step 1** | Project foundation, backend API, frontend scaffold | ✅ Current |
| **Step 2** | NWP data ingestion (GFS and ECMWF sources) | 🔲 Planned |
| **Step 3** | ML preprocessing and model performance tracking | 🔲 Planned |
| **Step 4** | Trust Engine — dynamic model weighting | 🔲 Planned |
| **Step 5** | Multi-model forecast blending | 🔲 Planned |
| **Step 6** | Uncertainty quantification | 🔲 Planned |
| **Step 7** | Extreme event detection and alerting | 🔲 Planned |
| **Step 8** | Dashboard visualization and final polish | 🔲 Planned |

---

**SIH 2026 — Team VisionCrafters**
