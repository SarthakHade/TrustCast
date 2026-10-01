import { VARIABLE_LABEL, fmt, formatDateUtc, modelHex, signed } from '../lib'
import type { ModelPerformance, PerformanceResponse } from '../types'
import { Loading, Notice, SectionHeader, Stat, StatusPill } from './ui'

type Props = { performance: PerformanceResponse | null; loading: boolean; error: string; locationName: string }

export function Verification({ performance, loading, error, locationName }: Props) {
  const scored = performance?.models.filter((m) => m.mae !== null) ?? []
  const unscored = performance?.models.filter((m) => m.mae === null) ?? []
  const best = scored.reduce<ModelPerformance | null>((a, m) => (!a || (m.mae ?? Infinity) < (a.mae ?? Infinity) ? m : a), null)
  const maxMae = Math.max(...scored.map((m) => m.mae ?? 0), 0.001)
  const unit = performance?.unit ?? ''
  const period = performance?.period_start && performance.period_end
    ? `${formatDateUtc(performance.period_start)} – ${formatDateUtc(performance.period_end)} UTC`
    : '—'
  const formula = performance?.skill_method.replace('Inverse-MAE: ', '') ?? ''

  return (
    <section id="verification" aria-labelledby="verification-title" className="scroll-mt-6">
      <SectionHeader index="02" question="Which models have historically performed well?" title="Historical Forecast Verification">
        <p className="max-w-md text-sm text-mist">
          Past forecasts are compared against a historical reference dataset (ERA5 reanalysis).
        </p>
      </SectionHeader>
      <h2 id="verification-title" className="sr-only">Historical Forecast Verification</h2>

      {loading && <Loading>Scoring archived forecasts for {locationName}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}

      {performance && !loading && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-sage/40 bg-sage/10 px-3 py-1 font-bold uppercase tracking-wider text-sage" title={performance.forecast_source}>
              Real archived forecasts
            </span>
            {[performance.location, VARIABLE_LABEL[performance.variable], `Day ${performance.lead_day} lead`, period].map((chip) => (
              <span key={chip} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-200">{chip}</span>
            ))}
          </div>

          <div className={`grid grid-cols-1 gap-4 ${scored.length > 3 ? 'md:grid-cols-2 xl:grid-cols-4' : 'md:grid-cols-3'}`}>
            {scored.map((m) => (
              <article
                key={m.model}
                className="card p-5 sm:p-6"
                style={{ background: `radial-gradient(120% 80% at 0% 0%, ${modelHex(m.model)}24 0%, transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))` }}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-base font-semibold text-white">{m.model}</h3>
                    <p className="text-xs text-mist">{m.model_type}</p>
                  </div>
                  {best?.model === m.model && (
                    <span
                      className="rounded-full border border-cream/40 bg-cream/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cream"
                      title="Lowest MAE for this location, variable, lead time and evaluation period only"
                    >
                      Lowest MAE here
                    </span>
                  )}
                </div>
                <p className="mt-5 text-[11px] font-semibold uppercase tracking-wider text-mist" title="Mean Absolute Error: average size of the error. Lower is better.">Mean absolute error</p>
                <p className="num text-5xl font-extralight tracking-tight text-white">
                  {fmt(m.mae, 2)}<span className="ml-1 text-lg text-white/60">{unit}</span>
                </p>
                <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3">
                  <Stat label="RMSE" value={`${fmt(m.rmse, 2)} ${unit}`} hint="Root Mean Squared Error: penalises large misses more. Lower is better." />
                  <Stat label="Bias" value={`${signed(m.bias)} ${unit}`} hint="Mean of (forecast − reference). Positive = model runs high." />
                  <Stat label="Correlation" value={fmt(m.correlation, 2)} hint="Pearson correlation with the ERA5 reference series." />
                  <Stat label="Samples" value={`${m.samples} h`} hint="Hourly forecast/reference pairs scored." />
                </div>
                <div className="mt-5">
                  <div className="flex justify-between text-[11px] font-semibold uppercase tracking-wider text-mist">
                    <span title={`Relative reliability: normalized inverse MAE, ${formula}`}>Relative reliability</span>
                    <span className="num text-slate-100">{m.skill_score === null ? '—' : `${(m.skill_score * 100).toFixed(1)}%`}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-white/10">
                    <div className="h-1.5 rounded-full" style={{ width: `${(m.skill_score ?? 0) * 100}%`, background: modelHex(m.model) }} />
                  </div>
                </div>
              </article>
            ))}
          </div>

          {unscored.length > 0 && (
            <ul className="mt-4 flex flex-wrap gap-2">
              {unscored.map((m) => (
                <li key={m.model} className="flex items-center gap-2 rounded-full border border-dashed border-white/12 px-3 py-1.5 text-xs text-mist" title={m.note ?? undefined}>
                  <span className="text-slate-300">{m.model}</span>
                  <StatusPill status={m.status} />
                  <span className="hidden sm:inline">{m.status === 'error' ? 'archived data temporarily unavailable' : m.status === 'live' ? 'Forecast live · historical verification unavailable (no archived forecasts)' : 'Historical verification unavailable'}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div className="card p-5 sm:p-6 lg:col-span-7">
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <Bars title={`Mean absolute error (${unit})`} caption="lower is better" rows={scored.map((m) => ({ model: m.model, hex: modelHex(m.model), share: (m.mae ?? 0) / maxMae, label: `${fmt(m.mae, 2)} ${unit}` }))} />
                <Bars title="Relative Reliability" caption="higher is better" rows={scored.map((m) => ({ model: m.model, hex: modelHex(m.model), share: m.skill_score ?? 0, label: `${((m.skill_score ?? 0) * 100).toFixed(1)}%` }))} />
              </div>
              {best && (
                <p className="mt-6 border-t border-white/5 pt-4 text-sm leading-relaxed text-mist">
                  For this location, variable, lead time and evaluation period, <span className="font-semibold text-white">{best.model}</span> had the lowest MAE against the ERA5 reference. This is not a general ranking of the models.
                </p>
              )}
            </div>

            <aside className="card-soft p-5 sm:p-6 lg:col-span-5" aria-label="Verification methodology">
              <p className="eyebrow">Methodology</p>
              <dl className="mt-4 space-y-3 text-sm">
                <Row term="Verification period" detail={period} />
                <Row term="Reference" detail="ERA5 reanalysis" />
                <Row term="Metrics" detail="MAE, RMSE, bias and correlation" />
                <Row term="Relative reliability" detail="Normalized inverse MAE" />
              </dl>
              <details className="mt-4 rounded-2xl border border-white/5 bg-black/20 p-3 text-xs text-mist">
                <summary className="font-semibold text-slate-200">How the numbers are calculated</summary>
                <div className="mt-2 space-y-1.5 leading-relaxed">
                  <p>Each hour pairs the value a model forecast ~{24 * performance.lead_day} h earlier with the ERA5 value for the same valid time. Error = forecast − reference.</p>
                  <p className="num">MAE = mean|e| · RMSE = √mean(e²) · Bias = mean(e) · Relative reliability = {formula}</p>
                  <p>Forecasts: {performance.forecast_source}.</p>
                  <p>Reference: {performance.observation_source}. ERA5 is a gridded reanalysis produced by ECMWF, not a station observation.</p>
                  <p>Relative reliability ranks only the models evaluated here, relative to each other. It is not a standardized skill score.</p>
                </div>
              </details>
            </aside>
          </div>
        </>
      )}
    </section>
  )
}

function Row({ term, detail }: { term: string; detail: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
      <dt className="text-mist">{term}</dt>
      <dd className="num font-semibold text-slate-100 sm:text-right">{detail}</dd>
    </div>
  )
}

function Bars({ title, caption, rows }: { title: string; caption: string; rows: { model: string; hex: string; share: number; label: string }[] }) {
  return (
    <div>
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="text-xs text-mist">{caption}</p>
      <ul className="mt-4 space-y-3">
        {rows.map((r) => (
          <li key={r.model}>
            <div className="flex justify-between gap-2 text-xs">
              <span className="truncate text-slate-300">{r.model}</span>
              <span className="num font-semibold text-slate-100">{r.label}</span>
            </div>
            <div className="mt-1.5 h-2 rounded-full bg-white/8">
              <div className="h-2 rounded-full" style={{ width: `${Math.max(r.share * 100, 2)}%`, background: r.hex }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
