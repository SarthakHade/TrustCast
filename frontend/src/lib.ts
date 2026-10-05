import { useEffect, useState } from 'react'
import type { DisagreementLevel, RiskIndicator, RiskLevel, Variable } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function fetchModels<T>(url: string, fallbackMessage: string, requiredKey = 'models'): Promise<T> {
  const response = await fetch(url)
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok || !data || typeof data !== 'object' || !(requiredKey in data)) {
    const detail = data && typeof data === 'object' && 'detail' in data ? String(data.detail) : ''
    throw new Error(detail || fallbackMessage)
  }
  return data as T
}

// ---- Palette (muted atmospheric tones; every colour is paired with a text label in the UI) ----
export const MODEL_HEX: Record<string, string> = {
  'ECMWF IFS': '#8cc8ea',
  'NOAA GFS': '#f0b27a',
  'ECMWF AIFS': '#b9a7f2',
  'NCUM-G': '#7fd6c2',
  'DWD ICON': '#e3d27a',
  'DWD AICON': '#f2a3c0',
  'NOAA AIGEFS': '#9fd6f5',
}
export const BLEND_HEX = '#fbf1de'
export const modelHex = (model: string) => MODEL_HEX[model] ?? '#94a3b8'

/** The deterministic models shown as forecast cards (the models the blend draws on). */
export const PRIMARY_SOURCES = ['ECMWF IFS', 'NOAA GFS', 'ECMWF AIFS', 'DWD ICON']

const SHORT_NAME: Record<string, string> = {
  'ECMWF IFS': 'IFS',
  'NOAA GFS': 'GFS',
  'ECMWF AIFS': 'AIFS',
  'DWD ICON': 'ICON',
  'NOAA AIGEFS': 'AIGEFS',
  'DWD AICON': 'AICON',
}
export const shortName = (model: string) => SHORT_NAME[model] ?? model

export const LEVEL_HEX: Record<RiskLevel | DisagreementLevel, string> = {
  NORMAL: '#7cc9a6',
  LOW: '#7cc9a6',
  ELEVATED: '#e8b86a',
  MEDIUM: '#e8b86a',
  HIGH: '#e57b72',
  LIMITED_DATA: '#94a3b8',
}

// ---- Plain-language wording for backend results (display only; the levels come from the API) ----
export const AGREEMENT: Record<DisagreementLevel, { label: string; short: string; text: string }> = {
  LOW: { label: 'Low uncertainty', short: 'Models agree', text: 'Models are closely aligned.' },
  MEDIUM: { label: 'Medium uncertainty', short: 'Some disagreement', text: 'Some variation between forecasts.' },
  HIGH: { label: 'High uncertainty', short: 'High disagreement', text: 'Models disagree significantly. Forecast may change.' },
  LIMITED_DATA: { label: 'Limited data', short: 'Limited data', text: 'Only one model is available, so agreement cannot be assessed.' },
}

export type PerformanceLabel = 'Strong' | 'Good' | 'Moderate' | 'Limited'
export const PERFORMANCE_HEX: Record<PerformanceLabel, string> = {
  Strong: '#7cc9a6',
  Good: '#9fd0c0',
  Moderate: '#e8b86a',
  Limited: '#e57b72',
}
/** Track-record label from the backend verification: a model's average error relative to the best model here. */
export function performanceLabel(mae: number, bestMae: number): PerformanceLabel {
  const ratio = bestMae > 0 ? mae / bestMae : 1
  if (ratio <= 1.15) return 'Strong'
  if (ratio <= 1.5) return 'Good'
  if (ratio <= 2) return 'Moderate'
  return 'Limited'
}

const RISK_NAME: Record<string, string> = { HEAT: 'Heat', COLD: 'Cold', HEAVY_RAIN: 'Heavy rain', HIGH_WIND: 'High wind' }
export const riskName = (r: RiskIndicator) => RISK_NAME[r.risk_type] ?? r.title

/** One plain sentence per level; the level itself comes from the backend risk engine. */
export function riskHeadline(r: RiskIndicator) {
  const name = riskName(r).toLowerCase()
  if (r.level === 'HIGH') return `High ${name} risk`
  if (r.level === 'ELEVATED') return `Elevated ${name} risk`
  return `No significant ${name} risk`
}

/**
 * In-app alert state for HIGH risks only (levels from the backend risk engine). The key identifies the
 * location + hazards + peak times, so re-renders and reloads of the same result never re-show a dismissed alert.
 */
export function highRiskAlert(
  risks: { risks: RiskIndicator[] } | null,
  location: { latitude: number; longitude: number } | null,
  loading: boolean,
  dismissed: string[],
) {
  const high = !loading && risks && location ? risks.risks.filter((r) => r.status === 'ok' && r.level === 'HIGH') : []
  const key = location ? `${location.latitude},${location.longitude}|${high.map((r) => `${r.risk_type}@${r.peak_time}`).join(',')}` : ''
  return { risks: high, key, show: high.length > 0 && !dismissed.includes(key) }
}

/** When the worst conditions are expected, in words. */
export function riskWhen(r: RiskIndicator) {
  if (!r.peak_time) return ''
  if (r.aggregation === 'sum_24h') return `in the 24 hours to ${formatShort(r.peak_time)}`
  return `around ${formatShort(r.peak_time)}`
}

export const VARIABLE_LABEL: Record<Variable, string> = {
  temperature: 'Temperature',
  precipitation: 'Precipitation',
  wind_speed: 'Wind speed (10 m)',
}


// ---- Formatting (display only; values stay full precision in state) ----
export const fmt = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : value.toFixed(digits)

export function formatTime(value: string) {
  return new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}
export function formatShort(value: string) {
  return new Date(value).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}
export function formatHour(value: string) {
  return new Date(value).toLocaleString([], { hour: 'numeric' })
}
export function formatDay(value: string) {
  return new Date(value).toLocaleString([], { weekday: 'short', day: 'numeric' })
}
export function formatCoords(latitude: number, longitude: number) {
  const lat = `${Math.abs(latitude).toFixed(4)}° ${latitude >= 0 ? 'N' : 'S'}`
  const lon = `${Math.abs(longitude).toFixed(4)}° ${longitude >= 0 ? 'E' : 'W'}`
  return `${lat} · ${lon}`
}

// ---- Timestamp selection shared by the blend and uncertainty sections ----
export function nowIndexOf(points: { valid_time: string }[], openedAt: number) {
  return points.findIndex((p) => new Date(p.valid_time).getTime() >= openedAt - 30 * 60 * 1000)
}
export function selectedIndexOf(points: { valid_time: string }[], selectedTime: string | null, openedAt: number) {
  const chosen = points.findIndex((p) => p.valid_time === selectedTime)
  if (chosen >= 0) return chosen
  return Math.max(0, nowIndexOf(points, openedAt))
}

// ---- Chart geometry ----
export type Pt = { x: number; y: number }
type Segment = { x0: number; y0: number; c1x: number; c1y: number; c2x: number; c2y: number; x1: number; y1: number }

/**
 * Monotone cubic (Fritsch–Carlson) segments through the points. Unlike Catmull-Rom, the curve
 * never overshoots the real hourly values, so smoothing does not invent peaks or troughs.
 */
function monotoneSegments(pts: Pt[]): Segment[] {
  const n = pts.length
  if (n < 2) return []
  const dx: number[] = []
  const m: number[] = []
  for (let i = 0; i < n - 1; i++) {
    dx[i] = pts[i + 1].x - pts[i].x
    m[i] = dx[i] === 0 ? 0 : (pts[i + 1].y - pts[i].y) / dx[i]
  }
  const t: number[] = new Array(n)
  t[0] = m[0]
  t[n - 1] = m[n - 2]
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0
      t[i + 1] = 0
      continue
    }
    const a = t[i] / m[i]
    const b = t[i + 1] / m[i]
    const s = a * a + b * b
    if (s > 9) {
      const tau = 3 / Math.sqrt(s)
      t[i] = tau * a * m[i]
      t[i + 1] = tau * b * m[i]
    }
  }
  return pts.slice(0, -1).map((p, i) => {
    const q = pts[i + 1]
    const h = dx[i] / 3
    return { x0: p.x, y0: p.y, c1x: p.x + h, c1y: p.y + t[i] * h, c2x: q.x - h, c2y: q.y - t[i + 1] * h, x1: q.x, y1: q.y }
  })
}

const n1 = (v: number) => v.toFixed(1)

/** Smooth line through runs of points; `null` entries break the line (no bridging over gaps). */
export function smoothLine(points: (Pt | null)[]): string {
  return splitRuns(points).map((run) => {
    if (run.length === 1) return `M${n1(run[0].x)},${n1(run[0].y)}`
    const segs = monotoneSegments(run)
    return `M${n1(run[0].x)},${n1(run[0].y)}` + segs.map((s) => `C${n1(s.c1x)},${n1(s.c1y)} ${n1(s.c2x)},${n1(s.c2y)} ${n1(s.x1)},${n1(s.y1)}`).join('')
  }).join('')
}

/** Closed smooth band between lower and upper bounds (same x for both); breaks on missing bounds. */
export function smoothBand(lower: (Pt | null)[], upper: (Pt | null)[]): string {
  const pairs = lower.map((lo, i) => (lo && upper[i] ? { lo, hi: upper[i] as Pt } : null))
  return splitRuns(pairs).filter((run) => run.length > 1).map((run) => {
    const top = monotoneSegments(run.map((r) => r.hi))
    const bottom = monotoneSegments(run.map((r) => r.lo)).reverse()
    const first = run[0].hi
    const last = run[run.length - 1].lo
    return `M${n1(first.x)},${n1(first.y)}`
      + top.map((s) => `C${n1(s.c1x)},${n1(s.c1y)} ${n1(s.c2x)},${n1(s.c2y)} ${n1(s.x1)},${n1(s.y1)}`).join('')
      + `L${n1(last.x)},${n1(last.y)}`
      + bottom.map((s) => `C${n1(s.c2x)},${n1(s.c2y)} ${n1(s.c1x)},${n1(s.c1y)} ${n1(s.x0)},${n1(s.y0)}`).join('')
      + 'Z'
  }).join('')
}

function splitRuns<T>(items: (T | null)[]): T[][] {
  const runs: T[][] = [[]]
  for (const item of items) {
    if (item === null) {
      if (runs[runs.length - 1].length) runs.push([])
    } else {
      runs[runs.length - 1].push(item)
    }
  }
  return runs.filter((run) => run.length > 0)
}

/** Width of an element, kept in sync with ResizeObserver so charts render at real pixel size. */
export function useElementWidth<T extends HTMLElement>() {
  // Callback ref: re-observes if the measured element is replaced (e.g. loading → chart).
  const [element, setElement] = useState<T | null>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver((entries) => setWidth(Math.round(entries[0].contentRect.width)))
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])
  return [setElement, width] as const
}
