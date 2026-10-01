import type { ReactNode } from 'react'
import { LEVEL_HEX, fmt, formatDay, formatShort, formatTime } from '../lib'
import type { RiskIndicator, RiskResponse } from '../types'
import { AlertIcon, LevelBadge, Loading, Notice, RainIcon, SectionHeader, SnowIcon, ThermometerIcon, WindIcon } from './ui'

const ICON: Record<string, (cls: string) => ReactNode> = {
  HEAT: (cls) => <ThermometerIcon className={cls} />,
  COLD: (cls) => <SnowIcon className={cls} />,
  HEAVY_RAIN: (cls) => <RainIcon className={cls} />,
  HIGH_WIND: (cls) => <WindIcon className={cls} />,
}
const TINT: Record<string, string> = {
  HEAT: 'rgba(214,120,80,0.20)',
  COLD: 'rgba(120,170,230,0.20)',
  HEAVY_RAIN: 'rgba(90,140,200,0.20)',
  HIGH_WIND: 'rgba(130,190,180,0.18)',
}

type Props = { risks: RiskResponse | null; loading: boolean; error: string; locationName: string }

export function Risk({ risks, loading, error, locationName }: Props) {
  const available = risks?.risks.filter((r) => r.status === 'ok') ?? []
  const times = available[0]?.timeline.map((p) => p.valid_time) ?? []

  return (
    <section id="risk" aria-labelledby="risk-title" className="scroll-mt-6">
      <SectionHeader index="06" question="Is there an extreme-weather risk?" title="Extreme Weather & Risk">
        <div className="flex max-w-md flex-col gap-2">
          <span className="inline-flex w-fit items-center gap-2 rounded-full border border-amberish/40 bg-amberish/10 px-3 py-1 text-xs font-bold text-amberish">
            <AlertIcon className="h-4 w-4" /> Forecast-based risk indicator — not an official warning.
          </span>
          <p className="text-sm text-mist">
            {risks?.source_label ?? 'Based on current TrustCast forecast'}
            {risks?.horizon_start && risks.horizon_end && ` · ${formatShort(risks.horizon_start)} – ${formatShort(risks.horizon_end)}`}
          </p>
        </div>
      </SectionHeader>
      <h2 id="risk-title" className="sr-only">Extreme Weather and Risk</h2>

      {loading && <Loading>Checking risk thresholds for {locationName}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {risks?.message && !loading && <Notice>{risks.message}</Notice>}

      {risks && !loading && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {risks.risks.map((r) => (r.status !== 'ok' || !r.level ? <UnavailableRisk key={r.risk_type} risk={r} /> : <RiskCard key={r.risk_type} risk={r} />))}
          </div>

          {available.length > 0 && times.length > 0 && (
            <div className="card mt-4 p-5 sm:p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-semibold text-white">Risk timeline · next {times.length} h</p>
                <p className="text-xs text-mist">{formatDay(times[0])} → {formatDay(times[times.length - 1])}</p>
              </div>
              <div className="mt-4 space-y-2.5">
                {available.map((r) => {
                  const counts = { NORMAL: 0, ELEVATED: 0, HIGH: 0 }
                  r.timeline.forEach((p) => { counts[p.level] += 1 })
                  return (
                    <div key={r.risk_type} className="grid grid-cols-1 gap-1.5 sm:grid-cols-[10rem_1fr] sm:items-center sm:gap-4">
                      <span className="flex items-center gap-2 text-xs text-slate-300">
                        {ICON[r.risk_type]?.('h-4 w-4 text-mist')}{r.title}
                      </span>
                      <div
                        className="flex h-5 gap-[2px]"
                        role="img"
                        aria-label={`${r.title}: ${counts.NORMAL} normal, ${counts.ELEVATED} elevated, ${counts.HIGH} high hours`}
                      >
                        {r.timeline.map((p) => (
                          <span
                            key={p.valid_time}
                            className="min-w-0 flex-1 rounded-[3px]"
                            style={{ background: LEVEL_HEX[p.level], opacity: p.level === 'NORMAL' ? 0.45 : 0.95 }}
                            title={`${formatTime(p.valid_time)} · ${p.value.toFixed(1)} ${r.unit}${r.aggregation === 'sum_24h' ? ' (trailing total)' : ''} · ${p.level}`}
                          />
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
              <ul className="mt-4 flex flex-wrap gap-4 text-xs text-mist">
                {(['NORMAL', 'ELEVATED', 'HIGH'] as const).map((l) => (
                  <li key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: LEVEL_HEX[l] }} aria-hidden="true" />{l}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="mt-4 text-xs leading-relaxed text-mist">
            {risks.disclaimer} Levels come from the TrustCast blended forecast. The uncertainty range comes from the Forecast Uncertainty step; for 24 h rainfall it is the spread of each model's own 24 h total. Model consensus counts the contributing models whose own forecast crosses the threshold; it is not a probability.
          </p>
        </>
      )}
    </section>
  )
}

function RiskCard({ risk: r }: { risk: RiskIndicator }) {
  const level = r.level ?? 'NORMAL'
  const cmp = r.direction === 'above' ? '≥' : '≤'
  const shownThreshold = level === 'HIGH' ? r.thresholds.HIGH : r.thresholds.ELEVATED
  return (
    <article
      className="card flex flex-col p-5 sm:p-6"
      style={{ background: `radial-gradient(110% 80% at 100% 0%, ${TINT[r.risk_type] ?? 'rgba(255,255,255,0.08)'}, transparent 60%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))`, borderColor: level === 'NORMAL' ? undefined : `${LEVEL_HEX[level]}66` }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="text-cream/85">{ICON[r.risk_type]?.('h-8 w-8')}</span>
          <h3 className="text-base font-semibold leading-tight text-white">{r.title}</h3>
        </div>
        <LevelBadge level={level} hex={LEVEL_HEX[level]} size="md" />
      </div>

      <p className="num mt-5 text-5xl font-extralight tracking-tight text-white">
        {fmt(r.forecast_value)}<span className="ml-1 text-lg text-white/60">{r.unit}</span>
      </p>
      <p className="text-xs text-mist">
        {r.aggregation === 'sum_24h'
          ? `${r.accumulation_hours} h total ending ${r.peak_time ? formatShort(r.peak_time) : ''}`
          : `${r.direction === 'above' ? 'Peak' : 'Lowest'} at ${r.peak_time ? formatShort(r.peak_time) : ''}`}
      </p>

      <dl className="num mt-5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-xs">
        <dt className="text-mist" title={r.range_source ?? undefined}>Uncertainty range</dt>
        <dd className="text-right font-semibold text-slate-100">{fmt(r.lower)} – {fmt(r.upper)} {r.unit}</dd>
        <dt className="text-mist">Threshold</dt>
        <dd className="text-right font-semibold text-slate-100">{cmp} {shownThreshold} {r.unit}</dd>
        <dt className="text-mist">Model consensus</dt>
        <dd className="text-right font-semibold text-slate-100">{r.models_total ? `${r.models_exceeding} / ${r.models_total} models` : '—'}</dd>
      </dl>
      <p className="num mt-2 text-[11px] text-mist">Levels: Elevated {cmp} {r.thresholds.ELEVATED} · High {cmp} {r.thresholds.HIGH} {r.unit}</p>

      {r.threshold_crossing && (
        <p className="mt-4 flex items-start gap-2 rounded-2xl border border-amberish/40 bg-amberish/10 px-3 py-2 text-xs font-semibold text-amber-100">
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-amberish" /> Threshold crossed within forecast uncertainty.
        </p>
      )}

      <ul className="mt-4 space-y-1 border-t border-white/5 pt-3 text-xs leading-relaxed text-mist">
        {r.messages.map((m) => <li key={m}>{m}</li>)}
      </ul>
      <p className="mt-auto pt-3 text-[11px] leading-relaxed text-mist/70">{r.basis}.</p>
    </article>
  )
}

function UnavailableRisk({ risk: r }: { risk: RiskIndicator }) {
  return (
    <article className="flex flex-col rounded-[28px] border border-dashed border-white/12 p-5 sm:p-6">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 text-slate-400">{ICON[r.risk_type]?.('h-8 w-8')}<h3 className="text-base font-semibold">{r.title}</h3></div>
        <span className="text-[11px] font-bold uppercase tracking-wider text-amberish">Data unavailable</span>
      </div>
      <p className="mt-4 text-xs text-mist">{r.reason}</p>
    </article>
  )
}
