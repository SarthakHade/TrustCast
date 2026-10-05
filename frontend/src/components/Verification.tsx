import { PERFORMANCE_HEX, PRIMARY_SOURCES, VARIABLE_LABEL, modelHex, performanceLabel, type PerformanceLabel } from '../lib'
import type { PerformanceResponse } from '../types'
import { Loading, Notice, SectionHeader } from './ui'

type Props = { performance: PerformanceResponse | null; loading: boolean; error: string; locationName: string }

const LEVELS: PerformanceLabel[] = ['Limited', 'Moderate', 'Good', 'Strong']
const SUMMARY: Record<PerformanceLabel, string> = {
  Strong: 'Strong historical performance',
  Good: 'Good historical performance',
  Moderate: 'Moderate historical performance',
  Limited: 'Limited historical performance',
}

export function Verification({ performance, loading, error, locationName }: Props) {
  const models = PRIMARY_SOURCES.map((name) => performance?.models.find((m) => m.model === name)).filter((m) => m !== undefined)
  const scored = models.filter((m) => m.mae !== null)
  const bestMae = Math.min(...scored.map((m) => m.mae as number))
  const best = scored.find((m) => m.mae === bestMae)
  const rows = [...models].sort((a, b) => (a.mae ?? Infinity) - (b.mae ?? Infinity))
  const days = performance?.period_start && performance.period_end
    ? Math.round((new Date(performance.period_end).getTime() - new Date(performance.period_start).getTime()) / 86400000)
    : null

  return (
    <section id="verification" aria-labelledby="verification-title" className="scroll-mt-24">
      <SectionHeader index="02" question="How have these models done here before?" title="Model track record" titleId="verification-title">
        <p className="max-w-md text-sm text-mist">
          Each model's recent forecasts{days ? ` from the past ${days} days` : ''} were checked against historical weather records{locationName ? ` for ${locationName}` : ''}.
        </p>
      </SectionHeader>

      {loading && <Loading>Checking each model's track record…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}

      {performance && !loading && (
        <div className="reveal grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {rows.map((m) => {
            const label = m.mae === null ? null : performanceLabel(m.mae, bestMae)
            const step = label ? LEVELS.indexOf(label) + 1 : 0
            return (
              <article key={m.model} className="card lift p-5">
                <p className="flex items-center gap-2 text-sm font-semibold text-white">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: modelHex(m.model) }} aria-hidden="true" />
                  {m.model}
                </p>
                {label ? (
                  <>
                    <p className="mt-5 text-2xl font-light text-white">{label}</p>
                    <p className="mt-1 text-xs text-mist">{SUMMARY[label]}</p>
                    <div className="mt-4 flex gap-1.5" role="img" aria-label={`${label}: ${step} of 4`}>
                      {LEVELS.map((l, i) => (
                        <span key={l} className="h-1.5 flex-1 rounded-full" style={{ background: i < step ? PERFORMANCE_HEX[label] : 'rgba(255,255,255,0.08)' }} />
                      ))}
                    </div>
                    {best?.model === m.model && <p className="mt-4 text-xs font-semibold text-cream">Most accurate here recently</p>}
                  </>
                ) : (
                  <p className="mt-5 text-sm text-mist">{m.status === 'error' ? 'Track record temporarily unavailable.' : 'Not enough history yet.'}</p>
                )}
              </article>
            )
          })}
        </div>
      )}

      {performance && !loading && (
        <p className="mt-4 text-xs text-mist">
          {VARIABLE_LABEL[performance.variable]} · ratings compare the four models with each other for this location. They are not a general ranking of the models.
        </p>
      )}
    </section>
  )
}
