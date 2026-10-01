import { useCallback, useEffect, useRef, useState } from 'react'
import { Blend } from './components/Blend'
import { Hero } from './components/Hero'
import { Limitations } from './components/Limitations'
import { Risk } from './components/Risk'
import { Sources } from './components/Sources'
import { TrustEngine } from './components/TrustEngine'
import { Uncertainty } from './components/Uncertainty'
import { Verification } from './components/Verification'
import { Connector, SparkIcon } from './components/ui'
import { API_BASE, VARIABLE_LABEL, fetchModels } from './lib'
import type {
  BlendResponse,
  Location,
  Model,
  PerformanceResponse,
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
  const [selectedLocationName, setSelectedLocationName] = useState('Mumbai')
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
  const forecastRequest = useRef(0)

  // Step 2: live source forecasts. Stale responses (older request ids) are ignored.
  const loadForecasts = useCallback(async (location: Location, days: number) => {
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
          throw new Error('Weather endpoints are unavailable. Restart the FastAPI backend from the updated TrustCast folder.')
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
          throw new Error('The backend returned an invalid weather configuration response.')
        }
        const parsedLocations = locationData as Location[]
        setLocations(parsedLocations)
        setModels(modelData.models as Model[])
        const defaultLocation = parsedLocations.find((location) => location.name === 'Mumbai') ?? parsedLocations[0]
        if (defaultLocation) {
          setSelectedLocationName(defaultLocation.name)
          await loadForecasts(defaultLocation, 2)
        }
      } catch (error) {
        setForecastError(error instanceof Error ? error.message : 'Weather configuration could not be loaded.')
        setBackendStatus((currentStatus) => (currentStatus === 'Connected' ? currentStatus : 'Not reachable'))
      }
    }
    void bootstrap()
  }, [loadForecasts])

  const selectedLocation = locations.find((location) => location.name === selectedLocationName)

  // Source cards follow the selected location / horizon: reload from the events that change them.
  function changeLocation(name: string) {
    setSelectedLocationName(name)
    setSelectedTime(null)
    const location = locations.find((l) => l.name === name)
    if (location) void loadForecasts(location, forecastDays)
  }
  function changeForecastDays(days: number) {
    setForecastDays(days)
    setSelectedTime(null)
    if (selectedLocation) void loadForecasts(selectedLocation, days)
  }

  // Steps 3 → 7, run sequentially so each backend step reuses the previous step's cache.
  useEffect(() => {
    if (locations.length === 0) return
    let cancelled = false
    async function loadPipeline() {
      setLoadingPerformance(true)
      setPerformanceError('')
      setTrustError('')
      setBlendError('')
      setUncertaintyError('')
      const params = new URLSearchParams({
        location: selectedLocationName,
        variable: perfVariable,
        lead_day: String(perfLeadDay),
        days: '21',
      })
      try {
        const data = await fetchModels<PerformanceResponse>(`${API_BASE}/api/performance?${params}`, 'Historical verification could not be loaded.')
        if (!cancelled) setPerformance(data)
        try {
          const trustData = await fetchModels<TrustResponse>(`${API_BASE}/api/trust?${params}`, 'Trust weights could not be calculated.')
          if (!cancelled) setTrust(trustData)
        } catch (error) {
          if (!cancelled) {
            setTrust(null)
            setTrustError(error instanceof Error ? error.message : 'Trust Engine request failed.')
          }
        }
        try {
          const blendParams = new URLSearchParams(params)
          blendParams.set('forecast_days', String(forecastDays))
          const blendData = await fetchModels<BlendResponse>(`${API_BASE}/api/blend?${blendParams}`, 'Blended forecast could not be calculated.', 'forecast')
          if (!cancelled) setBlend(blendData)
          try {
            const uncertaintyData = await fetchModels<UncertaintyResponse>(`${API_BASE}/api/uncertainty?${blendParams}`, 'Uncertainty could not be calculated.', 'forecast')
            if (!cancelled) setUncertainty(uncertaintyData)
          } catch (error) {
            if (!cancelled) {
              setUncertainty(null)
              setUncertaintyError(error instanceof Error ? error.message : 'Uncertainty request failed.')
            }
          }
        } catch (error) {
          if (!cancelled) {
            setBlend(null)
            setUncertainty(null)
            setBlendError(error instanceof Error ? error.message : 'Blended forecast request failed.')
            setUncertaintyError('Uncertainty cannot be calculated because the blended forecast is unavailable.')
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPerformance(null)
          setTrust(null)
          setBlend(null)
          setUncertainty(null)
          const message = error instanceof Error ? error.message : 'Historical verification request failed.'
          setPerformanceError(message)
          setTrustError(`Insufficient historical data to calculate trust. ${message}`)
          setBlendError('Blended forecast unavailable because trust weights could not be calculated.')
          setUncertaintyError('Uncertainty cannot be calculated because trust weights are unavailable.')
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
          location: selectedLocationName,
          lead_day: String(perfLeadDay),
          forecast_days: String(forecastDays),
          days: '21',
        })
        const riskData = await fetchModels<RiskResponse>(`${API_BASE}/api/risks?${riskParams}`, 'Risk assessment could not be loaded.', 'risks')
        if (!cancelled) setRisks(riskData)
      } catch (error) {
        if (!cancelled) {
          setRisks(null)
          setRiskError(error instanceof Error ? error.message : 'Risk assessment request failed.')
        }
      } finally {
        if (!cancelled) setLoadingRisks(false)
      }
    }
    void loadPipeline()
    return () => { cancelled = true }
  }, [locations.length, selectedLocationName, perfVariable, perfLeadDay, forecastDays])

  return (
    <div className="mx-auto w-full max-w-[1360px] px-4 pb-16 sm:px-6 lg:px-10">
      <header className="flex items-center justify-between gap-4 py-6 sm:py-8">
        <a href="#top" className="flex items-center gap-2.5" aria-label="TrustCast home">
          <SparkIcon className="h-7 w-7 text-cream" />
          <span className="text-xl font-semibold tracking-tight text-white">TrustCast</span>
        </a>
        <p className="hidden text-xs text-mist sm:block">Hybrid AI–NWP Multi-Model Forecast Blending System</p>
      </header>

      <main id="top">
        <Hero
          backendStatus={backendStatus}
          locations={locations}
          locationName={selectedLocationName}
          onLocation={changeLocation}
          forecastDays={forecastDays}
          onForecastDays={changeForecastDays}
          variable={perfVariable}
          onVariable={setPerfVariable}
          leadDay={perfLeadDay}
          onLeadDay={setPerfLeadDay}
          loadingForecasts={loadingForecasts}
          onRefresh={() => selectedLocation && void loadForecasts(selectedLocation, forecastDays)}
          models={models}
          results={results}
          blend={blend}
          uncertainty={uncertainty}
          loading={loadingPerformance}
          openedAt={openedAt}
        />

        <nav aria-label="Story" className="mt-8 sm:mt-10">
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {STORY.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="flex items-center gap-2 rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-2.5 text-sm text-slate-200 transition hover:border-white/20 hover:bg-white/[0.06]">
                  <span className="num text-xs text-cream/70">{s.index}</span>{s.label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="mt-12 sm:mt-16">
          <Sources
            models={models}
            results={results}
            loading={loadingForecasts}
            error={forecastError}
            openedAt={openedAt}
            contributors={blend?.models_used.map((m) => m.model) ?? []}
            exclusions={Object.fromEntries((blend?.excluded_models ?? []).map((m) => [m.model, m.reason]))}
            variableLabel={VARIABLE_LABEL[perfVariable]}
          />
          <Connector />
          <Verification performance={performance} loading={loadingPerformance} error={performanceError} locationName={selectedLocationName} />
          <Connector />
          <TrustEngine trust={trust} loading={loadingPerformance} error={trustError} locationName={selectedLocationName} />
          <Connector />
          <Blend
            blend={blend}
            uncertainty={uncertainty}
            loading={loadingPerformance}
            error={blendError}
            locationName={selectedLocationName}
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
          <Risk risks={risks} loading={loadingRisks} error={riskError} locationName={selectedLocationName} />
          <div className="mt-16">
            <Limitations />
          </div>
        </div>
      </main>

      <footer className="mt-16 flex flex-col items-center gap-2 border-t border-white/5 pt-8 text-center text-xs text-mist">
        <SparkIcon className="h-5 w-5 text-cream/60" />
        <p>TrustCast · SIH26081 · Team VisionCrafters · Smart India Hackathon 2026</p>
        <p className="text-mist/70">Live model data via Open-Meteo · Historical reference: ERA5 reanalysis · Forecast-based risk indicators, not official warnings.</p>
      </footer>
    </div>
  )
}

export default App
