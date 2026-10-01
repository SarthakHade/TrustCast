import { BLEND_HEX, VARIABLE_LABEL, fmt, formatTime, humanize, modelHex, nowIndexOf, selectedIndexOf } from '../lib'
import type { BlendResponse, UncertaintyResponse, Variable } from '../types'
import { ForecastChart } from './charts'
import { Loading, ModelDot, Notice, SectionHeader, StatusPill } from './ui'

type Props = {
  blend: BlendResponse | null
  uncertainty: UncertaintyResponse | null
  loading: boolean
  error: string
  locationName: string
  selectedTime: string | null
  openedAt: number
  onSelectTime: (time: string) => void
}

export function Blend({ blend, uncertainty, loading, error, locationName, selectedTime, openedAt, onSelectTime }: Props) {
  const points = blend?.forecast ?? []
  const nowIndex = nowIndexOf(points, openedAt)
  const selectedIndex = selectedIndexOf(points, selectedTime, openedAt)
  const selected = points[selectedIndex]
  const unc = uncertainty?.forecast.find((u) => u.valid_time === selected?.valid_time)
  const unit = blend?.unit ?? ''
  const variableLabel = blend ? (VARIABLE_LABEL[blend.variable as Variable] ?? humanize(blend.variable)) : ''
  const contributing = blend?.models_used.length ?? 0
  const title = contributing ? `${contributing}-model trust-weighted blend` : 'Trust-weighted blended forecast'

  return (
    <section id="blend" aria-labelledby="blend-title" className="scroll-mt-6">
      <SectionHeader index="04" question="What does the blended forecast say?" title={title}>
        <p className="max-w-md text-sm text-mist">
          TrustCast combines the available model forecasts hour by hour using the Trust Engine weights. Models with stronger measured performance contribute more.
        </p>
      </SectionHeader>
      <h2 id="blend-title" className="sr-only">Trust-weighted blended forecast</h2>

      {loading && <Loading>Blending forecasts for {locationName}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {blend?.message && !loading && <Notice>{blend.message}</Notice>}

      {blend && !loading && blend.status === 'ok' && selected && (
        <div
          className="card p-5 sm:p-8"
          style={{ background: 'linear-gradient(165deg, rgba(150,78,52,0.38) 0%, rgba(40,44,70,0.35) 45%, rgba(46,86,130,0.32) 100%)' }}
        >
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <p className="eyebrow text-cream/80">TrustCast · {blend.location} · {variableLabel} · {contributing} contributing models</p>
              <p className="num mt-3 text-6xl font-extralight tracking-tighter text-white sm:text-8xl">
                {fmt(selected.blended_value)}<span className="ml-1 align-top text-2xl font-light text-white/70 sm:text-3xl">{unit}</span>
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <label className="flex items-center gap-2 text-mist">
                  <span className="sr-only sm:not-sr-only">Valid</span>
                  <select className="field !w-auto !py-1.5 !text-sm" value={selected.valid_time} onChange={(e) => onSelectTime(e.target.value)} aria-label="Valid time">
                    {points.map((p) => <option key={p.valid_time} value={p.valid_time}>{formatTime(p.valid_time)}</option>)}
                  </select>
                </label>
                {unc?.historical_lower !== null && unc?.historical_lower !== undefined && (
                  <span className="num text-slate-200">Prediction range <span className="font-semibold text-cream">{fmt(unc.historical_lower)} – {fmt(unc.historical_upper)} {unit}</span></span>
                )}
              </div>
              <p className="mt-2 text-xs text-mist">{points.length} hourly steps · {blend.forecast_days} day{blend.forecast_days === 1 ? '' : 's'} · weights from Day {blend.trust_lead_day} verification</p>
            </div>

            <div className="lg:col-span-5">
              <p className="eyebrow">Model contribution</p>
              <ul className="mt-3 space-y-3">
                {[...blend.models_used].sort((a, b) => b.trust_weight - a.trust_weight).map((m) => (
                  <li key={m.model}>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex min-w-0 items-center gap-2 text-slate-200"><ModelDot hex={modelHex(m.model)} /><span className="truncate">{m.model}</span></span>
                      <span className="num font-semibold text-white">{(m.trust_weight_percent ?? m.trust_weight * 100).toFixed(1)}%</span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-white/10"><div className="h-1.5 rounded-full" style={{ width: `${m.trust_weight * 100}%`, background: modelHex(m.model) }} /></div>
                  </li>
                ))}
              </ul>
              {blend.excluded_models.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {blend.excluded_models.map((m) => (
                    <span key={m.model} className="flex items-center gap-2 rounded-full border border-dashed border-white/12 px-2.5 py-1 text-xs text-mist" title={m.reason}>
                      {m.model}<StatusPill status={m.status} />
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-3 text-xs text-mist/80">Only models with a valid forecast and a trust weight contribute to the blend.</p>
            </div>
          </div>

          <div className="mt-8">
            <ForecastChart blend={blend} uncertainty={uncertainty} selectedIndex={selectedIndex} nowIndex={nowIndex} onSelect={(i) => onSelectTime(points[i].valid_time)} />
          </div>

          <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div className="card-soft p-5 lg:col-span-7">
              <p className="eyebrow">How TrustCast produced {formatTime(selected.valid_time)}</p>
              {selected.status === 'ok' && selected.blended_value !== null ? (
                <table className="num mt-4 w-full text-sm">
                  <caption className="sr-only">Blend calculation for the selected hour</caption>
                  <tbody>
                    {Object.entries(selected.contributors).map(([model, value]) => (
                      <tr key={model} className="border-b border-white/5">
                        <th scope="row" className="py-2 pr-2 text-left font-medium" style={{ color: modelHex(model) }}>{model}</th>
                        <td className="py-2 pr-2 text-right text-slate-300">{fmt(value)} × {(selected.effective_weights[model] * 100).toFixed(1)}%</td>
                        <td className="py-2 text-right text-mist">{(value * selected.effective_weights[model]).toFixed(2)}</td>
                      </tr>
                    ))}
                    <tr>
                      <th scope="row" className="pt-3 text-left font-semibold" style={{ color: BLEND_HEX }}>TrustCast</th>
                      <td className="pt-3 pr-2 text-right text-xs text-mist">Σ weighted values</td>
                      <td className="pt-3 text-right text-lg font-bold" style={{ color: BLEND_HEX }}>{fmt(selected.blended_value)} {unit}</td>
                    </tr>
                  </tbody>
                </table>
              ) : (
                <p className="mt-3 text-sm text-rose-200">No model has a value at this hour, so no blended value is produced.</p>
              )}
              {selected.renormalized && (
                <p className="mt-3 text-xs text-amberish">A model has no value at this hour, so the remaining weights were renormalised to 100%.</p>
              )}
            </div>
            <div className="card-soft p-5 text-xs text-mist lg:col-span-5">
              <p className="eyebrow">Method</p>
              <ul className="num mt-3 space-y-1.5 font-mono text-[11px] leading-relaxed text-slate-300">
                {blend.formula.map((line) => <li key={line} className="break-words">{line}</li>)}
              </ul>
              <p className="mt-3 leading-relaxed">Forecasts are aligned by valid time; values from different hours are never mixed. Values are kept at full precision and rounded only for display.</p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
