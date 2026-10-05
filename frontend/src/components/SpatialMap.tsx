import { useState } from 'react'
import { LEVEL_HEX, fmt, modelHex, shortName, useElementWidth } from '../lib'
import type { Location, RiskLevel, SpatialCell, SpatialLayer } from '../types'

export type MapMetric = 'dominant' | 'skill' | 'risk'

type Props = {
  weights: SpatialLayer | null
  risk: SpatialLayer | null
  metric: MapMetric
  markers: Location[]
  selected?: { name: string; latitude: number; longitude: number } | null
}

const LON0 = 67
const LON1 = 98
const LAT0 = 6
const LAT1 = 38
const COS = Math.cos((22 * Math.PI) / 180) // equirectangular scaled at India's mid-latitude
const RISK_ORDER: Record<string, number> = { NORMAL: 0, ELEVATED: 1, HIGH: 2 }
const BALANCED_HEX = '#a7b0c2'

function skillHex(s: number | null | undefined) {
  if (s === null || s === undefined) return 'rgba(255,255,255,0.06)'
  const c = Math.max(-0.3, Math.min(0.3, s)) / 0.3
  return c >= 0 ? `rgba(124,201,166,${0.25 + 0.7 * c})` : `rgba(229,123,114,${0.25 + 0.7 * -c})`
}

function worstRisk(cell: SpatialCell): RiskLevel | null {
  const levels = Object.values(cell.risks ?? {}).map((r) => r.level).filter((l): l is RiskLevel => !!l)
  return levels.length ? levels.reduce((a, b) => (RISK_ORDER[b] > RISK_ORDER[a] ? b : a)) : null
}

/**
 * Grid-cell map of precomputed results (no basemap, no boundary lines: TrustCast draws cells, not borders).
 * Every colour comes from the stored values for that cell.
 */
export function SpatialMap({ weights, risk, metric, markers, selected }: Props) {
  const [ref, measured] = useElementWidth<HTMLDivElement>()
  const [active, setActive] = useState<string | null>(null)
  const width = Math.max(280, measured)
  const k = width / ((LON1 - LON0) * COS)
  const height = (LAT1 - LAT0) * k
  const x = (lon: number) => (lon - LON0) * COS * k
  const y = (lat: number) => (LAT1 - lat) * k
  const layer = metric === 'risk' ? risk : weights
  const cells = layer?.cells ?? []
  const byId = new Map(cells.map((c) => [c.id, c]))
  const activeCell = active ? byId.get(active) ?? null : null
  const riskCell = active && risk ? risk.cells.find((c) => c.id === active) ?? null : null
  const weightCell = active && weights ? weights.cells.find((c) => c.id === active) ?? null : null

  const fill = (c: SpatialCell) => {
    if (c.status !== 'ok') return 'rgba(255,255,255,0.04)'
    if (metric === 'dominant') {
      const d = c.live?.dominant
      return d ? (d === 'Balanced' ? BALANCED_HEX : modelHex(d)) : 'rgba(255,255,255,0.06)'
    }
    if (metric === 'skill') return skillHex(c.skill?.skill_vs_equal)
    const level = worstRisk(c)
    return level ? LEVEL_HEX[level] : 'rgba(255,255,255,0.06)'
  }
  const opacity = (c: SpatialCell) => (metric === 'skill' ? 1 : metric === 'risk' && worstRisk(c) === 'NORMAL' ? 0.35 : 0.8)

  if (layer?.status === 'unavailable' || !cells.length) {
    return <div ref={ref}><p className="text-sm text-mist">{layer?.reason ?? 'Regional results are not available yet.'}</p></div>
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
      <div ref={ref} className="lg:col-span-8">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block max-w-full" role="img" aria-label={`Grid map of ${metric === 'dominant' ? 'dominant model' : metric === 'skill' ? 'skill versus equal weighting' : 'forecast-based risk'} per 1.5° cell`}>
          {[10, 15, 20, 25, 30, 35].map((lat) => (
            <g key={lat}>
              <line x1={0} x2={width} y1={y(lat)} y2={y(lat)} stroke="rgba(255,255,255,0.05)" />
              <text x={4} y={y(lat) - 3} fontSize="9" fill="#6b778f">{lat}°N</text>
            </g>
          ))}
          {[70, 75, 80, 85, 90, 95].map((lon) => (
            <g key={lon}>
              <line y1={0} y2={height} x1={x(lon)} x2={x(lon)} stroke="rgba(255,255,255,0.05)" />
              <text x={x(lon) + 3} y={height - 4} fontSize="9" fill="#6b778f">{lon}°E</text>
            </g>
          ))}
          {cells.map((c) => (
            <rect
              key={c.id}
              x={x(c.west) + 0.5} y={y(c.north) + 0.5}
              width={Math.max(1, x(c.east) - x(c.west) - 1)} height={Math.max(1, y(c.south) - y(c.north) - 1)}
              rx={2}
              fill={fill(c)} fillOpacity={opacity(c)}
              stroke={c.id === active ? '#fbf1de' : 'none'} strokeWidth={2}
              className="cursor-pointer"
              onClick={() => setActive(c.id)}
            >
              <title>{`${c.latitude.toFixed(2)}°N ${c.longitude.toFixed(2)}°E`}</title>
            </rect>
          ))}
          {markers.map((m) => (
            <g key={m.name} pointerEvents="none">
              <circle cx={x(m.longitude)} cy={y(m.latitude)} r={2.5} fill="#ffffff" />
              <text x={x(m.longitude) + 5} y={y(m.latitude) + 3} fontSize="10" fill="#e6eaf2">{m.name}</text>
            </g>
          ))}
          {selected && (
            <g pointerEvents="none">
              <circle cx={x(selected.longitude)} cy={y(selected.latitude)} r={5} fill="none" stroke="#fbf1de" strokeWidth={2} />
              <text x={x(selected.longitude) + 8} y={y(selected.latitude) - 6} fontSize="11" fontWeight="700" fill="#fbf1de">{selected.name}</text>
            </g>
          )}
        </svg>
        <Legend metric={metric} models={weights?.models ?? []} />
      </div>

      <aside className="card-soft p-4 text-xs text-mist lg:col-span-4" aria-live="polite">
        {!activeCell ? (
          <p>Select a grid cell to see its details.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-white">Cell {activeCell.latitude.toFixed(2)}°N, {activeCell.longitude.toFixed(2)}°E</p>
            <p>{activeCell.south}–{activeCell.north}°N · {activeCell.west}–{activeCell.east}°E · land {Math.round(activeCell.land_fraction * 100)}%</p>
            {metric === 'risk' ? (
              riskCell?.risks ? (
                <ul className="space-y-1">
                  {Object.entries(riskCell.risks).map(([type, r]) => (
                    <li key={type} className="flex justify-between gap-2">
                      <span className="text-slate-200">{type.replace('_', ' ').toLowerCase()}</span>
                      <span style={{ color: r.level ? LEVEL_HEX[r.level] : undefined }}>{r.level ?? 'n/a'} · {fmt(r.value)} {r.unit}</span>
                    </li>
                  ))}
                </ul>
              ) : <p>No risk data for this cell.</p>
            ) : weightCell?.status === 'ok' && weightCell.live && weightCell.skill ? (
              <>
                <p>
                  {weights?.variable} · Day {weights?.lead_day} · dominant: <span className="text-white">{weightCell.live.dominant}</span>
                  {weightCell.regime && ` · regime ${weightCell.regime.toLowerCase().replace('_', ' ')}`}
                </p>
                <ul className="space-y-1.5">
                  {Object.entries(weightCell.live.weights).map(([m, w]) => (
                    <li key={m}>
                      <div className="flex justify-between"><span>{shortName(m)}</span><span className="num text-white">{(w * 100).toFixed(1)}%</span></div>
                      <div className="mt-0.5 h-1.5 rounded-full bg-white/8"><div className="h-1.5 rounded-full" style={{ width: `${w * 100}%`, background: modelHex(m) }} /></div>
                    </li>
                  ))}
                </ul>
                <dl className="num grid grid-cols-[1fr_auto] gap-x-3 gap-y-1">
                  <dt>TrustCast RMSE</dt><dd className="text-right text-white">{fmt(weightCell.skill.trustcast_rmse, 2)} {weights?.unit}</dd>
                  <dt>Equal-weight RMSE</dt><dd className="text-right">{fmt(weightCell.skill.equal_rmse, 2)}</dd>
                  <dt>Best single RMSE</dt><dd className="text-right">{fmt(weightCell.skill.best_single_rmse, 2)}</dd>
                  <dt>Skill vs equal</dt><dd className="text-right">{pct(weightCell.skill.skill_vs_equal)}</dd>
                  <dt>Skill vs best single</dt><dd className="text-right">{pct(weightCell.skill.skill_vs_best_single)}</dd>
                  {Object.entries(weightCell.skill.model_rmse).map(([m, v]) => (
                    <div key={m} className="contents"><dt>{shortName(m)} RMSE</dt><dd className="text-right">{fmt(v, 2)}</dd></div>
                  ))}
                  <dt>Evaluation</dt><dd className="text-right">{weightCell.evaluation_days} days · {weightCell.common_hours} h</dd>
                  <dt>Weights level</dt><dd className="text-right">{weightCell.live.level}</dd>
                  <dt>Trained to</dt><dd className="text-right">{weightCell.live.training_end}</dd>
                </dl>
              </>
            ) : (
              <p>{weightCell?.reason ?? 'Insufficient data for this cell.'}</p>
            )}
          </div>
        )}
      </aside>
    </div>
  )
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? 'N/A' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

function Legend({ metric, models }: { metric: MapMetric; models: string[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-mist">
      {metric === 'dominant' && (
        <>
          {models.map((m) => <li key={m} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: modelHex(m) }} />{shortName(m)}</li>)}
          <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: BALANCED_HEX }} />Balanced (no clear leader)</li>
        </>
      )}
      {metric === 'skill' && (
        <>
          <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: skillHex(-0.3) }} />Worse than equal weighting</li>
          <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: skillHex(0.3) }} />Better than equal weighting</li>
          <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-white/10" />Insufficient data</li>
        </>
      )}
      {metric === 'risk' && (['NORMAL', 'ELEVATED', 'HIGH'] as const).map((l) => (
        <li key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: LEVEL_HEX[l] }} />{l.charAt(0) + l.slice(1).toLowerCase()}</li>
      ))}
    </ul>
  )
}
