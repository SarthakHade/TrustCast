// API response shapes. These mirror the FastAPI schemas; field names must not change.

export type Location = { name: string; latitude: number; longitude: number }

/** A real geocoder result from /api/locations/search (fields exactly as returned by the API). */
export type GeocodeResult = {
  id?: number
  name: string
  display_name: string
  area: string
  latitude: number
  longitude: number
  country?: string
  country_code?: string
  admin1?: string
  admin2?: string
  admin3?: string
  admin4?: string
  feature_code?: string
  population?: number
}

/** The forecast context: these exact coordinates are sent to every pipeline step. */
export type SelectedLocation = {
  name: string
  display_name: string
  area?: string
  latitude: number
  longitude: number
  source: 'preset' | 'geocoder'
}

// Decided per request from what each real source returned (see backend schemas/weather.py).
export type ModelStatus = 'live' | 'waiting' | 'unavailable' | 'error' | 'inactive' | 'adapter_ready' | 'data_unavailable'
type Provenance = Record<string, string | number | boolean | null>
type SourceFlags = {
  source_type?: string | null
  is_live?: boolean
  tier?: 'core' | 'optional'
  variables?: string[]
}
export type Variable = 'temperature' | 'precipitation' | 'wind_speed'

export type Model = {
  name: string
  model_type: string
  provider: string
  status: ModelStatus
  source?: string
  source_url?: string | null
  note?: string
} & SourceFlags
export type ForecastRecord = {
  init_time: string
  valid_time: string
  lead_time_hours: number
  temperature: number | null
  precipitation: number | null
  wind_speed: number | null
  humidity: number | null
  ensemble_members?: number | null
  temperature_spread?: number | null
  precipitation_spread?: number | null
  wind_speed_spread?: number | null
}
export type ProviderForecast = {
  model: string
  model_type: string
  provider: string
  status: ModelStatus
  source?: string
  source_url?: string | null
  init_time?: string
  forecast: ForecastRecord[]
  error?: string
  retrieved_at?: string | null
  provenance?: Provenance
} & SourceFlags

export type ModelPerformance = {
  model: string
  model_type: string
  provider: string
  status: ModelStatus
  samples: number
  mae: number | null
  rmse: number | null
  bias: number | null
  correlation: number | null
  skill_score: number | null // relative reliability (normalized inverse MAE)
  note?: string | null
  calibration?: 'archived_forecasts' | null
}
export type PerformanceResponse = {
  location: string
  variable: Variable
  unit: string
  lead_day: number
  period_start: string | null
  period_end: string | null
  data_mode: 'real_archived_forecasts'
  forecast_source: string
  observation_source: string
  skill_method: string
  models: ModelPerformance[]
}

export type ModelTrust = {
  model: string
  model_type: string
  status: ModelStatus
  included: boolean
  historical_rmse: number | null
  recent_rmse: number | null
  bias: number | null
  samples: number
  historical_skill: number | null // = 1 / (historical RMSE + ε): shown as "historical inverse error"
  recent_skill: number | null // = 1 / (recent RMSE + ε): shown as "recent inverse error"
  trust_score: number | null
  weight: number | null
  weight_percent: number | null
  reasons: string[]
}
export type TrustResponse = {
  location: string
  variable: string
  unit: string
  lead_day: number
  status: 'ok' | 'single_model' | 'insufficient_data'
  message: string | null
  historical_period_start: string | null
  historical_period_end: string | null
  historical_days: number
  recent_days: number | null
  method: string
  formula: string[]
  models: ModelTrust[]
}

export type BlendPoint = {
  valid_time: string
  status: 'ok' | 'insufficient_data'
  blended_value: number | null
  contributors: Record<string, number>
  effective_weights: Record<string, number>
  renormalized: boolean
}
export type ExcludedModel = { model: string; status: ModelStatus; reason: string }
export type BlendModel = { model: string; trust_weight: number; trust_weight_percent: number | null; init_time: string | null; points: number }
export type BlendResponse = {
  location: string
  variable: string
  unit: string
  forecast_days: number
  trust_lead_day: number
  status: 'ok' | 'insufficient_data'
  message: string | null
  method: string
  formula: string[]
  models_used: BlendModel[]
  excluded_models: ExcludedModel[]
  forecast: BlendPoint[]
}

export type DisagreementLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'LIMITED_DATA'
export type UncertaintyPoint = {
  valid_time: string
  status: 'ok' | 'limited_data' | 'insufficient_data'
  blended_value: number | null
  models_used: string[]
  model_min: number | null
  model_max: number | null
  model_mean: number | null
  model_spread: number | null
  weighted_std: number | null
  disagreement_level: DisagreementLevel | null
  historical_lower: number | null
  historical_upper: number | null
  ensemble_spread?: Record<string, number>
}
export type UncertaintyResponse = {
  location: string
  variable: string
  unit: string
  forecast_days: number
  lead_day: number
  status: 'ok' | 'limited_data' | 'insufficient_data'
  message: string | null
  explanation: string
  formula: string[]
  thresholds: { low_max: number; medium_max: number; samples: number; source: string } | null
  historical: {
    samples: number; rmse: number; mae: number; bias: number; error_p10: number; error_p90: number
    coverage: number; period_start: string; period_end: string; note: string
  } | null
  models_used: string[]
  excluded_models: ExcludedModel[]
  forecast: UncertaintyPoint[]
  ensemble_sources?: Record<string, number>
}

export type RiskLevel = 'NORMAL' | 'ELEVATED' | 'HIGH'
export type RiskIndicator = {
  risk_type: string
  title: string
  variable: string
  unit: string
  status: 'ok' | 'data_unavailable'
  reason: string | null
  direction: 'above' | 'below'
  thresholds: { ELEVATED: number; HIGH: number }
  aggregation: 'hourly' | 'sum_24h'
  basis: string
  level: RiskLevel | null
  peak_time: string | null
  window_start: string | null
  accumulation_hours: number | null
  forecast_value: number | null
  lower: number | null
  upper: number | null
  range_source: string | null
  key_threshold: number | null
  range_position: 'CLEARLY_BELOW' | 'THRESHOLD_CROSSED' | 'CLEARLY_ABOVE' | null
  threshold_crossing: boolean
  models_exceeding: number
  models_total: number
  model_consensus: string | null
  messages: string[]
  timeline: { valid_time: string; level: RiskLevel; value: number }[]
}
export type RiskResponse = {
  location: string
  forecast_days: number
  lead_day: number
  status: 'ok' | 'insufficient_data'
  message: string | null
  horizon_start: string | null
  horizon_end: string | null
  source_label: string
  disclaimer: string
  risks: RiskIndicator[]
}


// ---- Advanced evaluation (walk-forward skill engine) ----
export type MethodMetrics = {
  n: number
  mae: number | null
  rmse: number | null
  bias: number | null
  correlation: number | null
  skill_vs_equal: number | null
  skill_vs_best_single: number | null
}
export type BreakdownRow = { group: string; hours: number; days: number; skill_vs_equal: number | null; skill_vs_best_single: number | null } & Record<string, number | string | null>
export type EventMethod = { hits: number; misses: number; false_alarms: number; correct_negatives: number; pod: number | null; far: number | null; csi: number | null }
export type SkillReport = {
  location: string
  latitude: number
  longitude: number
  variable: Variable
  unit: string
  lead_day: number
  models: string[]
  period_start: string | null
  period_end: string | null
  evaluation_days: number
  common_hours: number
  metrics: Record<string, MethodMetrics>
  skill_intervals_90: Record<'equal' | 'best_single', { low: number | null; high: number | null; resamples: number } | null>
  bias_correction_gain: number | null
  adaptive_weighting_gain: number | null
  by_season: BreakdownRow[]
  by_regime: BreakdownRow[]
  variant_usage: Record<string, number>
  fallback_days: number
  events?: { accumulation: string; days: number; thresholds: { threshold_mm: number; observed_events: number; methods: Record<string, EventMethod> }[] }
  oos_residuals: { samples: number; p10: number | null; p90: number | null; period_start: string | null; period_end: string | null }
  live: {
    status: string
    variant?: string
    level?: string
    note?: string
    weights?: Record<string, number>
    samples?: number
    training_end?: string
    bias_correction?: { kind: string; mode: string; per_model: Record<string, number> }
    reason?: string
  } | null
  live_target: { date: string; regime: string; regime_label: string; season: string; season_label: string }
  training: { window_days: number; gap_days: number }
  sources: Record<string, string>
  data_quality: Record<string, number | string | boolean | null>
  data_fetched_at: string | null
  methodology: Record<string, string | number>
  probabilistic: { status: string; reason: string }
}

export type SpatialCell = {
  id: string
  latitude: number
  longitude: number
  south: number
  north: number
  west: number
  east: number
  land_fraction: number
  status: string
  reason?: string
  evaluation_days?: number
  common_hours?: number
  period_start?: string | null
  period_end?: string | null
  skill?: {
    trustcast_rmse: number | null
    equal_rmse: number | null
    best_single_rmse: number | null
    skill_vs_equal: number | null
    skill_vs_best_single: number | null
    model_rmse: Record<string, number | null>
  }
  regime?: string
  season?: string
  coverage?: Record<string, number>
  live?: { variant: string; level: string; weights: Record<string, number>; dominant: string; training_end: string; bias_correction: Record<string, number> }
  risks?: Record<string, { level: RiskLevel | null; status: string; value: number | null; unit: string; peak_time: string | null; models_exceeding: number; models_total: number }>
}
export type SpatialLayer = {
  status?: string
  reason?: string
  generated_at?: string
  issued_at?: string
  resolution_deg?: number
  history_days?: number
  mask_source?: string
  models?: string[]
  variable?: Variable
  unit?: string
  lead_day?: number
  note?: string
  pooled?: Record<string, { weights: Record<string, number>; hours: number; cells: number; label: string }>
  cells: SpatialCell[]
}

// ---- AIGEFS ensemble guidance ----
export type EnsembleThreshold = { level: 'ELEVATED' | 'HIGH'; threshold: number; members_exceeding: number; members_valid: number; probability: number }
export type EnsembleRisk = {
  status: string
  reason?: string
  unit?: string
  valid_time?: string
  window_start?: string | null
  thresholds?: EnsembleThreshold[]
  member_percentiles?: { p50: number | null; p75: number | null; p90: number | null; max: number | null }
}
export type EnsembleGuidance = { status: string; reason?: string; source?: string; run?: string; members?: number; risks?: Record<string, EnsembleRisk>; caveats?: string[] }
