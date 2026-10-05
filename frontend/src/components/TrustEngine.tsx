import { PRIMARY_SOURCES, modelHex, shortName } from '../lib'
import type { BlendModel, ModelTrust, TrustResponse } from '../types'
import { Loading, Notice, SectionHeader } from './ui'

type Props = { trust: TrustResponse | null; applied: BlendModel[] | null; loading: boolean; error: string; locationName: string }

/** Words for a model's influence: its rank and its weight relative to the top model (weights come from the backend Trust Engine). */
function influence(rank: number, weight: number, top: number) {
  const ratio = top > 0 ? weight / top : 0
  if (rank === 0) return { label: 'Strongest influence', reason: 'Currently showing the strongest historical performance' }
  if (ratio >= 0.75) return { label: 'Strong influence', reason: 'Currently showing strong historical performance' }
  if (ratio >= 0.5) return { label: 'Moderate influence', reason: 'Contributes a balanced share of the forecast' }
  return { label: 'Supporting influence', reason: 'Useful supporting forecast' }
}

/** Recent form from the backend's recent vs full-period error (same ±10% rule the backend uses for its reasons). */
function recentForm(m: ModelTrust) {
  if (m.recent_rmse === null || m.historical_rmse === null || !m.historical_rmse) return null
  const change = m.recent_rmse / m.historical_rmse - 1
  if (change <= -0.1) return 'Improving recently'
  if (change >= 0.1) return 'Less accurate recently'
  return null
}

export function TrustEngine({ trust, applied, loading, error, locationName }: Props) {
  // Weights actually used by the forecast (bias-corrected adaptive blend when available).
  const appliedWeight = new Map((applied ?? []).map((m) => [m.model, m.trust_weight]))
  const weighted = (trust?.models ?? [])
    .filter((m) => m.included && PRIMARY_SOURCES.includes(m.model))
    .map((m) => (appliedWeight.has(m.model) ? { ...m, weight: appliedWeight.get(m.model) ?? 0 } : m))
    .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
  const top = weighted[0]?.weight ?? 0

  return (
    <section id="trust" aria-labelledby="trust-title" className="scroll-mt-24">
      <SectionHeader index="03" question="Why these models influence the forecast" title="Model influence" titleId="trust-title">
        <p className="max-w-md text-sm text-mist">
          TrustCast gives more influence to the models that have performed better{locationName ? ` in ${locationName}` : ' here'}, and keeps adjusting as their recent accuracy changes.
        </p>
      </SectionHeader>

      {loading && <Loading>Weighing the models…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {trust?.status === 'insufficient_data' && !loading && <Notice>Not enough history yet to weigh the models for this location.</Notice>}

      {trust && !loading && weighted.length > 0 && (
        <div
          className="card reveal p-5 sm:p-8"
          style={{ background: 'radial-gradient(90% 70% at 0% 0%, rgba(84,120,160,0.22), transparent 60%), radial-gradient(80% 60% at 100% 100%, rgba(200,140,90,0.14), transparent 60%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))' }}
        >
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-center">
            <ol className="space-y-5 lg:col-span-7">
              {weighted.map((m, i) => {
                const inf = influence(i, m.weight ?? 0, top)
                const form = recentForm(m)
                return (
                  <li key={m.model} className="flex items-start gap-4">
                    <span className="num mt-0.5 w-5 shrink-0 text-sm text-cream/60">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="flex items-center gap-2 text-base font-semibold text-white">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ background: modelHex(m.model) }} aria-hidden="true" />{m.model}
                        </span>
                        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-semibold text-slate-200">{inf.label}</span>
                      </p>
                      <p className="mt-1 text-sm text-mist">{inf.reason}{form ? ` · ${form}` : ''}</p>
                    </div>
                  </li>
                )
              })}
            </ol>

            <div className="card-soft p-5 lg:col-span-5" aria-label="Influence on the TrustCast forecast, from most to least">
              <p className="eyebrow">More influence</p>
              <ul className="mt-4 space-y-3">
                {weighted.map((m) => (
                  <li key={m.model} className="flex items-center gap-3">
                    <span className="w-12 shrink-0 text-sm text-slate-200">{shortName(m.model)}</span>
                    <span className="h-2 flex-1 rounded-full bg-white/8">
                      <span
                        className="block h-2 rounded-full"
                        style={{ width: `${top ? ((m.weight ?? 0) / top) * 100 : 0}%`, background: `linear-gradient(90deg, ${modelHex(m.model)}88, ${modelHex(m.model)})` }}
                      />
                    </span>
                  </li>
                ))}
              </ul>
              <p className="eyebrow mt-4 text-right">Less influence</p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
