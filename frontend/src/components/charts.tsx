import { useId, type KeyboardEvent } from 'react'
import { BLEND_HEX, fmt, formatTime, modelHex, smoothBand, smoothLine, useElementWidth, type Pt } from '../lib'
import type { BlendPoint, BlendResponse, UncertaintyResponse } from '../types'

/** Tiny trend line of real values (no axes). Gaps (null) break the line. */
export function Sparkline({ values, color, height = 44, fill = true, label }: { values: (number | null)[]; color: string; height?: number; fill?: boolean; label?: string }) {
  const gradientId = useId()
  const finite = values.filter((v): v is number => v !== null)
  if (finite.length < 2) return null
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min || 1
  const width = 200
  const pts = values.map((v, i) => (v === null ? null : { x: (i / (values.length - 1)) * width, y: 4 + (1 - (v - min) / span) * (height - 8) }))
  const line = smoothLine(pts)
  const firstIdx = pts.findIndex((p) => p !== null)
  const lastIdx = pts.length - 1 - [...pts].reverse().findIndex((p) => p !== null)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-full w-full" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {label && <title>{label}</title>}
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && firstIdx >= 0 && !values.includes(null) && (
        <path d={`${line}L${(pts[lastIdx] as Pt).x},${height}L${(pts[firstIdx] as Pt).x},${height}Z`} fill={`url(#${gradientId})`} />
      )}
      <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
    </svg>
  )
}

/** Donut showing a share (0–1); the percentage is always printed in the centre. */
export function WeightRing({ value, color, size = 92, label }: { value: number; color: string; size?: number; label: string }) {
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} className="shrink-0">
      <title>{label}</title>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
      <circle
        cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
        strokeDasharray={`${c * value} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" fill="#fff" fontSize={size * 0.2} fontWeight="700" className="num">
        {(value * 100).toFixed(1)}%
      </text>
    </svg>
  )
}

type ForecastChartProps = {
  blend: BlendResponse
  uncertainty: UncertaintyResponse | null
  selectedIndex: number
  nowIndex: number
  onSelect: (index: number) => void
}

/**
 * Model curves + TrustCast blend + backend uncertainty bands, drawn at the container's real
 * pixel width so labels stay readable on phones. Every point comes from /api/blend and
 * /api/uncertainty; nothing is interpolated beyond the monotone smoothing between hours.
 */
export function ForecastChart({ blend, uncertainty, selectedIndex, nowIndex, onSelect }: ForecastChartProps) {
  const [ref, measured] = useElementWidth<HTMLDivElement>()
  const width = Math.max(measured, 280)
  const compact = width < 560
  const height = compact ? 250 : 330
  const pad = { left: compact ? 34 : 44, right: 12, top: 26, bottom: 34 }
  const points = blend.forecast
  const models = blend.models_used.map((m) => m.model)
  const bands = new Map((uncertainty?.forecast ?? []).map((u) => [u.valid_time, u]))

  const values = [
    ...points.flatMap((p) => [...Object.values(p.contributors), ...(p.blended_value === null ? [] : [p.blended_value])]),
    ...[...bands.values()].flatMap((u) => [u.historical_lower, u.historical_upper].filter((v): v is number => v !== null)),
  ]
  if (points.length < 2 || values.length === 0) {
    return <div ref={ref}><p className="text-sm text-mist">Not enough points to draw a chart.</p></div>
  }

  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin || 1
  const yMin = rawMin - span * 0.1
  const yMax = rawMax + span * 0.1
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom
  const x = (i: number) => pad.left + (i / (points.length - 1)) * plotW
  const y = (v: number) => pad.top + (1 - (v - yMin) / (yMax - yMin)) * plotH
  const series = (get: (p: BlendPoint) => number | null | undefined) =>
    points.map((p, i) => {
      const v = get(p)
      return v === null || v === undefined ? null : { x: x(i), y: y(v) }
    })

  const ticks = Array.from({ length: 4 }, (_, i) => yMin + ((yMax - yMin) * (i + 0.5)) / 4)
  const labelCount = Math.max(3, Math.floor(plotW / (compact ? 70 : 95)))
  const labelEvery = Math.max(1, Math.ceil(points.length / labelCount))
  const step = plotW / (points.length - 1)
  const selected = points[selectedIndex]
  const hasHistorical = [...bands.values()].some((u) => u.historical_lower !== null)

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'ArrowRight') onSelect(Math.min(points.length - 1, selectedIndex + 1))
    else if (event.key === 'ArrowLeft') onSelect(Math.max(0, selectedIndex - 1))
    else return
    event.preventDefault()
  }

  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block max-w-full touch-pan-y rounded-2xl"
        role="img"
        aria-label={`${blend.variable} forecast: model curves, TrustCast blend and uncertainty bands. Use arrow keys to move between hours.`}
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="rgba(255,255,255,0.06)" />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#8b96ad" className="num">{t.toFixed(1)}</text>
          </g>
        ))}
        {points.map((p, i) => i % labelEvery === 0 && (
          <text key={p.valid_time} x={x(i)} y={height - 10} textAnchor="middle" fontSize="11" fill="#8b96ad">
            {new Date(p.valid_time).toLocaleString([], compact ? { hour: 'numeric' } : { weekday: 'short', hour: 'numeric' })}
          </text>
        ))}

        {bands.size > 0 && (
          <>
            <path
              d={smoothBand(series((p) => bands.get(p.valid_time)?.model_min), series((p) => bands.get(p.valid_time)?.model_max))}
              fill="#ffffff" fillOpacity="0.05"
            />
            {hasHistorical && (
              <path
                d={smoothBand(series((p) => bands.get(p.valid_time)?.historical_lower), series((p) => bands.get(p.valid_time)?.historical_upper))}
                fill={BLEND_HEX} fillOpacity="0.16"
              />
            )}
          </>
        )}

        {nowIndex >= 0 && (
          <g>
            <line x1={x(nowIndex)} x2={x(nowIndex)} y1={pad.top} y2={height - pad.bottom} stroke="rgba(255,255,255,0.25)" strokeDasharray="3 4" />
            <text x={x(nowIndex) + 5} y={height - pad.bottom - 6} fontSize="11" fill="#aab4c8">now</text>
          </g>
        )}

        {models.map((m) => (
          <path key={m} d={smoothLine(series((p) => p.contributors[m]))} fill="none" stroke={modelHex(m)} strokeWidth="1.6" strokeOpacity="0.85" />
        ))}
        <path d={smoothLine(series((p) => p.blended_value))} fill="none" stroke={BLEND_HEX} strokeWidth="9" strokeOpacity="0.08" strokeLinecap="round" />
        <path d={smoothLine(series((p) => p.blended_value))} fill="none" stroke={BLEND_HEX} strokeWidth="3" strokeLinecap="round" />

        <line x1={x(selectedIndex)} x2={x(selectedIndex)} y1={pad.top} y2={height - pad.bottom} stroke="rgba(251,241,222,0.35)" />
        {selected?.blended_value !== null && selected && (
          <g>
            <circle cx={x(selectedIndex)} cy={y(selected.blended_value)} r="5.5" fill={BLEND_HEX} stroke="#0b1120" strokeWidth="2" />
            <text
              x={Math.min(Math.max(x(selectedIndex), pad.left + 30), width - pad.right - 30)}
              y={pad.top - 10}
              textAnchor="middle" fontSize="12" fontWeight="700" fill={BLEND_HEX} className="num"
            >
              {fmt(selected.blended_value)} {blend.unit}
            </text>
          </g>
        )}

        {points.map((p, i) => (
          <rect
            key={p.valid_time}
            x={x(i) - step / 2} y={pad.top} width={step} height={plotH}
            fill="transparent" className="cursor-pointer" onClick={() => onSelect(i)}
          >
            <title>{formatTime(p.valid_time)}{p.blended_value === null ? '' : ` · TrustCast ${fmt(p.blended_value)} ${blend.unit}`}</title>
          </rect>
        ))}
      </svg>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-mist">
        {models.map((m) => (
          <li key={m} className="flex items-center gap-2"><span className="inline-block h-0.5 w-5 rounded" style={{ background: modelHex(m) }} aria-hidden="true" />{m}</li>
        ))}
        <li className="flex items-center gap-2 font-semibold text-cream"><span className="inline-block h-1 w-6 rounded" style={{ background: BLEND_HEX }} aria-hidden="true" />TrustCast blend</li>
        {hasHistorical && (
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-6 rounded-sm" style={{ background: BLEND_HEX, opacity: 0.3 }} aria-hidden="true" />Prediction range</li>
        )}
        {bands.size > 0 && (
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-6 rounded-sm bg-white/10" aria-hidden="true" />Model spread (min–max)</li>
        )}
      </ul>
    </div>
  )
}
