import { VARIABLE_LABEL, fmt, humanize, modelHex } from '../lib'
import type { TrustResponse, Variable } from '../types'
import { WeightRing } from './charts'
import { Loading, Notice, SectionHeader, StatusPill } from './ui'

type Props = { trust: TrustResponse | null; loading: boolean; error: string; locationName: string }

export function TrustEngine({ trust, loading, error, locationName }: Props) {
  const weighted = [...(trust?.models.filter((m) => m.included) ?? [])].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
  const excluded = trust?.models.filter((m) => !m.included) ?? []
  const unit = trust?.unit ?? ''
  const variableLabel = trust ? (VARIABLE_LABEL[trust.variable as Variable] ?? humanize(trust.variable)) : ''

  return (
    <section id="trust" aria-labelledby="trust-title" className="scroll-mt-6">
      <SectionHeader index="03" question="How does TrustCast decide which forecast to trust?" title="Trust Engine">
        <p className="max-w-md text-sm text-mist">
          Measured historical and recent model error is converted into reliability information, then normalised into the weights used for blending.
        </p>
      </SectionHeader>
      <h2 id="trust-title" className="sr-only">Trust Engine</h2>

      {loading && <Loading>Calculating trust for {locationName}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {trust?.message && !loading && <Notice tone={trust.status === 'insufficient_data' ? 'error' : 'warn'}>{trust.message}</Notice>}

      {trust && !loading && weighted.length > 0 && (
        <div className="card p-5 sm:p-8" style={{ background: 'radial-gradient(90% 70% at 0% 0%, rgba(84,120,160,0.22), transparent 60%), radial-gradient(80% 60% at 100% 100%, rgba(200,140,90,0.14), transparent 60%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))' }}>
          {/* Flow: inputs → trust score → weight */}
          <ol className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr] md:items-stretch" aria-label="Trust Engine calculation flow">
            <li className="card-soft p-4">
              <p className="eyebrow">Inputs</p>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-200">
                <li>Historical error <span className="text-mist">· {trust.historical_days}-day RMSE</span></li>
                {trust.recent_days && <li>Recent error <span className="text-mist">· last {trust.recent_days} days RMSE</span></li>}
                <li>Lead-time context <span className="text-mist">· scored at Day {trust.lead_day}</span></li>
              </ul>
            </li>
            <FlowArrow />
            <li className="card-soft p-4">
              <p className="eyebrow">Trust score</p>
              <p className="num mt-2 text-sm leading-relaxed text-slate-200">
                {trust.recent_days ? '0.7 × historical inverse error + 0.3 × recent inverse error' : 'historical inverse error'}
              </p>
              <p className="mt-1 text-xs text-mist">inverse error = 1 / (RMSE + 0.05)</p>
            </li>
            <FlowArrow />
            <li className="card-soft p-4">
              <p className="eyebrow">Dynamic weight</p>
              <p className="mt-2 text-sm text-slate-200">trust score ÷ Σ trust scores</p>
              <p className="mt-1 text-xs text-mist">Only available models count; the weights sum to 100%.</p>
            </li>
          </ol>

          <div className="mt-8">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-semibold text-white">Weights for {trust.location} · {variableLabel} · Day {trust.lead_day}</p>
              <p className="num text-xs text-mist">Total {weighted.reduce((s, m) => s + (m.weight_percent ?? 0), 0).toFixed(1)}% across {weighted.length} models</p>
            </div>
            <div className="mt-3 flex h-4 overflow-hidden rounded-full bg-white/5" role="img" aria-label={weighted.map((m) => `${m.model} ${m.weight_percent?.toFixed(1)}%`).join(', ')}>
              {weighted.map((m) => (
                <div
                  key={m.model}
                  style={{ width: `${(m.weight ?? 0) * 100}%`, background: modelHex(m.model) }}
                  className="h-full border-r-2 border-ink-900 last:border-r-0"
                  title={`${m.model}: ${m.weight_percent?.toFixed(1)}%`}
                />
              ))}
            </div>
          </div>

          <div className={`mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 ${weighted.length > 3 ? 'xl:grid-cols-4' : 'xl:grid-cols-3'}`}>
            {weighted.map((m) => (
              <article key={m.model} className="card-soft flex flex-col p-5">
                <div className="flex items-center gap-4">
                  <WeightRing value={m.weight ?? 0} color={modelHex(m.model)} label={`${m.model} weight ${m.weight_percent?.toFixed(1)} percent`} />
                  <div className="min-w-0">
                    <h3 className="text-base font-semibold text-white">{m.model}</h3>
                    <p className="text-xs text-mist">{m.model_type}</p>
                    <p className="num mt-1 text-xs text-slate-300">Trust score <span className="font-bold text-cream">{fmt(m.trust_score, 2)}</span></p>
                  </div>
                </div>
                <dl className="num mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <dt className="text-mist" title="RMSE over the full evaluation window">Historical RMSE</dt>
                  <dd className="text-right font-semibold text-slate-100">{fmt(m.historical_rmse, 2)} {unit}</dd>
                  <dt className="text-mist" title="RMSE over the most recent days">Recent RMSE</dt>
                  <dd className="text-right font-semibold text-slate-100">{m.recent_rmse === null ? '—' : `${fmt(m.recent_rmse, 2)} ${unit}`}</dd>
                  <dt className="text-mist" title="1 / (historical RMSE + 0.05)">Historical inverse error</dt>
                  <dd className="text-right font-semibold text-slate-100">{fmt(m.historical_skill, 2)}</dd>
                  <dt className="text-mist" title="1 / (recent RMSE + 0.05)">Recent inverse error</dt>
                  <dd className="text-right font-semibold text-slate-100">{fmt(m.recent_skill, 2)}</dd>
                </dl>
                <ul className="mt-4 space-y-1.5 border-t border-white/5 pt-3 text-xs leading-relaxed text-mist">
                  {m.reasons.map((r) => <li key={r} className="flex gap-2"><span aria-hidden="true" className="text-cream/70">›</span><span>{r}</span></li>)}
                </ul>
              </article>
            ))}
          </div>

          {excluded.length > 0 && (
            <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-mist">
              <span>Not weighted:</span>
              {excluded.map((m) => (
                <span key={m.model} className="flex items-center gap-2 rounded-full border border-dashed border-white/12 px-3 py-1" title={m.reasons[0]}>
                  <span className="text-slate-300">{m.model}</span><StatusPill status={m.status} />
                </span>
              ))}
            </div>
          )}

          <details className="mt-6 rounded-2xl border border-white/5 bg-black/20 p-4 text-sm">
            <summary className="font-semibold text-slate-200">Why do the weights differ?</summary>
            <div className="mt-3 grid grid-cols-1 gap-4 text-xs text-mist md:grid-cols-2">
              <ul className="space-y-1.5 leading-relaxed">
                <li>✓ Lower measured error → higher inverse error → higher trust.</li>
                {trust.recent_days && <li>✓ The last {trust.recent_days} days count for 30%, so a model that is currently drifting loses trust.</li>}
                <li>✓ The weights are normalised across available models and sum to 100%.</li>
                <li>✓ Unavailable models are excluded and do not affect the denominator.</li>
                <li>✓ Deterministic: the same data always gives the same weights. No randomness, no hard-coded ranking.</li>
                <li>✓ Weights are specific to this location, variable and lead time. They are not probabilities of correctness.</li>
              </ul>
              <ul className="num space-y-1 font-mono text-[11px] leading-relaxed text-slate-300">
                {trust.formula.map((line) => <li key={line} className="break-words">{line}</li>)}
              </ul>
            </div>
          </details>
        </div>
      )}
    </section>
  )
}

function FlowArrow() {
  return (
    <li aria-hidden="true" className="flex items-center justify-center text-cream/50">
      <svg viewBox="0 0 24 24" className="h-5 w-5 rotate-90 md:rotate-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 12h15M13 6l6 6-6 6" /></svg>
    </li>
  )
}
