import { DISAGREEMENT_TEXT, LEVEL_HEX, fmt, formatHour, formatTime, selectedIndexOf, signed } from '../lib'
import type { UncertaintyResponse } from '../types'
import { LevelBadge, Loading, Notice, SectionHeader } from './ui'

type Props = {
  uncertainty: UncertaintyResponse | null
  loading: boolean
  error: string
  selectedTime: string | null
  openedAt: number
  onSelectTime: (time: string) => void
}

export function Uncertainty({ uncertainty, loading, error, selectedTime, openedAt, onSelectTime }: Props) {
  const points = uncertainty?.forecast ?? []
  const selected = points[selectedIndexOf(points, selectedTime, openedAt)]
  const unit = uncertainty?.unit ?? ''
  const hist = uncertainty?.historical
  const th = uncertainty?.thresholds
  const level = selected?.disagreement_level
  const explanation = hist
    ? 'Estimated from historical model residuals and forecast-model spread.'
    : uncertainty?.explanation ?? 'Estimated from disagreement among the contributing forecast models.'

  return (
    <section id="uncertainty" aria-labelledby="uncertainty-title" className="scroll-mt-6">
      <SectionHeader index="05" question="How uncertain is it?" title="Forecast Uncertainty">
        <p className="max-w-md text-sm text-mist">{explanation}</p>
      </SectionHeader>
      <h2 id="uncertainty-title" className="sr-only">Forecast Uncertainty</h2>

      {loading && <Loading>Estimating uncertainty…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {uncertainty?.message && !loading && <Notice tone="warn">{uncertainty.message}</Notice>}

      {uncertainty && !loading && selected && (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <article className="card p-6" style={{ background: 'linear-gradient(170deg, rgba(251,241,222,0.12), rgba(255,255,255,0.02))' }}>
              <p className="eyebrow">TrustCast · {formatTime(selected.valid_time)}</p>
              <p className="num mt-3 text-5xl font-extralight tracking-tight text-white">{fmt(selected.blended_value)}<span className="ml-1 text-lg text-white/60">{unit}</span></p>
              {hist ? (
                <>
                  <p className="num mt-4 text-lg font-semibold text-cream">{fmt(selected.historical_lower)} – {fmt(selected.historical_upper)} {unit}</p>
                  <p className="text-xs text-mist">Prediction range: 10th–90th percentile of past TrustCast errors</p>
                </>
              ) : (
                <>
                  <p className="num mt-4 text-lg font-semibold text-slate-100">{fmt(selected.model_min)} – {fmt(selected.model_max)} {unit}</p>
                  <p className="text-xs text-mist">Model disagreement range (min–max)</p>
                </>
              )}
            </article>

            <article className="card p-6">
              <div className="flex items-start justify-between gap-2">
                <p className="eyebrow">Model disagreement</p>
                {level && <LevelBadge level={level} hex={LEVEL_HEX[level]} />}
              </div>
              <p className="num mt-3 text-5xl font-extralight tracking-tight text-white">{fmt(selected.model_spread)}<span className="ml-1 text-lg text-white/60">{unit}</span></p>
              <p className="mt-4 text-sm text-slate-200">{level ? DISAGREEMENT_TEXT[level] : 'No historical spread data to classify this value.'}</p>
              <p className="num mt-1 text-xs text-mist">Model range {fmt(selected.model_min)} – {fmt(selected.model_max)} {unit} · {selected.models_used.length} model{selected.models_used.length === 1 ? '' : 's'}</p>
            </article>

            <article className="card p-6">
              <p className="eyebrow">Uncertainty sources</p>
              <dl className="num mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2.5 text-sm">
                <dt className="text-mist" title="max − min of contributing model forecasts at this hour">Model spread</dt>
                <dd className="text-right font-semibold text-slate-100">{fmt(selected.model_spread, 2)} {unit}</dd>
                <dt className="text-mist" title="√ Σ w·(f − blend)² with the Trust Engine weights">Trust-weighted std</dt>
                <dd className="text-right font-semibold text-slate-100">{fmt(selected.weighted_std, 2)} {unit}</dd>
                <dt className="text-mist" title="RMSE of the TrustCast blend (current weights) on archived forecasts vs ERA5">Historical RMSE (blend)</dt>
                <dd className="text-right font-semibold text-slate-100">{hist ? `${hist.rmse.toFixed(2)} ${unit}` : 'unavailable'}</dd>
                <dt className="text-mist" title="Mean of (past blend − ERA5). Positive = ran high.">Historical bias (blend)</dt>
                <dd className="text-right font-semibold text-slate-100">{hist ? `${signed(hist.bias)} ${unit}` : 'unavailable'}</dd>
                {Object.entries(selected.ensemble_spread ?? {}).map(([model, spread]) => (
                  <div key={model} className="contents">
                    <dt className="text-mist" title={`Standard deviation of ${uncertainty.ensemble_sources?.[model] ?? ''} ensemble members at this valid time`}>{model} ensemble spread</dt>
                    <dd className="text-right font-semibold text-slate-100">±{spread.toFixed(2)} {unit}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-xs text-mist">
                {uncertainty.models_used.length} contributing model{uncertainty.models_used.length === 1 ? '' : 's'}
                {uncertainty.excluded_models.length > 0 && ` · unavailable: ${uncertainty.excluded_models.map((m) => m.model).join(', ')}`}
              </p>
            </article>
          </div>

          <div className="card mt-4 p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-semibold text-white">Model disagreement across the forecast horizon</p>
              <p className="text-xs text-mist">Select an hour to inspect it</p>
            </div>
            <div className="mt-4 flex h-9 gap-[2px]" role="group" aria-label="Hourly model disagreement">
              {points.map((p) => {
                const hex = p.disagreement_level ? LEVEL_HEX[p.disagreement_level] : 'rgba(255,255,255,0.08)'
                const isSelected = p.valid_time === selected.valid_time
                return (
                  <button
                    key={p.valid_time}
                    type="button"
                    onClick={() => onSelectTime(p.valid_time)}
                    aria-label={`${formatTime(p.valid_time)}: spread ${fmt(p.model_spread, 2)} ${unit}, ${p.disagreement_level ?? p.status.replace('_', ' ')}`}
                    aria-pressed={isSelected}
                    title={`${formatTime(p.valid_time)} · ${fmt(p.model_spread, 2)} ${unit} · ${p.disagreement_level ?? p.status}`}
                    className={`min-w-0 flex-1 rounded-[3px] transition-opacity hover:opacity-100 ${isSelected ? 'opacity-100 ring-2 ring-cream ring-offset-2 ring-offset-ink-900' : 'opacity-75'}`}
                    style={{ background: hex }}
                  />
                )
              })}
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-mist">
              <span>{points[0] ? formatHour(points[0].valid_time) : ''}</span>
              <span>{points.length ? formatHour(points[points.length - 1].valid_time) : ''}</span>
            </div>
            <ul className="mt-3 flex flex-wrap gap-4 text-xs text-mist">
              {(['LOW', 'MEDIUM', 'HIGH'] as const).map((l) => (
                <li key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: LEVEL_HEX[l] }} aria-hidden="true" />{l}</li>
              ))}
              <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-white/10" aria-hidden="true" />No data</li>
            </ul>
          </div>

          <aside className="card-soft mt-4 space-y-2 p-5 text-xs leading-relaxed text-mist sm:p-6" aria-label="Uncertainty methodology">
            <p className="eyebrow">Methodology</p>
            <p className="text-slate-200">
              Current prototype uncertainty is derived from the available historical verification period and model forecasts. Production deployment should use rolling out-of-sample validation for calibrated coverage.
            </p>
            {hist && (
              <p>
                Prediction range: the current trust weights applied to {hist.samples} past hours of archived forecasts gave TrustCast errors between {signed(hist.error_p10)} and {signed(hist.error_p90)} {unit} (10th–90th percentile). The range is in-sample, and its future coverage is not guaranteed.
              </p>
            )}
            {th && (
              <p>
                Disagreement levels: LOW ≤ {th.low_max.toFixed(2)} {unit} &lt; MEDIUM ≤ {th.medium_max.toFixed(2)} {unit} &lt; HIGH. The cut-offs are the 33rd/67th percentiles of {th.samples} past hourly model spreads for this location and lead time.
              </p>
            )}
            {Object.keys(uncertainty.ensemble_sources ?? {}).length > 0 && (
              <p>
                Ensemble spread: {Object.entries(uncertainty.ensemble_sources ?? {}).map(([m, n]) => `${m} (${n} members)`).join(', ')} provides the standard deviation of its own members at its native valid times. It is shown as an additional uncertainty source and is not mixed into the blend.
              </p>
            )}
            <p>No confidence percentage or probability is shown. Trust weights are not probabilities of correctness.</p>
            <details className="pt-1">
              <summary className="font-semibold text-slate-200">Formulas</summary>
              <ul className="num mt-2 space-y-1 font-mono text-[11px] text-slate-300">
                {uncertainty.formula.map((line) => <li key={line} className="break-words">{line}</li>)}
              </ul>
            </details>
          </aside>
        </>
      )}
    </section>
  )
}
