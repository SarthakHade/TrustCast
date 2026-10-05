import { useCallback, useEffect, useRef, useState } from 'react'
import { Blend } from './components/Blend'
import { EvaluationView } from './components/EvaluationView'
import { Hero } from './components/Hero'
import { Intro } from './components/Intro'
import { Risk } from './components/Risk'
import { RiskAlert } from './components/RiskAlert'
import { Sources } from './components/Sources'
import { TrustEngine } from './components/TrustEngine'
import { Uncertainty } from './components/Uncertainty'
import { Verification } from './components/Verification'
import { Connector, SparkIcon } from './components/ui'
import { API_BASE, fetchModels, highRiskAlert } from './lib'
import type {
  BlendResponse,
  EnsembleGuidance,
  Location,
  Model,
  PerformanceResponse,
  SelectedLocation,
  ProviderForecast,
  RiskResponse,
  TrustResponse,
  UncertaintyResponse,
  Variable,
} from './types'

const STORY = [
  { id: 'sources', index: '01', label: 'Forecasts' },
  { id: 'verification', index: '02', label: 'Verification' },
  { id: 'trust', index: '03', label: 'Trust' },
  { id: 'blend', index: '04', label: 'Blend' },
  { id: 'uncertainty', index: '05', label: 'Uncertainty' },
  { id: 'risk', index: '06', label: 'Risk' },
]

function App() {
  const [backendStatus, setBackendStatus] = useState('checking')
  const [locations, setLocations] = useState<Location[]>([])
  const [models, setModels] = useState<Model[]>([])
  // Forecast context: exact selected coordinates (preset city or real geocoder result).
  const [selectedLocation, setSelectedLocation] = useState<SelectedLocation | null>(null)
  const [forecastDays, setForecastDays] = useState(2)
  const [results, setResults] = useState<ProviderForecast[]>([])
  const [loadingForecasts, setLoadingForecasts] = useState(false)
  const [forecastError, setForecastError] = useState('')
  const [perfVariable, setPerfVariable] = useState<Variable>('temperature')
  const [perfLeadDay, setPerfLeadDay] = useState(1)
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null)
  const [loadingPerformance, setLoadingPerformance] = useState(false)
  const [performanceError, setPerformanceError] = useState('')
  const [trust, setTrust] = useState<TrustResponse | null>(null)
  const [trustError, setTrustError] = useState('')
  const [blend, setBlend] = useState<BlendResponse | null>(null)
  const [blendError, setBlendError] = useState('')
  const [uncertainty, setUncertainty] = useState<UncertaintyResponse | null>(null)
  const [uncertaintyError, setUncertaintyError] = useState('')
  const [risks, setRisks] = useState<RiskResponse | null>(null)
  const [riskError, setRiskError] = useState('')
  const [loadingRisks, setLoadingRisks] = useState(false)
  const [selectedTime, setSelectedTime] = useState<string | null>(null)
  const [openedAt] = useState(() => Date.now())
  const [activeSection, setActiveSection] = useState('')
  const [ensemble, setEnsemble] = useState<EnsembleGuidance | null>(null)
  // Two views: the public forecast (default) and the advanced evaluation (#/evaluation).
  const [view, setView] = useState<'dashboard' | 'evaluation'>(() => (window.location.hash === '#/evaluation' ? 'evaluation' : 'dashboard'))
  useEffect(() => {
    const onHash = () => setView(window.location.hash === '#/evaluation' ? 'evaluation' : 'dashboard')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  // Alerts the user dismissed, by a key of location + hazard + peak time (so re-renders never re-show them).
  const [dismissedAlerts, setDismissedAlerts] = useState<string[]>([])
  const forecastRequest = useRef(0)

  // Highlight the last pipeline step whose section top has passed the upper third of the viewport.
  useEffect(() => {
    const update = () => {
      const line = window.innerHeight * 0.33
      let current = ''
      for (const s of STORY) {
        const el = document.getElementById(s.id)
        if (el && el.getBoundingClientRect().top <= line) current = s.id
      }
      setActiveSection(current)
    }
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    const initial = window.requestAnimationFrame(update)
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
      window.cancelAnimationFrame(initial)
    }
  }, [])

  // Step 2: live source forecasts. Stale responses (older request ids) are ignored.
  const loadForecasts = useCallback(async (location: Pick<Location, 'latitude' | 'longitude'>, days: number) => {
    const requestId = ++forecastRequest.current
    setLoadingForecasts(true)
    setForecastError('')
    try {
      const response = await fetch(
        `${API_BASE}/api/weather/all-models?latitude=${location.latitude}&longitude=${location.longitude}&forecast_days=${days}`,
      )
      if (!response.ok) throw new Error('Weather sources could not be reached.')
      const data = await response.json()
      if (requestId === forecastRequest.current) setResults(data.results)
    } catch (error) {
      if (requestId === forecastRequest.current) setForecastError(error instanceof Error ? error.message : 'Weather request failed.')
    } finally {
      if (requestId === forecastRequest.current) setLoadingForecasts(false)
    }
  }, [])

  useEffect(() => {
    async function bootstrap() {
      try {
        const [healthResponse, locationsResponse, modelsResponse] = await Promise.all([
          fetch(`${API_BASE}/api/health`),
          fetch(`${API_BASE}/api/weather/locations`),
          fetch(`${API_BASE}/api/weather/models`),
        ])
        setBackendStatus(healthResponse.ok ? 'Connected' : 'Error')

        if (!locationsResponse.ok || !modelsResponse.ok) {
          throw new Error('The forecast service is not responding. Please try again shortly.')
        }

        const locationData: unknown = await locationsResponse.json()
        const modelData: unknown = await modelsResponse.json()
        if (
          !Array.isArray(locationData)
          || !modelData
          || typeof modelData !== 'object'
          || !('models' in modelData)
          || !Array.isArray(modelData.models)
        ) {
          throw new Error('The forecast service returned an unexpected response. Please try again shortly.')
        }
        const parsedLocations = locationData as Location[]
        setLocations(parsedLocations)
        setModels(modelData.models as Model[])
        const defaultLocation = parsedLocations.find((location) => location.name === 'Mumbai') ?? parsedLocations[0]
        if (defaultLocation) {
          setSelectedLocation({
            name: defaultLocation.name,
            display_name: defaultLocation.name,
            area: 'India',
            latitude: defaultLocation.latitude,
            longitude: defaultLocation.longitude,
            source: 'preset',
          })
          await loadForecasts(defaultLocation, 2)
        }
      } catch (error) {
        setForecastError(error instanceof Error ? error.message : 'Forecasts could not be loaded. Please try again shortly.')
        setBackendStatus((currentStatus) => (currentStatus === 'Connected' ? currentStatus : 'Not reachable'))
      }
    }
    void bootstrap()
  }, [loadForecasts])

  // Source cards follow the selected location / horizon: reload from the events that change them.
  function changeLocation(location: SelectedLocation) {
    setSelectedLocation(location)
    setSelectedTime(null)
    setResults([])
    void loadForecasts(location, forecastDays)
  }
  function changeForecastDays(days: number) {
    setForecastDays(days)
    setSelectedTime(null)
    if (selectedLocation) void loadForecasts(selectedLocation, days)
  }

  // Steps 3 → 7, run sequentially so each backend step reuses the previous step's cache.
  useEffect(() => {
    if (!selectedLocation) return
    const place = selectedLocation
    let cancelled = false
    async function loadPipeline() {
      // Never show the previous location's / variable's numbers while the new ones load.
      setPerformance(null)
      setTrust(null)
      setBlend(null)
      setUncertainty(null)
      setRisks(null)
      setEnsemble(null)
      setLoadingPerformance(true)
      setPerformanceError('')
      setTrustError('')
      setBlendError('')
      setUncertaintyError('')
      const params = new URLSearchParams({
        latitude: String(place.latitude),
        longitude: String(place.longitude),
        name: place.name,
        variable: perfVariable,
        lead_day: String(perfLeadDay),
        days: '21',
      })
      try {
        const data = await fetchModels<PerformanceResponse>(`${API_BASE}/api/performance?${params}`, 'The model track record could not be loaded right now.')
        if (!cancelled) setPerformance(data)
        try {
          const trustData = await fetchModels<TrustResponse>(`${API_BASE}/api/trust?${params}`, 'Model influence could not be worked out right now.')
          if (!cancelled) setTrust(trustData)
        } catch (error) {
          if (!cancelled) {
            setTrust(null)
            setTrustError(error instanceof Error ? error.message : 'Model influence could not be worked out right now.')
          }
        }
        try {
          const blendParams = new URLSearchParams(params)
          blendParams.set('forecast_days', String(forecastDays))
          const blendData = await fetchModels<BlendResponse>(`${API_BASE}/api/blend?${blendParams}`, 'The TrustCast forecast could not be built right now.', 'forecast')
          if (!cancelled) setBlend(blendData)
          try {
            const uncertaintyData = await fetchModels<UncertaintyResponse>(`${API_BASE}/api/uncertainty?${blendParams}`, 'Forecast agreement could not be checked right now.', 'forecast')
            if (!cancelled) setUncertainty(uncertaintyData)
          } catch (error) {
            if (!cancelled) {
              setUncertainty(null)
              setUncertaintyError(error instanceof Error ? error.message : 'Forecast agreement could not be checked right now.')
            }
          }
        } catch (error) {
          if (!cancelled) {
            setBlend(null)
            setUncertainty(null)
            setBlendError(error instanceof Error ? error.message : 'The TrustCast forecast could not be built right now.')
            setUncertaintyError('Forecast agreement is unavailable because the TrustCast forecast could not be built.')
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPerformance(null)
          setTrust(null)
          setBlend(null)
          setUncertainty(null)
          const message = error instanceof Error ? error.message : 'The model track record could not be loaded right now.'
          setPerformanceError(message)
          setTrustError('Not enough history yet to weigh the models for this location.')
          setBlendError('The TrustCast forecast is unavailable because the models could not be weighed.')
          setUncertaintyError('Forecast agreement is unavailable because the models could not be weighed.')
        }
      } finally {
        if (!cancelled) setLoadingPerformance(false)
      }

      if (!cancelled) {
        setLoadingRisks(true)
        setRiskError('')
      }
      try {
        const riskParams = new URLSearchParams({
          latitude: String(place.latitude),
          longitude: String(place.longitude),
          name: place.name,
          lead_day: String(perfLeadDay),
          forecast_days: String(forecastDays),
          days: '21',
        })
        const riskData = await fetchModels<RiskResponse>(`${API_BASE}/api/risks?${riskParams}`, 'Weather risk could not be checked right now.', 'risks')
        if (!cancelled) setRisks(riskData)
        // Optional ensemble guidance (NOAA AIGEFS member counts); the risk view works without it.
        try {
          const ensembleData = await fetchModels<EnsembleGuidance>(`${API_BASE}/api/ensemble?${riskParams}`, 'Ensemble guidance unavailable.', 'status')
          if (!cancelled) setEnsemble(ensembleData)
        } catch {
          if (!cancelled) setEnsemble(null)
        }
      } catch (error) {
        if (!cancelled) {
          setRisks(null)
          setRiskError(error instanceof Error ? error.message : 'Weather risk could not be checked right now.')
        }
      } finally {
        if (!cancelled) setLoadingRisks(false)
      }
    }
    void loadPipeline()
    return () => { cancelled = true }
  }, [selectedLocation, perfVariable, perfLeadDay, forecastDays])

  // HIGH risks from the backend risk engine only; shown once the risk result for this location is in.
  const alert = highRiskAlert(risks, selectedLocation, loadingRisks, dismissedAlerts)

  return (
    <div className="mx-auto w-full max-w-[1360px] px-4 pb-12 sm:px-6 lg:px-10">
      <Intro />
      {alert.show && view === 'dashboard' && (
        <RiskAlert
          risks={alert.risks}
          locationName={selectedLocation?.name ?? ''}
          onDismiss={() => setDismissedAlerts((keys) => [...keys, alert.key])}
        />
      )}
      <header className="flex items-center justify-between gap-4 py-6 sm:py-8">
        <a href="#top" className="flex items-center gap-2.5" aria-label="TrustCast home">
          <SparkIcon className="h-7 w-7 text-cream" />
          <span className="text-xl font-semibold tracking-tight text-white">TrustCast</span>
        </a>
        {view === 'dashboard'
          ? <a href="#/evaluation" className="text-xs text-mist hover:text-white">Evaluation</a>
          : <a href="#top" className="text-xs text-mist hover:text-white">Forecast</a>}
      </header>

      {view === 'evaluation' ? (
        <main id="top">
          <EvaluationView location={selectedLocation} presets={locations} onBack={() => { window.location.hash = '#top' }} />
        </main>
      ) : (
      <main id="top">
        <Hero
          backendStatus={backendStatus}
          locations={locations}
          selected={selectedLocation}
          onLocation={changeLocation}
          forecastDays={forecastDays}
          onForecastDays={changeForecastDays}
          variable={perfVariable}
          onVariable={setPerfVariable}
          leadDay={perfLeadDay}
          onLeadDay={setPerfLeadDay}
          loadingForecasts={loadingForecasts}
          onRefresh={() => selectedLocation && void loadForecasts(selectedLocation, forecastDays)}
          results={results}
          blend={blend}
          uncertainty={uncertainty}
          risks={risks}
          loading={loadingPerformance}
          openedAt={openedAt}
        />

        <PipelineNav active={activeSection} />

        <div className="mt-12 sm:mt-16">
          <Sources
            models={models}
            results={results}
            loading={loadingForecasts}
            error={forecastError}
            openedAt={openedAt}
            contributors={blend?.models_used.map((m) => m.model) ?? []}
            exclusions={Object.fromEntries((blend?.excluded_models ?? []).map((m) => [m.model, m.reason]))}
          />
          <Connector />
          <Verification performance={performance} loading={loadingPerformance} error={performanceError} locationName={selectedLocation?.name ?? ''} />
          <Connector />
          <TrustEngine trust={trust} applied={blend?.models_used ?? null} loading={loadingPerformance} error={trustError} locationName={selectedLocation?.name ?? ''} />
          <Connector />
          <Blend
            blend={blend}
            uncertainty={uncertainty}
            results={results}
            loading={loadingPerformance}
            error={blendError}
            locationName={selectedLocation?.name ?? ''}
            selectedTime={selectedTime}
            openedAt={openedAt}
            onSelectTime={setSelectedTime}
          />
          <Connector />
          <Uncertainty
            uncertainty={uncertainty}
            loading={loadingPerformance}
            error={uncertaintyError}
            selectedTime={selectedTime}
            openedAt={openedAt}
            onSelectTime={setSelectedTime}
          />
          <Connector />
          <Risk risks={risks} ensemble={ensemble} loading={loadingRisks || loadingPerformance} error={riskError} locationName={selectedLocation?.name ?? ''} />
        </div>
      </main>
      )}

      <footer className="mt-16 flex flex-col gap-6 border-t border-white/5 pt-8 text-xs text-mist sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold text-white"><SparkIcon className="h-5 w-5 text-cream/70" />TrustCast</p>
          <p className="mt-1">Multi-model weather intelligence</p>
        </div>
        <ul className="space-y-1 sm:text-right">
          <li>Forecast data via Open-Meteo</li>
          <li>Historical reference: ERA5</li>
          <li>Risk indicators are not official warnings</li>
        </ul>
      </footer>
    </div>
  )
}

/** The six-step journey. Sticky on wide screens; the step in view is highlighted. */
function PipelineNav({ active }: { active: string }) {
  return (
    <nav aria-label="Forecast pipeline" className="mt-10 sm:mt-12 lg:sticky lg:top-3 lg:z-20">
      <ol className="grid grid-cols-3 gap-1.5 rounded-[22px] border border-white/8 bg-ink-900/70 p-1.5 backdrop-blur-md sm:grid-cols-6">
        {STORY.map((s) => {
          const isActive = s.id === active
          return (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                aria-current={isActive ? 'step' : undefined}
                className={`flex flex-col items-center gap-0.5 rounded-2xl px-1 py-2 text-[13px] transition sm:text-sm lg:flex-row lg:justify-start lg:gap-2 lg:px-3 lg:py-2.5 ${isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'}`}
              >
                <span className={`num text-[11px] sm:text-xs ${isActive ? 'text-cream' : 'text-cream/50'}`}>{s.index}</span>
                <span className="max-w-full truncate">{s.label}</span>
              </a>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default App
