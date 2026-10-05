import type { ReactNode } from 'react'
import { LEVEL_HEX, fmt, formatDay, formatShort, formatTime, riskHeadline, riskName, riskWhen } from '../lib'
import type { EnsembleGuidance, EnsembleRisk, RiskIndicator, RiskResponse } from '../types'
import { AlertIcon, LevelBadge, Loading, Notice, RainIcon, SectionHeader, SnowIcon, ThermometerIcon, WindIcon } from './ui'

const ICON: Record<string, (cls: string) => ReactNode> = {
  HEAT: (cls) => <ThermometerIcon className={cls} />,
  COLD: (cls) => <SnowIcon className={cls} />,
  HEAVY_RAIN: (cls) => <RainIcon className={cls} />,
  HIGH_WIND: (cls) => <WindIcon className={cls} />,
}
const TINT: Record<string, string> = {
  HEAT: 'rgba(214,120,80,0.18)',
  COLD: 'rgba(120,170,230,0.18)',
  HEAVY_RAIN: 'rgba(90,140,200,0.18)',
  HIGH_WIND: 'rgba(130,190,180,0.16)',
}

type Props = { risks: RiskResponse | null; ensemble: EnsembleGuidance | null; loading: boolean; error: string; locationName: string }

const ENSEMBLE_PHRASE: Record<string, string> = {
  HEAVY_RAIN: 'rainfall above the heavy-rain threshold',
  HEAT: 'temperatures above the heat threshold',
  COLD: 'temperatures below the cold threshold',
  HIGH_WIND: 'winds above the high-wind threshold',
}

export function Risk({ risks, ensemble, loading, error, locationName }: Props) {
  const available = risks?.risks.filter((r) => r.status === 'ok') ?? []
  const times = available[0]?.timeline.map((p) => p.valid_time) ?? []
  const elevated = available.filter((r) => r.level === 'ELEVATED')

  return (
    <section id="risk" aria-labelledby="risk-title" className="scroll-mt-24">
      <SectionHeader index="06" question="Is any weather to watch out for?" title="Weather risk" titleId="risk-title">
        <p className="max-w-md text-sm text-mist">Forecast-based risk indicator — not an official warning.</p>
      </SectionHeader>

      {loading && <Loading>Checking for weather risks{locationName ? ` in ${locationName}` : ''}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {risks?.message && !loading && <Notice>{risks.message}</Notice>}

      {risks && !loading && (
        <div className="reveal">
          {elevated.length > 0 && (
            <p className="mb-4 flex items-start gap-3 rounded-2xl border border-amberish/30 bg-amberish/[0.07] px-4 py-3 text-sm text-amber-100">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-amberish" />
              <span>
                {elevated.map((r) => `${riskHeadline(r)} ${riskWhen(r)}`).join(' · ')}. Keep an eye on the forecast.
              </span>
            </p>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {risks.risks.map((r) => (r.status !== 'ok' || !r.level ? <UnavailableRisk key={r.risk_type} risk={r} /> : <RiskCard key={r.risk_type} risk={r} ensemble={ensemble?.status === 'ok' ? ensemble.risks?.[r.risk_type] : undefined} />))}
          </div>

          {available.length > 0 && times.length > 0 && (
            <div className="card mt-4 p-5 sm:p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-semibold text-white">Risk over the next {times.length} hours</p>
                <p className="text-xs text-mist">{formatDay(times[0])} → {formatDay(times[times.length - 1])}</p>
              </div>
              <div className="mt-4 space-y-2.5">
                {available.map((r) => (
                  <div key={r.risk_type} className="grid grid-cols-1 gap-1.5 sm:grid-cols-[9rem_1fr] sm:items-center sm:gap-4">
                    <span className="flex items-center gap-2 text-xs text-slate-300">{ICON[r.risk_type]?.('h-4 w-4 text-mist')}{riskName(r)}</span>
                    <div className="flex h-4 gap-[2px]" role="img" aria-label={`${riskName(r)} risk by hour`}>
                      {r.timeline.map((p) => (
                        <span
                          key={p.valid_time}
                          className="min-w-0 flex-1 rounded-[3px]"
                          style={{ background: LEVEL_HEX[p.level], opacity: p.level === 'NORMAL' ? 0.4 : 0.95 }}
                          title={`${formatTime(p.valid_time)} · ${p.level.toLowerCase()}`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <ul className="mt-4 flex flex-wrap gap-4 text-xs text-mist">
                {(['NORMAL', 'ELEVATED', 'HIGH'] as const).map((l) => (
                  <li key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: LEVEL_HEX[l] }} aria-hidden="true" />{l.charAt(0) + l.slice(1).toLowerCase()}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function RiskCard({ risk: r, ensemble }: { risk: RiskIndicator; ensemble?: EnsembleRisk }) {
  const elevated = ensemble?.status === 'ok' ? ensemble.thresholds?.find((t) => t.level === 'ELEVATED') : undefined
  const level = r.level ?? 'NORMAL'
  const peakLabel = r.aggregation === 'sum_24h' ? '24-hour total' : r.direction === 'above' ? 'Peak' : 'Lowest'
  return (
    <article
      className="card lift flex flex-col p-5 sm:p-6"
      style={{ background: `radial-gradient(110% 80% at 100% 0%, ${TINT[r.risk_type] ?? 'rgba(255,255,255,0.08)'}, transparent 60%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))`, borderColor: level === 'NORMAL' ? undefined : `${LEVEL_HEX[level]}66` }}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-200">
          <span className="text-cream/80">{ICON[r.risk_type]?.('h-5 w-5')}</span>{riskName(r)}
        </h3>
        <LevelBadge level={level} hex={LEVEL_HEX[level]} />
      </div>
      <p className="mt-5 text-lg font-light leading-snug text-white">{riskHeadline(r)}</p>
      {elevated && (
        <p className="mt-3 text-xs text-slate-300" title={`NOAA AIGEFS: ${elevated.members_exceeding} of ${elevated.members_valid} members (not calibrated)`}>
          {Math.round(elevated.probability * 100)}% of ensemble members indicate {ENSEMBLE_PHRASE[r.risk_type] ?? 'crossing the threshold'}.
        </p>
      )}
      <p className="num mt-auto pt-4 text-xs text-mist">
        {peakLabel} {fmt(r.forecast_value)} {r.unit}{r.peak_time ? ` · ${formatShort(r.peak_time)}` : ''}
      </p>
    </article>
  )
}

function UnavailableRisk({ risk: r }: { risk: RiskIndicator }) {
  return (
    <article className="flex flex-col rounded-[28px] border border-dashed border-white/12 p-5 sm:p-6">
      <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">{ICON[r.risk_type]?.('h-5 w-5')}{riskName(r)}</h3>
      <p className="mt-5 text-sm text-mist">Not available for this forecast.</p>
    </article>
  )
}
