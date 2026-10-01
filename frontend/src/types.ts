// API response shapes. These mirror the FastAPI schemas; field names must not change.

export type Location = { name: string; latitude: number; longitude: number }
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
  models_used: { model: string; trust_weight: number; trust_weight_percent: number | null; init_time: string | null; points: number }[]
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

