import { AGREEMENT, LEVEL_HEX, VARIABLE_LABEL, fmt, formatTime, modelHex, nowIndexOf, selectedIndexOf, shortName } from '../lib'
import type { BlendResponse, ProviderForecast, UncertaintyResponse, Variable } from '../types'
import { ForecastTimeline } from './ForecastTimeline'
import { LevelBadge, Loading, ModelDot, Notice, SectionHeader } from './ui'

type Props = {
  blend: BlendResponse | null
  uncertainty: UncertaintyResponse | null
  results: ProviderForecast[]
  loading: boolean
  error: string
  locationName: string
  selectedTime: string | null
  openedAt: number
  onSelectTime: (time: string) => void
}

export function Blend({ blend, uncertainty, results, loading, error, locationName, selectedTime, openedAt, onSelectTime }: Props) {
  const points = blend?.forecast ?? []
  const nowIndex = nowIndexOf(points, openedAt)
  const selectedIndex = selectedIndexOf(points, selectedTime, openedAt)
  const selected = points[selectedIndex]
  const unc = uncertainty?.forecast.find((u) => u.valid_time === selected?.valid_time)
  const unit = blend?.unit ?? ''
  const variableLabel = blend ? (VARIABLE_LABEL[blend.variable as Variable] ?? blend.variable) : ''
  const level = unc?.disagreement_level

  return (
    <section id="blend" aria-labelledby="blend-title" className="scroll-mt-24">
      <SectionHeader index="04" question="The final forecast" title="TrustCast forecast" titleId="blend-title">
        <p className="max-w-md text-sm text-mist">One forecast built from all four models, leaning on the ones that have been most accurate here.</p>
      </SectionHeader>

      {loading && <Loading>Building the forecast for {locationName}…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}
      {blend?.message && !loading && <Notice>{blend.message}</Notice>}

      {blend && !loading && blend.status === 'ok' && selected && (
        <div
          className="card reveal p-5 sm:p-8"
          style={{ background: 'linear-gradient(165deg, rgba(150,78,52,0.34) 0%, rgba(40,44,70,0.35) 45%, rgba(46,86,130,0.30) 100%)' }}
        >
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
            <div className="lg:col-span-7">
              <p className="eyebrow text-cream/80">{variableLabel}</p>
              <p className="num mt-3 text-6xl font-extralight tracking-tighter text-white sm:text-8xl">
                {fmt(selected.blended_value)}<span className="ml-1 align-top text-2xl font-light text-white/70 sm:text-3xl">{unit}</span>
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <select className="field !w-auto !py-1.5 !text-sm" value={selected.valid_time} onChange={(e) => onSelectTime(e.target.value)} aria-label="Forecast time">
                  {points.map((p) => <option key={p.valid_time} value={p.valid_time}>{formatTime(p.valid_time)}</option>)}
                </select>
                {unc?.historical_lower != null && (
                  <span className="num text-slate-200">Forecast range <span className="font-semibold text-cream">{fmt(unc.historical_lower)}–{fmt(unc.historical_upper)} {unit}</span></span>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-4 lg:col-span-5 lg:items-end lg:text-right">
              {level && (
                <div>
                  <p className="eyebrow">Model agreement</p>
                  <div className="mt-2 flex items-center gap-3 lg:justify-end">
                    <LevelBadge level={AGREEMENT[level].short} hex={LEVEL_HEX[level]} />
                  </div>
                </div>
              )}
              <div>
                <p className="eyebrow">Built from</p>
                <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-200 lg:justify-end">
                  {blend.models_used.map((m) => (
                    <span key={m.model} className="flex items-center gap-1.5" title={m.model}><ModelDot hex={modelHex(m.model)} />{shortName(m.model)}</span>
                  ))}
                </p>
              </div>
            </div>
          </div>

          <div className="mt-8">
            <ForecastTimeline blend={blend} uncertainty={uncertainty} results={results} selectedIndex={selectedIndex} nowIndex={nowIndex} onSelect={(i) => onSelectTime(points[i].valid_time)} />
          </div>
        </div>
      )}
    </section>
  )
}
