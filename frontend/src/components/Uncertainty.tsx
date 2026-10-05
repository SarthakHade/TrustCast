import { AGREEMENT, LEVEL_HEX, fmt, formatHour, formatShort, formatTime, selectedIndexOf } from '../lib'
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
  const level = selected?.disagreement_level
  const hasRange = selected?.historical_lower != null && selected.historical_upper != null

  return (
    <section id="uncertainty" aria-labelledby="uncertainty-title" className="scroll-mt-24">
      <SectionHeader index="05" question="How sure is the forecast?" title="Forecast agreement" titleId="uncertainty-title">
        <p className="max-w-md text-sm text-mist">When the models agree, the forecast is more settled. When they disagree, it may still change.</p>
      </SectionHeader>

      {loading && <Loading>Comparing the forecasts…</Loading>}
      {error && !loading && <Notice>{error}</Notice>}

      {uncertainty && !loading && selected && (
        <div className="reveal">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <article className="card p-6" style={{ background: 'linear-gradient(170deg, rgba(251,241,222,0.12), rgba(255,255,255,0.02))' }}>
              <p className="eyebrow">Forecast range · {formatShort(selected.valid_time)}</p>
              {hasRange ? (
                <p className="num mt-3 text-5xl font-extralight tracking-tight text-white">
                  {fmt(selected.historical_lower)}–{fmt(selected.historical_upper)}<span className="ml-1 text-lg text-white/60">{unit}</span>
                </p>
              ) : (
                <p className="mt-3 text-sm text-mist">Not enough history yet to estimate a range.</p>
              )}
              <p className="num mt-3 text-sm text-slate-200">TrustCast forecast {fmt(selected.blended_value)} {unit}</p>
              <p className="mt-1 text-xs text-mist">The likely range, based on how far past forecasts here were off.</p>
            </article>

            <article className="card p-6">
              <p className="eyebrow">Model agreement</p>
              {level ? (
                <>
                  <div className="mt-4"><LevelBadge level={AGREEMENT[level].label} hex={LEVEL_HEX[level]} size="md" /></div>
                  <p className="mt-4 text-lg font-light text-white">{AGREEMENT[level].text}</p>
                  {selected.model_spread !== null && (
                    <p className="num mt-2 text-xs text-mist">Models range from {fmt(selected.model_min)} to {fmt(selected.model_max)} {unit}</p>
                  )}
                </>
              ) : (
                <p className="mt-4 text-sm text-mist">Not enough history yet to judge agreement.</p>
              )}
            </article>
          </div>

          <div className="card mt-4 p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm font-semibold text-white">Agreement hour by hour</p>
              <p className="text-xs text-mist">Select an hour</p>
            </div>
            <div className="mt-4 flex h-9 gap-[2px]" role="group" aria-label="Hourly model agreement">
              {points.map((p) => {
                const hex = p.disagreement_level ? LEVEL_HEX[p.disagreement_level] : 'rgba(255,255,255,0.08)'
                const isSelected = p.valid_time === selected.valid_time
                const words = p.disagreement_level ? AGREEMENT[p.disagreement_level].short : 'No data'
                return (
                  <button
                    key={p.valid_time}
                    type="button"
                    onClick={() => onSelectTime(p.valid_time)}
                    aria-label={`${formatTime(p.valid_time)}: ${words}`}
                    aria-pressed={isSelected}
                    title={`${formatTime(p.valid_time)} · ${words}`}
                    className={`min-w-0 flex-1 rounded-[3px] transition-opacity hover:opacity-100 ${isSelected ? 'opacity-100 ring-2 ring-cream ring-offset-2 ring-offset-ink-900' : 'opacity-70'}`}
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
                <li key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: LEVEL_HEX[l] }} aria-hidden="true" />{AGREEMENT[l].short}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  )
}
