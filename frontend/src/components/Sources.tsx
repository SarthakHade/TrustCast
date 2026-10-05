import { useId, useState, type ReactNode } from 'react'
import { PRIMARY_SOURCES, fmt, formatShort, formatTime, modelHex, shortName } from '../lib'
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
}

export function Sources({ models, results, loading, error, openedAt, contributors, exclusions }: SourcesProps) {
  const primary = PRIMARY_SOURCES.map((name) => models.find((m) => m.name === name)).filter((m): m is Model => m !== undefined)
  const resultOf = (name: string) => results.find((r) => r.model === name)
  // Accordion: at most one card shows its technical details.
  const [openDetails, setOpenDetails] = useState<string | null>(null)

  return (
    <section id="sources" aria-labelledby="sources-title" className="scroll-mt-24">
      <SectionHeader index="01" question="What each weather model predicts" title="Model forecasts" titleId="sources-title">
        <p className="max-w-md text-sm text-mist">The four weather models behind the TrustCast forecast, each from its latest run.</p>
      </SectionHeader>

      {contributors.length > 0 && (
        <p className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="eyebrow text-slate-200">{contributors.length} models contributing</span>
          <span className="text-xs text-mist">{contributors.map(shortName).join(' · ')}</span>
        </p>
      )}

      {error && <div className="mb-4"><Notice>{error}</Notice></div>}
      {loading && results.length === 0 && <div className="mb-4"><Loading>Fetching current model runs…</Loading></div>}

      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {primary.map((m) => (
          <SourceCard
            key={m.name}
            model={m}
            result={resultOf(m.name)}
            openedAt={openedAt}
            contributing={contributors.includes(m.name)}
            exclusion={exclusions[m.name]}
            blendKnown={contributors.length > 0}
            detailsOpen={openDetails === m.name}
            onToggleDetails={() => setOpenDetails((current) => (current === m.name ? null : m.name))}
          />
        ))}
      </div>

    </section>
  )
}

function SourceCard({ model, result, openedAt, contributing, exclusion, blendKnown, detailsOpen, onToggleDetails }: {
  model: Model
  result?: ProviderForecast
  openedAt: number
  contributing: boolean
  exclusion?: string
  blendKnown: boolean
  detailsOpen: boolean
  onToggleDetails: () => void
}) {
  const detailsId = useId()
  const hex = modelHex(model.name)
  const records = result?.forecast ?? []
  const current = records.find((r) => new Date(r.valid_time).getTime() >= openedAt - 30 * 60 * 1000) ?? records[0]
  const variables = result?.variables ?? []
  const status = result?.status ?? model.status
  return (
    <article
      className="card lift reveal flex flex-col p-5"
      style={{ background: `radial-gradient(120% 90% at 100% 0%, ${hex}26 0%, transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: hex }} aria-hidden="true" />
            <span className="truncate">{model.name}</span>
          </h3>
          <p className="mt-0.5 text-xs text-mist">{model.model_type}</p>
        </div>
        <StatusPill status={status} />
      </div>

      {current ? (
        <>
          <div className="mt-5 flex items-end justify-between gap-3">
            <p className="num text-5xl font-extralight tracking-tight text-white">
              {fmt(current.temperature)}<span className="ml-0.5 align-top text-xl text-white/70">°C</span>
            </p>
            <div className="h-10 w-24">
              <Sparkline values={records.map((r) => r.temperature)} color={hex} label={`${model.name} temperature across ${records.length} forecast steps`} />
            </div>
          </div>

          <dl className="mt-4 grid grid-cols-3 gap-2">
            <Metric icon={<DropIcon className="h-3.5 w-3.5" />} label="Rain" value={variables.includes('precipitation') ? `${fmt(current.precipitation)} mm` : '—'} />
            <Metric icon={<WindIcon className="h-3.5 w-3.5" />} label="Wind" value={`${fmt(current.wind_speed, 0)} km/h`} />
            <Metric icon={<HumidityIcon className="h-3.5 w-3.5" />} label="RH" value={variables.includes('humidity') ? `${fmt(current.humidity, 0)}%` : '—'} />
          </dl>

          <p className="num mt-3 text-[11px] text-mist">
            Valid {formatShort(current.valid_time)}{result?.init_time ? ` · run ${formatShort(result.init_time)}` : ''}
          </p>

          {blendKnown && (
            <p className={`mt-3 border-t border-white/5 pt-3 text-xs ${contributing ? 'text-sage' : 'text-amberish'}`} title={exclusion}>
              {contributing ? '● Contributing to forecast' : '○ Not used in this forecast'}
            </p>
          )}

          <button
            type="button"
            className="mt-3 w-fit rounded-md text-[11px] text-mist/80 hover:text-white"
            aria-expanded={detailsOpen}
            aria-controls={detailsId}
            onClick={onToggleDetails}
          >
            {detailsOpen ? 'Hide details' : 'Details'}
          </button>
          {detailsOpen && (
            <dl id={detailsId} className="mt-2 grid text-[11px] text-mist grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 leading-relaxed">
              <dt>Forecast source</dt><dd className="text-right text-slate-300">{model.provider.split(' / ')[0]}</dd>
              <dt>Latest model run</dt><dd className="text-right text-slate-300">{result?.init_time ? formatTime(result.init_time) : '—'}</dd>
              <dt>Forecast horizon</dt><dd className="num text-right text-slate-300">{records.length ? `${Math.round((new Date(records[records.length - 1].valid_time).getTime() - new Date(records[0].valid_time).getTime()) / 3600000) + 1} hours` : '—'}</dd>
              <dt>Status</dt><dd className="text-right text-slate-300">{status === 'live' ? 'Up to date' : 'Waiting for data'}</dd>
            </dl>
          )}
        </>
      ) : (
        <p className="mt-5 text-sm text-mist">{result?.error ?? 'Waiting for forecast data…'}</p>
      )}
    </article>
  )
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-black/20 px-2.5 py-2">
      <dt className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-mist">{icon}{label}</dt>
      <dd className="num mt-0.5 truncate text-sm font-semibold text-slate-100">{value}</dd>
    </div>
  )
}
