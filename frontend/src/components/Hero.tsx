import { DISAGREEMENT_TEXT, LEVEL_HEX, VARIABLE_LABEL, fmt, formatShort, formatTime, modelHex, nowIndexOf } from '../lib'
import type { BlendResponse, Location, Model, ProviderForecast, UncertaintyResponse, Variable } from '../types'
import { Sparkline } from './charts'
import { CloudIcon, LevelBadge, ModelDot, PartlyCloudyIcon, RainIcon, SparkIcon, SunIcon } from './ui'

type HeroProps = {
  backendStatus: string
  locations: Location[]
  locationName: string
  onLocation: (name: string) => void
  forecastDays: number
  onForecastDays: (days: number) => void
  variable: Variable
  onVariable: (variable: Variable) => void
  leadDay: number
  onLeadDay: (day: number) => void
  loadingForecasts: boolean
  onRefresh: () => void
  models: Model[]
  results: ProviderForecast[]
  blend: BlendResponse | null
  uncertainty: UncertaintyResponse | null
  loading: boolean
  openedAt: number
}

/** Sky icon chosen from live Step 2 precipitation / humidity near "now" (mean over live models). */
function skyIcon(results: ProviderForecast[], openedAt: number) {
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
  const label = `Sky icon from live model data: mean precipitation ${fmt(rain)} mm, humidity ${fmt(humidity, 0)}%`
  const cls = 'h-24 w-24 text-cream/90 sm:h-28 sm:w-28'
  if (rain !== null && rain >= 0.2) return <RainIcon className={cls} label={label} />
  if (humidity !== null && humidity >= 85) return <CloudIcon className={cls} label={label} />
  if (humidity !== null && humidity >= 65) return <PartlyCloudyIcon className={cls} label={label} />
  return <SunIcon className={cls} label={label} />
}

export function Hero(props: HeroProps) {
  const { blend, uncertainty, openedAt } = props
  const points = blend?.forecast ?? []
  const nowIndex = Math.max(0, nowIndexOf(points, openedAt))
  const now = points[nowIndex]
  const unc = uncertainty?.forecast.find((u) => u.valid_time === now?.valid_time)
  const upcoming = points.slice(nowIndex)
  const connected = props.models.filter((m) => m.status !== 'inactive').length
  const contributing = blend?.models_used ?? []

  return (
    <section className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-x-8 lg:gap-y-6">
      {/* Mobile order: headline → forecast card → controls. Desktop: two columns. */}
      <div className="lg:col-span-6 lg:row-start-1 xl:col-span-7">
          <p className="eyebrow flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>SIH26081 · VisionCrafters</span>
            <span className="h-px w-6 bg-white/20" aria-hidden="true" />
            <span className={props.backendStatus === 'Connected' ? 'text-sage' : 'text-coral'}>
              ● Backend {props.backendStatus === 'Connected' ? 'connected' : props.backendStatus.toLowerCase()}
            </span>
          </p>
          <h1 className="mt-5 text-[2.6rem] font-light leading-[1.05] tracking-tight text-white sm:text-6xl xl:text-7xl">
            Know which forecast to trust, <span className="text-cream">where and when.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-mist sm:text-lg">
            Adaptive AI–NWP forecast blending with historical verification, model reliability, uncertainty and extreme-weather risk.
          </p>
      </div>

        <form className="card glass order-3 self-end p-4 sm:p-5 lg:order-none lg:col-span-6 lg:row-start-2 xl:col-span-7" aria-label="Forecast controls" onSubmit={(e) => { e.preventDefault(); props.onRefresh() }}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <label className="col-span-2 text-xs font-semibold text-mist md:col-span-1">
              Location
              <select className="field mt-1.5" value={props.locationName} onChange={(e) => props.onLocation(e.target.value)}>
                {props.locations.map((l) => <option key={l.name}>{l.name}</option>)}
              </select>
            </label>
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
            <label className="col-span-2 text-xs font-semibold text-mist md:col-span-1">
              Variable
              <select className="field mt-1.5" value={props.variable} onChange={(e) => props.onVariable(e.target.value as Variable)}>
                {(Object.keys(VARIABLE_LABEL) as Variable[]).map((v) => <option key={v} value={v}>{VARIABLE_LABEL[v]}</option>)}
              </select>
            </label>
          </div>
          <button
            type="submit"
            className="mt-4 w-full rounded-2xl bg-cream px-5 py-3 text-sm font-bold text-ink-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={props.loadingForecasts || props.locations.length === 0}
          >
            {props.loadingForecasts ? 'Loading live forecasts…' : 'Load forecasts'}
          </button>
        </form>

      <article
        className="card relative order-2 flex min-h-[26rem] flex-col justify-between overflow-hidden p-6 sm:p-8 lg:order-none lg:col-span-6 lg:col-start-7 lg:row-span-2 lg:row-start-1 xl:col-span-5 xl:col-start-8"
        style={{ background: 'linear-gradient(160deg, rgba(58,62,140,0.85) 0%, rgba(92,78,150,0.55) 45%, rgba(214,146,120,0.55) 100%)' }}
        aria-label={`Current TrustCast forecast for ${props.locationName}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="truncate text-2xl font-medium text-white sm:text-3xl">{props.locationName}</h2>
            <p className="mt-1 text-sm text-white/70">{now ? formatTime(now.valid_time) : 'Loading forecast…'}</p>
          </div>
          <span className="flex shrink-0 items-center gap-1.5 text-xs font-semibold text-white/80">
            TrustCast blend <SparkIcon className="h-4 w-4 text-cream" />
          </span>
        </div>

        <div className="mt-6 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="num text-7xl font-extralight leading-none tracking-tighter text-white sm:text-8xl">
              {now?.blended_value !== null && now ? fmt(now.blended_value) : '—'}
              <span className="ml-1 align-top text-2xl font-light text-white/80 sm:text-3xl">{blend?.unit ?? ''}</span>
            </p>
            <p className="mt-3 text-base text-white/85">{VARIABLE_LABEL[props.variable]} · trust-weighted blend</p>
          </div>
          <div className="hidden shrink-0 sm:block">{skyIcon(props.results, openedAt)}</div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Prediction range</p>
            <p className="num mt-1 text-sm font-semibold text-white">
              {unc?.historical_lower !== null && unc?.historical_lower !== undefined ? `${fmt(unc.historical_lower)} – ${fmt(unc.historical_upper)} ${blend?.unit}` : '—'}
            </p>
          </div>
          <div className="rounded-2xl bg-black/20 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Model disagreement</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {unc?.disagreement_level ? <LevelBadge level={unc.disagreement_level} hex={LEVEL_HEX[unc.disagreement_level]} /> : <span className="text-sm text-white">—</span>}
              <span className="num text-xs text-white/75" title={unc?.disagreement_level ? DISAGREEMENT_TEXT[unc.disagreement_level] : undefined}>
                {unc?.model_spread !== null && unc?.model_spread !== undefined ? `${fmt(unc.model_spread)} ${blend?.unit} spread` : ''}
              </span>
            </div>
          </div>
          <div className="col-span-2 rounded-2xl bg-black/20 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60">
                Next {upcoming.length} h{upcoming.length ? ` · until ${formatShort(upcoming[upcoming.length - 1].valid_time)}` : ''}
              </p>
              <p className="text-[11px] text-white/60">
                {contributing.length} / {connected} models contributing
              </p>
            </div>
            <div className="mt-2 h-12" >
              <Sparkline values={upcoming.map((p) => p.blended_value)} color="#fbf1de" label={`TrustCast ${VARIABLE_LABEL[props.variable].toLowerCase()} for the next ${upcoming.length} hours`} />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
              {contributing.map((m) => (
                <span key={m.model} className="flex items-center gap-1.5 text-xs text-white/85"><ModelDot hex={modelHex(m.model)} />{m.model}</span>
              ))}
            </div>
          </div>
        </div>
        {props.loading && !blend && <p className="mt-3 text-xs text-white/70" role="status">Blending live forecasts…</p>}
      </article>
    </section>
  )
}
