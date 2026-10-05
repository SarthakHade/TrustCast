import { AGREEMENT, LEVEL_HEX, VARIABLE_LABEL, fmt, formatCoords, formatTime, modelHex, nowIndexOf, riskHeadline, shortName } from '../lib'
import type { BlendResponse, Location, ProviderForecast, RiskResponse, SelectedLocation, UncertaintyResponse, Variable } from '../types'
import { Sparkline } from './charts'
import { LocationSearch } from './LocationSearch'
import { CloudIcon, ModelDot, MoonIcon, Notice, PartlyCloudyIcon, RainIcon, SunIcon } from './ui'

type HeroProps = {
  backendStatus: string
  locations: Location[]
  selected: SelectedLocation | null
  onLocation: (location: SelectedLocation) => void
  forecastDays: number
  onForecastDays: (days: number) => void
  variable: Variable
  onVariable: (variable: Variable) => void
  leadDay: number
  onLeadDay: (day: number) => void
  loadingForecasts: boolean
  onRefresh: () => void
  results: ProviderForecast[]
  blend: BlendResponse | null
  uncertainty: UncertaintyResponse | null
  risks: RiskResponse | null
  loading: boolean
  openedAt: number
}

/**
 * Current conditions from the live model data near "now" (mean over live models): rain amount and
 * humidity only. The icon is a simple cue; the label states only what the data supports.
 */
function currentConditions(results: ProviderForecast[], openedAt: number) {
  const nearNow = results
    .filter((r) => r.status === 'live')
    .map((r) => r.forecast.find((rec) => new Date(rec.valid_time).getTime() >= openedAt - 30 * 60 * 1000))
    .filter((rec) => rec !== undefined)
  const mean = (key: 'precipitation' | 'humidity') => {
    const vals = nearNow.map((rec) => rec[key]).filter((v): v is number => v !== null)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  const rain = mean('precipitation')
  const humidity = mean('humidity')
  if (rain === null && humidity === null) return null
  const hour = nearNow[0] ? new Date(nearNow[0].valid_time).getHours() : 12
  const night = hour < 6 || hour >= 18
  const cls = 'h-20 w-20 text-cream/85 sm:h-24 sm:w-24'
  const wet = rain !== null && rain >= 0.2
  const label = wet ? `Rain · ${fmt(rain)} mm/h` : `No rain expected${humidity !== null ? ` · humidity ${fmt(humidity, 0)}%` : ''}`
  let icon
  if (wet) icon = <RainIcon className={cls} />
  else if (humidity !== null && humidity >= 85) icon = <CloudIcon className={cls} />
  else if (night) icon = <MoonIcon className={cls} />
  else if (humidity !== null && humidity >= 65) icon = <PartlyCloudyIcon className={cls} />
  else icon = <SunIcon className={cls} />
  return { icon, label }
}

/** The most serious current risk, in words (levels come from the backend risk engine). */
function riskStatus(risks: RiskResponse | null) {
  const ok = risks?.risks.filter((r) => r.status === 'ok' && r.level) ?? []
  if (!ok.length) return null
  const worst = ok.find((r) => r.level === 'HIGH') ?? ok.find((r) => r.level === 'ELEVATED')
  if (!worst) return { text: 'No significant weather risk', hex: LEVEL_HEX.NORMAL }
  return { text: riskHeadline(worst), hex: LEVEL_HEX[worst.level ?? 'NORMAL'] }
}

export function Hero(props: HeroProps) {
  const { blend, uncertainty, openedAt, selected } = props
  const points = blend?.forecast ?? []
  const nowIndex = Math.max(0, nowIndexOf(points, openedAt))
  const now = points[nowIndex]
  const unc = uncertainty?.forecast.find((u) => u.valid_time === now?.valid_time)
  const upcoming = points.slice(nowIndex)
  const contributing = blend?.models_used ?? []
  const unit = blend?.unit ?? ''
  const conditions = currentConditions(props.results, openedAt)
  const risk = riskStatus(props.risks)
  const level = unc?.disagreement_level

  return (
    <section className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-8" aria-label="Current forecast">
      <h1 className="sr-only">TrustCast forecast dashboard</h1>

      <form
        className="card-soft flex flex-col gap-5 p-5 sm:p-6 lg:col-span-5"
        aria-label="Forecast controls"
        onSubmit={(e) => { e.preventDefault(); props.onRefresh() }}
      >
        {props.backendStatus !== 'Connected' && props.backendStatus !== 'checking' && (
          <Notice>Forecast service {props.backendStatus.toLowerCase()}. Start the TrustCast backend and reload.</Notice>
        )}
        <div>
          <p className="eyebrow mb-2">Location</p>
          <LocationSearch selected={selected} presets={props.locations} onSelect={props.onLocation} />
        </div>
        <div>
          <p className="eyebrow mb-2">Forecast settings</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <label className="text-xs font-semibold text-mist">
              Forecast days
              <select className="field mt-1.5" value={props.forecastDays} onChange={(e) => props.onForecastDays(Number(e.target.value))}>
                {[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{d} day{d === 1 ? '' : 's'}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-mist">
              Lead time
              <select className="field mt-1.5" value={props.leadDay} onChange={(e) => props.onLeadDay(Number(e.target.value))}>
                <option value={1}>Day 1 (~24 h)</option>
                <option value={2}>Day 2 (~48 h)</option>
              </select>
            </label>
            <label className="text-xs font-semibold text-mist sm:col-span-2 lg:col-span-1">
              Variable
              <select className="field mt-1.5" value={props.variable} onChange={(e) => props.onVariable(e.target.value as Variable)}>
                {(Object.keys(VARIABLE_LABEL) as Variable[]).map((v) => <option key={v} value={v}>{VARIABLE_LABEL[v]}</option>)}
              </select>
            </label>
          </div>
        </div>
        <button
          type="submit"
          className="mt-auto w-full rounded-[14px] bg-cream px-6 py-3 text-sm font-bold text-ink-900 shadow-[0_10px_30px_-12px_rgba(251,241,222,0.6)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          disabled={props.loadingForecasts || !selected}
        >
          {props.loadingForecasts ? 'Loading…' : 'Load forecasts'}
        </button>
      </form>

      <article
        className="card relative flex min-h-[25rem] flex-col justify-between p-6 sm:p-8 lg:col-span-7"
        style={{ background: 'linear-gradient(160deg, rgba(58,62,140,0.85) 0%, rgba(92,78,150,0.55) 45%, rgba(214,146,120,0.55) 100%)' }}
        aria-label={`TrustCast forecast for ${selected?.name ?? 'the selected location'}`}
      >
        <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-2xl font-medium text-white sm:text-3xl">{selected?.name ?? '—'}</h2>
          {selected && (
            <p className="mt-0.5 truncate text-xs text-white/70" title={selected.display_name}>
              {selected.area && <span>{selected.area} · </span>}
              <span className="num">{formatCoords(selected.latitude, selected.longitude)}</span>
            </p>
          )}
          <p className="mt-1 text-sm text-white/70">{now ? formatTime(now.valid_time) : props.loading ? 'Updating forecast…' : '—'}</p>
        </div>
        {risk && (
          <a
            href="#risk"
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-black/25 px-3 py-1 text-[11px] font-semibold text-white/90 hover:bg-black/35"
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: risk.hex }} aria-hidden="true" />{risk.text}
          </a>
        )}
        </div>

        <div className="mt-6 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="num text-7xl font-extralight leading-none tracking-tighter text-white sm:text-8xl">
              {now && now.blended_value !== null ? fmt(now.blended_value) : '—'}
              <span className="ml-1 align-top text-2xl font-light text-white/80 sm:text-3xl">{unit}</span>
            </p>
            <p className="mt-3 text-base text-white/85">{VARIABLE_LABEL[props.variable]}</p>
            {conditions && <p className="mt-1 text-sm text-white/65">{conditions.label}</p>}
          </div>
          {conditions && <div className="hidden shrink-0 sm:block" aria-hidden="true">{conditions.icon}</div>}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Forecast range</p>
            <p className="num mt-1 text-sm font-semibold text-white">
              {unc?.historical_lower != null && unc.historical_upper != null ? `${fmt(unc.historical_lower)}–${fmt(unc.historical_upper)} ${unit}` : '—'}
            </p>
          </div>
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Forecast agreement</p>
            <p className="mt-1 flex items-center gap-2 text-sm font-semibold text-white">
              {level ? <><span className="h-2 w-2 rounded-full" style={{ background: LEVEL_HEX[level] }} aria-hidden="true" />{AGREEMENT[level].short}</> : '—'}
            </p>
          </div>
          <div className="col-span-2 rounded-2xl bg-black/20 p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">
                {contributing.length > 0 ? `${contributing.length} forecast models contributing` : 'Forecast models'}
              </p>
              {upcoming.length > 0 && (
                <p className="num text-[11px] text-white/60">Next {upcoming.length} hours</p>
              )}
            </div>
            <div className="mt-2 h-12">
              <Sparkline values={upcoming.map((p) => p.blended_value)} color="#fbf1de" label={`TrustCast ${VARIABLE_LABEL[props.variable].toLowerCase()} for the next ${upcoming.length} hours`} />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
              {contributing.map((m) => (
                <span key={m.model} className="flex items-center gap-1.5 text-xs text-white/85" title={m.model}><ModelDot hex={modelHex(m.model)} />{shortName(m.model)}</span>
              ))}
            </div>
          </div>
        </div>
      </article>
    </section>
  )
}
