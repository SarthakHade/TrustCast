import type { ReactNode } from 'react'
import { fmt, formatTime, humanize, modelHex } from '../lib'
import type { Model, ProviderForecast } from '../types'
import { Sparkline } from './charts'
import { DropIcon, HumidityIcon, Loading, Notice, SectionHeader, StatusPill, WindIcon } from './ui'

type SourcesProps = {
  models: Model[]
  results: ProviderForecast[]
  loading: boolean
  error: string
  openedAt: number
  /** Models contributing to the currently selected variable's blend, and why others are not. */
  contributors: string[]
  exclusions: Record<string, string>
  variableLabel: string
}

const VARIABLE_SHORT: Record<string, string> = { temperature: '2 m temp', precipitation: 'Rain', wind_speed: '10 m wind', humidity: 'RH' }

export function Sources({ models, results, loading, error, openedAt, contributors, exclusions, variableLabel }: SourcesProps) {
  const statusOf = (m: Model) => results.find((r) => r.model === m.name)?.status ?? m.status
  const live = models.filter((m) => statusOf(m) === 'live')
  const offline = models.filter((m) => !['live', 'inactive'].includes(statusOf(m)))
  const inactive = models.filter((m) => statusOf(m) === 'inactive')
  const registered = models.length - inactive.length

  return (
    <section id="sources" aria-labelledby="sources-title" className="scroll-mt-6">
      <SectionHeader index="01" question="What are the forecasts saying?" title="Live forecast sources">
        <div className="max-w-md text-sm text-mist">
          <p>Raw, normalised output from each model at its own run time. A model is LIVE only when its real current run was retrieved and validated.</p>
          {results.length > 0 && (
            <p className="mt-2 text-slate-200">
              <span className="num font-semibold">{live.length} / {registered}</span> models live · <span className="num font-semibold">{contributors.length}</span> contributing to the {variableLabel.toLowerCase()} blend
            </p>
          )}
        </div>
      </SectionHeader>
      <h2 id="sources-title" className="sr-only">Live forecast sources</h2>

      {error && <div className="mb-4"><Notice>{error}</Notice></div>}
      {loading && results.length === 0 && <div className="mb-4"><Loading>Fetching live model runs…</Loading></div>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {live.map((m) => (
          <LiveSourceCard
            key={m.name}
            model={m}
            result={results.find((r) => r.model === m.name)}
            openedAt={openedAt}
            contributing={contributors.includes(m.name)}
            exclusion={exclusions[m.name]}
          />
        ))}
        {offline.map((m) => <OfficialSourceCard key={m.name} model={m} result={results.find((r) => r.model === m.name)} />)}
      </div>

      {inactive.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-mist">
          <span>Optional models, not part of the active blend:</span>
          {inactive.map((m) => (
            <span key={m.name} className="flex items-center gap-2 rounded-full border border-dashed border-white/12 px-3 py-1" title={m.note}>
              <span className="text-slate-300">{m.name}</span>
              <StatusPill status="inactive" />
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function LiveSourceCard({ model, result, openedAt, contributing, exclusion }: {
  model: Model
  result?: ProviderForecast
  openedAt: number
  contributing: boolean
  exclusion?: string
}) {
  const hex = modelHex(model.name)
  const records = result?.forecast ?? []
  const current = records.find((r) => new Date(r.valid_time).getTime() >= openedAt - 30 * 60 * 1000) ?? records[0]
  const variables = result?.variables ?? []
  const prov = result?.provenance ?? {}
  return (
    <article
      className="card flex flex-col p-5 sm:p-6"
      style={{ background: `radial-gradient(120% 90% at 100% 0%, ${hex}2e 0%, transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.02))` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: hex }} aria-hidden="true" />
            <span className="truncate">{model.name}</span>
          </h3>
          <p className="mt-0.5 text-xs text-mist">{model.provider} · {model.model_type}{model.tier === 'optional' ? ' · optional' : ''}</p>
        </div>
        <StatusPill status={result?.status ?? model.status} />
      </div>

      {current ? (
        <>
          <div className="mt-5 flex items-end justify-between gap-4">
            <p className="num text-5xl font-extralight tracking-tight text-white">
              {fmt(current.temperature)}<span className="ml-0.5 align-top text-xl text-white/70">°C</span>
            </p>
            <div className="h-12 w-28 sm:w-32">
              <Sparkline values={records.map((r) => r.temperature)} color={hex} label={`${model.name} temperature across ${records.length} forecast steps`} />
            </div>
          </div>
          <p className="mt-1 text-xs text-mist">
            Valid {formatTime(current.valid_time)} · <span className="num">+{current.lead_time_hours} h</span> lead
          </p>
          {current.ensemble_members && (
            <p className="mt-1 text-xs text-slate-300">
              {current.ensemble_members}-member ensemble mean · spread ±{fmt(current.temperature_spread, 2)} °C
            </p>
          )}

          <dl className="mt-4 grid grid-cols-3 gap-2">
            <Metric icon={<DropIcon className="h-4 w-4" />} label="Rain" value={variables.includes('precipitation') ? `${fmt(current.precipitation)} mm` : 'not ingested'} />
            <Metric icon={<WindIcon className="h-4 w-4" />} label="Wind" value={`${fmt(current.wind_speed)} km/h`} />
            <Metric icon={<HumidityIcon className="h-4 w-4" />} label="Humidity" value={variables.includes('humidity') ? `${fmt(current.humidity, 0)} %` : 'n/a'} />
          </dl>

          <div className="mt-4 flex flex-wrap gap-1.5" aria-label="Variables retrieved">
            {variables.map((v) => (
              <span key={v} className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-semibold text-slate-200">{VARIABLE_SHORT[v] ?? v}</span>
            ))}
          </div>
          <p className={`mt-3 text-xs ${contributing ? 'text-sage' : 'text-amberish'}`}>
            {contributing ? '● Contributing to the current blend' : `○ Not in the current blend${exclusion ? `: ${exclusion}` : ''}`}
          </p>

          <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-t border-white/5 pt-3 text-[11px] leading-relaxed text-mist/90">
            <dt>Run</dt><dd className="text-right">{result?.init_time ? formatTime(result.init_time) : 'not supplied'}</dd>
            <dt>Retrieved</dt><dd className="text-right">{result?.retrieved_at ? formatTime(result.retrieved_at) : '—'}</dd>
            {prov.grid_latitude !== undefined && (
              <><dt>Grid point</dt><dd className="num text-right">{fmt(Number(prov.grid_latitude), 2)}°N, {fmt(Number(prov.grid_longitude), 2)}°E</dd></>
            )}
            <dt>Source</dt><dd className="truncate text-right" title={model.source}>{model.source}</dd>
          </dl>
        </>
      ) : (
        <p className="mt-5 text-sm text-mist">{result?.error ?? 'Waiting for forecast data…'}</p>
      )}
    </article>
  )
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-black/20 px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-mist">{icon}{label}</dt>
      <dd className="num mt-1 truncate text-sm font-semibold text-slate-100">{value}</dd>
    </div>
  )
}

/** Waiting / unavailable / error: the official source is shown with what it currently publishes. No values. */
function OfficialSourceCard({ model, result }: { model: Model; result?: ProviderForecast }) {
  const status = result?.status ?? model.status
  const prov = Object.entries(result?.provenance ?? {}).filter(([k, v]) => k !== 'reason' && v !== null && v !== undefined)
  const ncmrwf = model.provider.includes('NCMRWF')
  return (
    <article
      className="flex flex-col rounded-[28px] border border-dashed border-cream/20 p-5 sm:p-6"
      style={{ background: 'radial-gradient(90% 90% at 0% 0%, rgba(251,241,222,0.06), transparent 60%), rgba(255,255,255,0.015)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-xl font-light leading-snug text-white">{model.name}</h3>
          <p className="mt-0.5 text-xs text-mist">{model.provider} · {model.model_type}</p>
        </div>
        <StatusPill status={status} />
      </div>
      {ncmrwf && (
        <p className="mt-4 text-sm leading-relaxed text-slate-200">
          NCUM-G is NCMRWF&apos;s global numerical weather prediction system. TrustCast keeps a provider adapter so NCUM can be normalised and evaluated alongside the other sources as soon as machine-readable data is available.
        </p>
      )}
      <p className="mt-3 text-sm font-semibold text-amberish">{result?.error ?? model.note}</p>
      <p className="mt-1 text-xs text-mist">No values are shown, scored, weighted or blended for this model.</p>

      {prov.length > 0 && (
        <details className="mt-4 rounded-2xl border border-white/5 bg-black/20 p-3 text-xs text-mist">
          <summary className="font-semibold text-slate-200">What the official source publishes now</summary>
          <dl className="mt-2 grid grid-cols-1 gap-y-1 sm:grid-cols-[auto_1fr] sm:gap-x-3">
            {prov.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-mist/80">{humanize(k)}</dt>
                <dd className="break-words text-slate-200">{String(v)}</dd>
              </div>
            ))}
          </dl>
          {result?.retrieved_at && <p className="mt-2 text-mist/70">Checked {formatTime(result.retrieved_at)}</p>}
        </details>
      )}

      {model.source_url && (
        <a
          href={model.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto inline-flex w-fit items-center gap-1.5 self-start rounded-full border border-white/15 px-3 py-1.5 pt-1.5 text-xs font-semibold text-cream hover:border-cream/50 [margin-top:1.25rem]"
        >
          Official {model.provider.split(' ')[0]} source <span aria-hidden="true">↗</span><span className="sr-only">(opens in a new tab)</span>
        </a>
      )}
    </article>
  )
}
