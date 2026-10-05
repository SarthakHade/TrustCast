import { useEffect, useState } from 'react'
import { API_BASE, VARIABLE_LABEL, fmt, modelHex, shortName } from '../lib'
import type { Location, SelectedLocation, SkillReport, SpatialLayer, Variable } from '../types'
import { SpatialMap, type MapMetric } from './SpatialMap'
import { Loading, Notice } from './ui'

const METHOD_LABEL: Record<string, string> = {
  equal: 'Equal-weight mean',
  best_single: 'Best single model',
  trust_v1: 'Previous TrustCast weights',
  bc_equal: 'Bias-corrected mean',
  bc_stack: 'Bias-corrected stacking',
  bc_regime: '+ regime conditioning',
  bc_season: '+ season conditioning',
  trustcast: 'TrustCast (selected)',
}
const BASELINE_LABEL = { equal: 'the equal-weight mean', best_single: 'the best single model' }

const pct = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? 'N/A' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`)
const ratio = (v: number | null | undefined) => (v === null || v === undefined ? 'N/A' : v.toFixed(2))

type Props = { location: SelectedLocation | null; presets: Location[]; onBack: () => void }

export function EvaluationView({ location, presets, onBack }: Props) {
  const [variable, setVariable] = useState<Variable>('temperature')
  const [lead, setLead] = useState(1)
  const [report, setReport] = useState<SkillReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [metric, setMetric] = useState<MapMetric>('dominant')
  const [weights, setWeights] = useState<SpatialLayer | null>(null)
  const [risk, setRisk] = useState<SpatialLayer | null>(null)

  useEffect(() => {
    if (!location) return
    let cancelled = false
    const params = new URLSearchParams({ latitude: String(location.latitude), longitude: String(location.longitude), name: location.name, variable, lead_day: String(lead) })
    const run = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(`${API_BASE}/api/skill?${params}`)
        const data = await response.json()
        if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Evaluation could not be loaded.')
        if (!cancelled) setReport(data)
      } catch (e) {
        if (!cancelled) {
          setReport(null)
          setError(e instanceof Error ? e.message : 'Evaluation could not be loaded.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [location, variable, lead])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const [w, r] = await Promise.all([
          fetch(`${API_BASE}/api/spatial/map?variable=${variable}&lead_day=${lead}`).then((x) => x.json()),
          fetch(`${API_BASE}/api/spatial/risk`).then((x) => x.json()),
        ])
        if (!cancelled) {
          setWeights(w)
          setRisk(r)
        }
      } catch {
        if (!cancelled) setWeights({ status: 'unavailable', reason: 'Regional results could not be loaded.', cells: [] })
      }
    }
    void run()
    return () => { cancelled = true }
  }, [variable, lead])

  const m = report?.metrics
  const methods = report ? [...report.models.map((x) => `model:${x}`), ...Object.keys(METHOD_LABEL)] : []
  const unit = report?.unit ?? ''

  return (
    <div className="reveal">
      <button type="button" onClick={onBack} className="mb-6 text-sm text-mist hover:text-white">← Back to forecast</button>
      <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="eyebrow">Advanced evaluation · research prototype</p>
          <h1 className="mt-3 text-3xl font-light tracking-tight text-white sm:text-4xl">Is TrustCast better than simpler alternatives?</h1>
          <p className="mt-3 max-w-2xl text-sm text-mist">
            Every number below is out-of-sample: each forecast day was predicted with parameters trained only on data available before it was issued, then compared with ERA5. Results are shown as computed, including where TrustCast does not help.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <label className="text-xs font-semibold text-mist">Variable
            <select className="field mt-1.5 !w-44" value={variable} onChange={(e) => setVariable(e.target.value as Variable)}>
              {(Object.keys(VARIABLE_LABEL) as Variable[]).map((v) => <option key={v} value={v}>{VARIABLE_LABEL[v]}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-mist">Lead time
            <select className="field mt-1.5 !w-36" value={lead} onChange={(e) => setLead(Number(e.target.value))}>
              <option value={1}>Day 1</option>
              <option value={2}>Day 2</option>
            </select>
          </label>
        </div>
      </header>

      {!location && <Notice tone="info">Choose a location on the forecast page first.</Notice>}
      {loading && <Loading>Running walk-forward evaluation for {location?.name}… The first run for a new location downloads about 19 months of history (up to ~30 s).</Loading>}
      {error && !loading && <Notice>{error}</Notice>}

      {report && m && !loading && (
        <div className="space-y-6">
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2" aria-label="Baseline comparison">
            {(['equal', 'best_single'] as const).map((base) => {
              const s = base === 'equal' ? m.trustcast.skill_vs_equal : m.trustcast.skill_vs_best_single
              const ci = report.skill_intervals_90[base]
              const verdict = !ci || ci.low === null || ci.high === null ? 'Not enough days for an interval.'
                : ci.low > 0 ? `TrustCast was more accurate than ${BASELINE_LABEL[base]}.`
                  : ci.high < 0 ? `TrustCast was less accurate than ${BASELINE_LABEL[base]}.`
                    : `No significant difference from ${BASELINE_LABEL[base]}.`
              return (
                <article key={base} className="card p-6">
                  <p className="eyebrow">Skill vs {base === 'equal' ? 'equal-weight mean' : `best single model`}</p>
                  <p className="num mt-3 text-5xl font-extralight" style={{ color: s !== null && s < 0 ? '#e57b72' : '#ffffff' }}>{pct(s)}</p>
                  <p className="num mt-2 text-xs text-mist">90% interval {pct(ci?.low)} to {pct(ci?.high)} · RMSE skill = 1 − RMSE_TrustCast / RMSE_baseline</p>
                  <p className="mt-3 text-sm text-slate-200">{verdict}</p>
                </article>
              )
            })}
          </section>

          <section className="card p-5 sm:p-6" aria-labelledby="skill-table">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="skill-table" className="text-lg font-light text-white">Model skill · {report.location} · {VARIABLE_LABEL[report.variable]} · Day {report.lead_day}</h2>
              <p className="num text-xs text-mist">{report.period_start} → {report.period_end} · {report.evaluation_days} days · {report.common_hours} common hours</p>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="num w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wider text-mist">
                    <th className="py-2 pr-3 font-semibold">Method</th>
                    <th className="py-2 pr-3 text-right font-semibold">RMSE</th>
                    <th className="py-2 pr-3 text-right font-semibold">MAE</th>
                    <th className="py-2 pr-3 text-right font-semibold">Bias</th>
                    <th className="py-2 pr-3 text-right font-semibold">Corr.</th>
                    <th className="py-2 pr-3 text-right font-semibold">vs equal</th>
                    <th className="py-2 text-right font-semibold">vs best</th>
                  </tr>
                </thead>
                <tbody>
                  {methods.map((key) => {
                    const r = m[key]
                    if (!r) return null
                    const isModel = key.startsWith('model:')
                    const name = isModel ? key.slice(6) : METHOD_LABEL[key]
                    return (
                      <tr key={key} className={`border-b border-white/5 ${key === 'trustcast' ? 'bg-cream/[0.06] font-semibold text-white' : 'text-slate-200'}`}>
                        <td className="py-2 pr-3">
                          <span className="flex items-center gap-2">
                            {isModel && <span className="h-2 w-2 rounded-full" style={{ background: modelHex(name) }} aria-hidden="true" />}
                            {name}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right">{fmt(r.rmse, 3)}</td>
                        <td className="py-2 pr-3 text-right">{fmt(r.mae, 3)}</td>
                        <td className="py-2 pr-3 text-right">{r.bias === null ? '—' : `${r.bias > 0 ? '+' : ''}${r.bias.toFixed(3)}`}</td>
                        <td className="py-2 pr-3 text-right">{fmt(r.correlation, 3)}</td>
                        <td className={`py-2 pr-3 text-right ${r.skill_vs_equal !== null && r.skill_vs_equal < 0 ? 'text-coral' : ''}`}>{pct(r.skill_vs_equal)}</td>
                        <td className={`py-2 text-right ${r.skill_vs_best_single !== null && r.skill_vs_best_single < 0 ? 'text-coral' : ''}`}>{pct(r.skill_vs_best_single)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-mist">Units: {unit}. Bias = forecast − ERA5. Every method is scored on the same hours.</p>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-3" aria-label="Where the improvement comes from">
            <Stat title="Bias-correction gain" value={pct(report.bias_correction_gain)} note="Bias-corrected mean vs raw equal-weight mean" />
            <Stat title="Adaptive weighting gain" value={pct(report.adaptive_weighting_gain)} note="Stacking vs bias-corrected mean" />
            <article className="card p-5">
              <p className="eyebrow">Variant used per day</p>
              <ul className="mt-3 space-y-1 text-xs text-slate-200">
                {Object.entries(report.variant_usage).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                  <li key={k} className="flex justify-between gap-2"><span>{METHOD_LABEL[k] ?? k}</span><span className="num text-mist">{n} days</span></li>
                ))}
              </ul>
              {report.fallback_days > 0 && <p className="mt-2 text-xs text-amberish">{report.fallback_days} days used the fallback weights (insufficient data for stacking).</p>}
            </article>
          </section>

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Breakdown title="By season (IMD)" rows={report.by_season} unit={unit} />
            <Breakdown title="By rule-based weather regime" rows={report.by_regime} unit={unit} />
          </section>

          {report.events && (
            <section className="card p-5 sm:p-6" aria-labelledby="events-title">
              <h2 id="events-title" className="text-lg font-light text-white">Rain event verification</h2>
              <p className="mt-1 text-xs text-mist">{report.events.accumulation} · {report.events.days} complete days · metrics need at least 5 cases in their denominator, otherwise N/A.</p>
              <div className="mt-4 overflow-x-auto">
                <table className="num w-full min-w-[600px] text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wider text-mist">
                      <th className="py-2 pr-3">Threshold</th><th className="py-2 pr-3">Observed events</th><th className="py-2 pr-3">Method</th>
                      <th className="py-2 pr-3 text-right">POD</th><th className="py-2 pr-3 text-right">FAR</th><th className="py-2 pr-3 text-right">CSI</th><th className="py-2 text-right">H / M / F</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.events.thresholds.flatMap((t) => (['trustcast', 'equal', 'best_single'] as const).map((key, i) => {
                      const e = t.methods[key]
                      return (
                        <tr key={`${t.threshold_mm}-${key}`} className={`border-b border-white/5 ${key === 'trustcast' ? 'text-white' : 'text-slate-300'}`}>
                          <td className="py-1.5 pr-3">{i === 0 ? `≥ ${t.threshold_mm} mm / 24 h` : ''}</td>
                          <td className="py-1.5 pr-3">{i === 0 ? t.observed_events : ''}</td>
                          <td className="py-1.5 pr-3">{METHOD_LABEL[key]}</td>
                          <td className="py-1.5 pr-3 text-right">{ratio(e.pod)}</td>
                          <td className="py-1.5 pr-3 text-right">{ratio(e.far)}</td>
                          <td className="py-1.5 pr-3 text-right">{ratio(e.csi)}</td>
                          <td className="py-1.5 text-right text-mist">{e.hits} / {e.misses} / {e.false_alarms}</td>
                        </tr>
                      )
                    }))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <article className="card p-5 sm:p-6">
              <p className="eyebrow">Current TrustCast configuration</p>
              {report.live?.status === 'ok' && report.live.weights ? (
                <>
                  <p className="mt-2 text-sm text-slate-200">
                    For {report.live_target.date} ({report.live_target.season_label}, regime: {report.live_target.regime_label}) · {METHOD_LABEL[report.live.variant ?? ''] ?? report.live.variant} · {report.live.level}
                  </p>
                  <ul className="mt-4 space-y-2">
                    {Object.entries(report.live.weights).sort((a, b) => b[1] - a[1]).map(([model, w]) => (
                      <li key={model}>
                        <div className="flex justify-between text-xs"><span className="text-slate-200">{model}</span><span className="num text-white">{(w * 100).toFixed(1)}% · correction {fmtBias(report.live?.bias_correction, model, unit)}</span></div>
                        <div className="mt-1 h-1.5 rounded-full bg-white/8"><div className="h-1.5 rounded-full" style={{ width: `${w * 100}%`, background: modelHex(model) }} /></div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-xs text-mist">Trained on data up to {report.live.training_end} · bias correction {report.live.bias_correction?.mode}{report.live.note ? ` · ${report.live.note}` : ''}</p>
                </>
              ) : <p className="mt-2 text-sm text-mist">{report.live?.reason ?? 'No live configuration available.'}</p>}
            </article>
            <article className="card p-5 sm:p-6">
              <p className="eyebrow">Probabilistic verification</p>
              <p className="mt-2 text-sm text-slate-200">Unavailable</p>
              <p className="mt-1 text-xs text-mist">{report.probabilistic.reason}</p>
              <p className="eyebrow mt-5">Out-of-sample error range</p>
              <p className="num mt-2 text-sm text-slate-200">10th–90th percentile of TrustCast errors: {fmt(report.oos_residuals.p10, 2)} to {fmt(report.oos_residuals.p90, 2)} {unit}</p>
              <p className="mt-1 text-xs text-mist">{report.oos_residuals.samples} hours, {report.oos_residuals.period_start} → {report.oos_residuals.period_end}; used for the forecast range on the main page.</p>
            </article>
          </section>
        </div>
      )}

      <section className="card mt-6 p-5 sm:p-6" aria-labelledby="map-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="map-title" className="text-lg font-light text-white">Regional model skill</h2>
            <p className="mt-1 text-xs text-mist">
              {weights?.generated_at ? `Precomputed ${new Date(weights.generated_at).toLocaleString()} · ${weights.resolution_deg}° cells · last ${weights.history_days} days · ${VARIABLE_LABEL[variable]} · Day ${lead}` : 'Precomputed offline; the page never calls the weather APIs for the map.'}
            </p>
          </div>
          <div className="flex gap-1.5 rounded-xl border border-white/10 p-1" role="group" aria-label="Map layer">
            {(['dominant', 'skill', 'risk'] as const).map((k) => (
              <button key={k} type="button" aria-pressed={metric === k} onClick={() => setMetric(k)}
                className={`rounded-lg px-3 py-1.5 text-xs ${metric === k ? 'bg-white/10 text-white' : 'text-mist hover:text-white'}`}>
                {k === 'dominant' ? 'Dominant model' : k === 'skill' ? 'Skill vs equal' : 'Risk'}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-5">
          <SpatialMap weights={weights} risk={risk} metric={metric} markers={presets} selected={location} />
        </div>
        {weights?.pooled && Object.keys(weights.pooled).length > 0 && metric !== 'risk' && (
          <div className="mt-5">
            <p className="eyebrow">Regional pooled weights by regime (used when a location lacks history for a regime)</p>
            <div className="mt-2 overflow-x-auto">
              <table className="num w-full min-w-[520px] text-xs text-slate-200">
                <thead><tr className="text-left text-mist"><th className="py-1 pr-3">Regime</th>{weights.models?.map((x) => <th key={x} className="py-1 pr-3 text-right">{shortName(x)}</th>)}<th className="py-1 text-right">Hours / cells</th></tr></thead>
                <tbody>
                  {Object.entries(weights.pooled).map(([k, p]) => (
                    <tr key={k} className="border-t border-white/5">
                      <td className="py-1 pr-3">{p.label}</td>
                      {weights.models?.map((x) => <td key={x} className="py-1 pr-3 text-right">{(p.weights[x] * 100).toFixed(0)}%</td>)}
                      <td className="py-1 text-right text-mist">{p.hours} / {p.cells}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {metric === 'risk' && risk?.note && <p className="mt-3 text-xs text-mist">{risk.note}{risk.issued_at ? ` Issued ${new Date(risk.issued_at).toLocaleString()}.` : ''}</p>}
        <p className="mt-3 text-[11px] text-mist/70">Cells are selected with Natural Earth country polygons as a computational mask; no boundaries are drawn.</p>
      </section>

      {report && !loading && (
        <section className="card-soft mt-6 p-5 text-xs leading-relaxed text-mist sm:p-6" aria-labelledby="method-title">
          <h2 id="method-title" className="eyebrow">Methodology & data</h2>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-[12rem_1fr]">
            {Object.entries(report.methodology).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-300">{k.replace(/_/g, ' ')}</dt><dd>{String(v)}</dd></div>
            ))}
            {Object.entries(report.sources).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-300">{k}</dt><dd>{v}</dd></div>
            ))}
            <dt className="text-slate-300">data quality</dt>
            <dd>{Object.entries(report.data_quality).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ')}{report.data_fetched_at ? ` · downloaded ${report.data_fetched_at}` : ''}</dd>
          </dl>
        </section>
      )}
    </div>
  )
}

function fmtBias(b: { kind: string; per_model: Record<string, number> } | undefined, model: string, unit: string) {
  const v = b?.per_model[model]
  if (v === undefined) return '—'
  return b?.kind === 'multiplicative' ? `×${v.toFixed(2)}` : `${v > 0 ? '−' : '+'}${Math.abs(v).toFixed(2)} ${unit}`
}

function Stat({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <article className="card p-5">
      <p className="eyebrow">{title}</p>
      <p className={`num mt-3 text-4xl font-extralight ${value.startsWith('-') ? 'text-coral' : 'text-white'}`}>{value}</p>
      <p className="mt-2 text-xs text-mist">{note}</p>
    </article>
  )
}

function Breakdown({ title, rows, unit }: { title: string; rows: SkillReport['by_season']; unit: string }) {
  return (
    <article className="card p-5">
      <p className="eyebrow">{title}</p>
      <div className="mt-3 overflow-x-auto">
        <table className="num w-full min-w-[420px] text-xs">
          <thead><tr className="text-left text-mist"><th className="py-1 pr-2">Group</th><th className="py-1 pr-2 text-right">Days</th><th className="py-1 pr-2 text-right">TrustCast RMSE</th><th className="py-1 pr-2 text-right">Equal RMSE</th><th className="py-1 pr-2 text-right">vs equal</th><th className="py-1 text-right">vs best</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.group} className="border-t border-white/5 text-slate-200">
                <td className="py-1.5 pr-2">{r.group.replace(/_/g, ' ').toLowerCase()}</td>
                <td className="py-1.5 pr-2 text-right">{r.days}</td>
                <td className="py-1.5 pr-2 text-right">{fmt(r.trustcast as number | null, 2)}</td>
                <td className="py-1.5 pr-2 text-right">{fmt(r.equal as number | null, 2)}</td>
                <td className={`py-1.5 pr-2 text-right ${r.skill_vs_equal !== null && r.skill_vs_equal < 0 ? 'text-coral' : ''}`}>{pct(r.skill_vs_equal)}</td>
                <td className={`py-1.5 text-right ${r.skill_vs_best_single !== null && r.skill_vs_best_single < 0 ? 'text-coral' : ''}`}>{pct(r.skill_vs_best_single)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-mist">RMSE in {unit}. Small groups (few days) are noisy.</p>
    </article>
  )
}
