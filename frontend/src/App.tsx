import { useEffect, useState } from 'react'

// Override this value in frontend/.env.local when the API is hosted elsewhere.
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function App() {
  const [backendStatus, setBackendStatus] = useState<string>('checking...')
  const [projectInfo, setProjectInfo] = useState<Record<string, string> | null>(null)

  useEffect(() => {
    // Check backend health
    fetch(`${API_BASE}/api/health`)
      .then((res) => res.json())
      .then((data) => {
        setBackendStatus(data.status === 'ok' ? '✅ Connected' : '❌ Error')
      })
      .catch(() => setBackendStatus('❌ Not reachable'))

    // Fetch project info
    fetch(`${API_BASE}/api/info`)
      .then((res) => res.json())
      .then((data) => setProjectInfo(data))
      .catch(() => {})
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-cyan-400">TRUSTCAST</h1>
            <p className="text-sm text-slate-400">Hybrid AI–NWP Multi-Model Forecast Blending System</p>
          </div>
          <div className="text-right">
            <span className="text-xs font-mono bg-cyan-900/40 text-cyan-300 px-2 py-1 rounded">SIH26081</span>
            <p className="text-xs text-slate-500 mt-1">Team VisionCrafters</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">

        {/* Status Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-slate-200 mb-3">System Status</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-400">Backend connection:</span>
            <span className="text-sm font-mono">{backendStatus}</span>
          </div>
          {projectInfo && (
            <div className="mt-3 text-xs text-slate-500 font-mono">
              Stage: {projectInfo.stage} | Project: {projectInfo.project}
            </div>
          )}
        </div>

        {/* Placeholder Sections */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PlaceholderCard title="📊 Forecast" description="Multi-model NWP forecast display will appear here." />
          <PlaceholderCard title="🛡️ Trust Engine" description="Dynamic model trust scoring and weighting will appear here." />
          <PlaceholderCard title="📈 Uncertainty" description="Prediction confidence intervals and uncertainty bands will appear here." />
          <PlaceholderCard title="⚠️ Extreme Events" description="Extreme weather event detection and alerts will appear here." />
        </div>

        {/* Footer */}
        <footer className="text-center text-xs text-slate-600 pt-6 border-t border-slate-800">
          TrustCast — Smart India Hackathon 2026 — Team VisionCrafters
        </footer>
      </main>
    </div>
  )
}

function PlaceholderCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-5 hover:border-slate-700 transition-colors">
      <h3 className="text-base font-semibold text-slate-300 mb-2">{title}</h3>
      <p className="text-sm text-slate-500">{description}</p>
      <div className="mt-3 text-xs text-slate-600 italic">Coming in a future step</div>
    </div>
  )
}

export default App
