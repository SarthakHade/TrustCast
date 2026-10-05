import { useEffect, useRef, type KeyboardEvent } from 'react'
import { AGREEMENT, BLEND_HEX, LEVEL_HEX, fmt, formatTime, modelHex, shortName, smoothBand, smoothLine, useElementWidth } from '../lib'
import type { BlendPoint, BlendResponse, ProviderForecast, UncertaintyResponse } from '../types'

type Props = {
  blend: BlendResponse
  uncertainty: UncertaintyResponse | null
  /** Live source forecasts: used only for the rain row (mean of the contributing models). */
  results: ProviderForecast[]
  selectedIndex: number
  nowIndex: number
  onSelect: (index: number) => void
}

const GUTTER = 64
const MIN_COL = 46
const ROW = { day: 13, time: 30, value: 52, chartTop: 70 }
const RAIN_HEX = '#8cc8ea'

const timeLabel = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
const dayKey = (iso: string) => new Date(iso).toDateString()
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString([], { weekday: 'short', day: 'numeric' })

/**
 * Weather-style hourly timeline of the trust-weighted blend: one column per valid time with the
 * blended value, the contributing model curves (secondary), the TrustCast curve (dominant), the
 * backend prediction range, rain from the contributing models and the model-disagreement level.
 * Every value comes from /api/blend, /api/uncertainty and /api/weather/all-models.
 */
export function ForecastTimeline({ blend, uncertainty, results, selectedIndex, nowIndex, onSelect }: Props) {
  const [measureRef, measured] = useElementWidth<HTMLDivElement>()
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const points = blend.forecast
  const n = points.length
  const isRain = blend.variable === 'precipitation'
  const unit = blend.unit
  const compact = measured > 0 && measured < 560
  const gutter = compact ? 0 : GUTTER
  const colW = Math.max(MIN_COL, n ? (measured - gutter) / n : MIN_COL)
  const width = Math.round(colW * n)
  const chartH = compact ? 150 : 190
  const chartBottom = ROW.chartTop + chartH
  const models = blend.models_used.map((m) => m.model)
  const bands = new Map((uncertainty?.forecast ?? []).map((u) => [u.valid_time, u]))
  const hasRange = [...bands.values()].some((u) => u.historical_lower !== null)

  // Rain row (non-rain variables): mean hourly precipitation of the contributing models at each valid time.
  const rainByTime = new Map<string, number>()
  if (!isRain) {
    const sources = results.filter((r) => models.includes(r.model) && r.status === 'live' && (r.variables ?? []).includes('precipitation'))
    for (const p of points) {
      const t = new Date(p.valid_time).getTime()
      const vals = sources
        .map((r) => r.forecast.find((rec) => new Date(rec.valid_time).getTime() === t)?.precipitation)
        .filter((v): v is number => v !== null && v !== undefined)
      if (vals.length) rainByTime.set(p.valid_time, vals.reduce((a, b) => a + b, 0) / vals.length)
    }
  }
  const hasRainRow = rainByTime.size > 0
  const rainY = chartBottom + 22
  const spreadY = hasRainRow ? rainY + 24 : chartBottom + 20
  const height = spreadY + 16

  // Keep the selected hour in view when the timeline scrolls horizontally. DOM only, no state.
  useEffect(() => {
    const el = scrollRef.current
    if (!el || selectedIndex < 0) return
    const left = selectedIndex * colW
    if (left < el.scrollLeft || left + colW > el.scrollLeft + el.clientWidth) {
      el.scrollLeft = Math.max(0, left - el.clientWidth / 3)
    }
  }, [selectedIndex, colW, measured])

  const values = [
    ...points.flatMap((p) => [...Object.values(p.contributors), ...(p.blended_value === null ? [] : [p.blended_value])]),
    ...[...bands.values()].flatMap((u) => [u.historical_lower, u.historical_upper].filter((v): v is number => v !== null)),
  ]
  if (n < 2 || values.length === 0) {
    return <div ref={measureRef}><p className="text-sm text-mist">Not enough points to draw the timeline.</p></div>
  }

  const rawMin = isRain ? 0 : Math.min(...values)
  const rawMax = Math.max(...values, isRain ? 0.5 : -Infinity)
  const span = rawMax - rawMin || 1
  const yMin = isRain ? 0 : rawMin - span * 0.12
  const yMax = rawMax + span * 0.12
  const x = (i: number) => (i + 0.5) * colW
  const y = (v: number) => ROW.chartTop + (1 - (v - yMin) / (yMax - yMin)) * chartH
  const series = (get: (p: BlendPoint) => number | null | undefined) =>
    points.map((p, i) => {
      const v = get(p)
      return v === null || v === undefined ? null : { x: x(i), y: y(v) }
    })
  const shortValue = (v: number) => (isRain ? v.toFixed(1) : unit === '°C' ? `${Math.round(v)}°` : `${Math.round(v)}`)
  const blendLine = smoothLine(series((p) => p.blended_value))

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'ArrowRight') onSelect(Math.min(n - 1, selectedIndex + 1))
    else if (event.key === 'ArrowLeft') onSelect(Math.max(0, selectedIndex - 1))
    else return
    event.preventDefault()
  }

  const rowLabel = (top: number, text: string) => (
    <span className="absolute left-0 -translate-y-1/2 text-[10px] font-semibold uppercase tracking-wider text-mist" style={{ top }}>{text}</span>
  )

  return (
    <div ref={measureRef} className="w-full">
      <div className="flex">
        {/* Row labels stay in place while the hours scroll. */}
        {gutter > 0 && (
          <div className="relative shrink-0" style={{ width: gutter, height }} aria-hidden="true">
            {rowLabel(ROW.time, 'Time')}
            {rowLabel(ROW.value, unit)}
            {rowLabel(ROW.chartTop + chartH / 2, 'Models')}
            {hasRainRow && rowLabel(rainY, 'Rain mm')}
            {rowLabel(spreadY, 'Agreement')}
          </div>
        )}
        <div
          ref={scrollRef}
          className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain rounded-xl [scrollbar-width:thin]"
          tabIndex={0}
          onKeyDown={onKeyDown}
          role="group"
          aria-label={`Hourly ${blend.variable} timeline: TrustCast forecast, the four model forecasts and the forecast range. Use the arrow keys to move between hours.`}
        >
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block">
            {/* Selected column and current hour */}
            <rect x={selectedIndex * colW} y={0} width={colW} height={height} rx={10} fill={BLEND_HEX} fillOpacity="0.07" />
            {nowIndex >= 0 && (
              <line x1={nowIndex * colW} x2={nowIndex * colW} y1={ROW.chartTop - 6} y2={chartBottom} stroke="rgba(255,255,255,0.25)" strokeDasharray="2 4" />
            )}

            {/* Day, time and blended-value rows */}
            {points.map((p, i) => {
              const newDay = i === 0 || dayKey(p.valid_time) !== dayKey(points[i - 1].valid_time)
              const selected = i === selectedIndex
              return (
                <g key={p.valid_time}>
                  {newDay && (
                    <>
                      {i > 0 && <line x1={i * colW} x2={i * colW} y1={4} y2={height - 4} stroke="rgba(255,255,255,0.10)" />}
                      <text x={i * colW + 6} y={ROW.day} fontSize="10" fontWeight="700" fill="#c9d2e3" letterSpacing="0.08em">{dayLabel(p.valid_time).toUpperCase()}</text>
                    </>
                  )}
                  <text x={x(i)} y={ROW.time} textAnchor="middle" fontSize="11" fill={selected ? '#ffffff' : '#8b96ad'} className="num">
                    {i === nowIndex ? 'Now' : timeLabel(p.valid_time)}
                  </text>
                  <text x={x(i)} y={ROW.value} textAnchor="middle" fontSize={selected ? 14 : 13} fontWeight={selected ? 700 : 500} fill={selected ? BLEND_HEX : '#e6eaf2'} className="num">
                    {p.blended_value === null ? '–' : shortValue(p.blended_value)}
                  </text>
                </g>
              )
            })}

            {/* Chart */}
            {[0.25, 0.5, 0.75].map((f) => (
              <line key={f} x1={0} x2={width} y1={ROW.chartTop + chartH * f} y2={ROW.chartTop + chartH * f} stroke="rgba(255,255,255,0.05)" />
            ))}
            {hasRange && (
              <path
                d={smoothBand(series((p) => bands.get(p.valid_time)?.historical_lower), series((p) => bands.get(p.valid_time)?.historical_upper))}
                fill={BLEND_HEX} fillOpacity="0.13"
              />
            )}
            {isRain && points.map((p, i) => p.blended_value !== null && p.blended_value > 0 && (
              <rect
                key={p.valid_time}
                x={x(i) - colW * 0.22} width={colW * 0.44}
                y={y(p.blended_value)} height={Math.max(1, chartBottom - y(p.blended_value))}
                rx={3} fill={BLEND_HEX} fillOpacity={i === selectedIndex ? 0.9 : 0.55}
              />
            ))}
            {models.map((m) => (
              <path key={m} d={smoothLine(series((p) => p.contributors[m]))} fill="none" stroke={modelHex(m)} strokeWidth="1.3" strokeOpacity="0.5" />
            ))}
            {!isRain && (
              <>
                <path d={blendLine} fill="none" stroke={BLEND_HEX} strokeWidth="10" strokeOpacity="0.08" strokeLinecap="round" />
                <path d={blendLine} pathLength={1} className="draw" fill="none" stroke={BLEND_HEX} strokeWidth="3.2" strokeLinecap="round" />
              </>
            )}
            {points.map((p, i) => p.blended_value !== null && (i === selectedIndex || !isRain) && (
              <circle
                key={p.valid_time}
                cx={x(i)} cy={y(p.blended_value)}
                r={i === selectedIndex ? 5.5 : 2.2}
                fill={BLEND_HEX} fillOpacity={i === selectedIndex ? 1 : 0.7}
                stroke={i === selectedIndex ? '#0b1120' : 'none'} strokeWidth="2"
              />
            ))}

            {/* Rain row: mean of the contributing models */}
            {hasRainRow && points.map((p, i) => {
              const rain = rainByTime.get(p.valid_time)
              if (rain === undefined) return null
              const wet = rain >= 0.1
              return (
                <g key={p.valid_time} opacity={wet ? 1 : 0.4}>
                  <path
                    d={`M${x(i) - 9},${rainY - 6} c2,3 3.5,5 3.5,6.5 a3.5,3.5 0 0 1 -7,0 c0,-1.5 1.5,-3.5 3.5,-6.5z`}
                    fill={wet ? RAIN_HEX : 'none'} stroke={RAIN_HEX} strokeWidth="1"
                  />
                  <text x={x(i) + 5} y={rainY + 4} textAnchor="middle" fontSize="10.5" fill={wet ? '#cfe6f5' : '#6b778f'} className="num">{rain.toFixed(1)}</text>
                </g>
              )
            })}

            {/* Model disagreement row */}
            {points.map((p, i) => {
              const level = bands.get(p.valid_time)?.disagreement_level
              return (
                <rect
                  key={p.valid_time}
                  x={i * colW + 3} width={colW - 6} y={spreadY - 3} height={6} rx={3}
                  fill={level ? LEVEL_HEX[level] : 'rgba(255,255,255,0.08)'} fillOpacity={i === selectedIndex ? 1 : 0.6}
                />
              )
            })}

            {/* Hit areas */}
            {points.map((p, i) => (
              <rect key={p.valid_time} x={i * colW} y={0} width={colW} height={height} fill="transparent" className="cursor-pointer" onClick={() => onSelect(i)}>
                <title>{formatTime(p.valid_time)}{p.blended_value === null ? '' : ` · TrustCast ${fmt(p.blended_value)} ${unit}`}</title>
              </rect>
            ))}
          </svg>
        </div>
      </div>

      <ul className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-mist">
        <li className="flex items-center gap-2 font-semibold text-cream">
          {isRain
            ? <span className="inline-block h-3 w-2 rounded-sm" style={{ background: BLEND_HEX }} aria-hidden="true" />
            : <span className="inline-block h-1 w-6 rounded" style={{ background: BLEND_HEX }} aria-hidden="true" />}
          TrustCast
        </li>
        {models.map((m) => (
          <li key={m} className="flex items-center gap-2" title={m}>
            <span className="inline-block h-0.5 w-5 rounded" style={{ background: modelHex(m), opacity: 0.8 }} aria-hidden="true" />{shortName(m)}
          </li>
        ))}
        {hasRange && (
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-6 rounded-sm" style={{ background: BLEND_HEX, opacity: 0.25 }} aria-hidden="true" />Forecast range</li>
        )}
        {hasRainRow && (
          <li className="flex items-center gap-2"><span className="inline-block h-2 w-2 rounded-full" style={{ background: RAIN_HEX }} aria-hidden="true" />Rain (mm)</li>
        )}
        <li className="flex flex-wrap items-center gap-3">
          {(['LOW', 'MEDIUM', 'HIGH'] as const).map((l) => (
            <span key={l} className="flex items-center gap-1"><span className="inline-block h-1.5 w-3.5 rounded-full" style={{ background: LEVEL_HEX[l] }} aria-hidden="true" />{AGREEMENT[l].short}</span>
          ))}
        </li>
      </ul>
    </div>
  )
}
