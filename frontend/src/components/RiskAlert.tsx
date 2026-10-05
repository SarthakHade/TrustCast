import { riskWhen } from '../lib'
import type { RiskIndicator } from '../types'
import { AlertIcon } from './ui'

const PHRASE: Record<string, string> = {
  HEAT: 'Very high temperatures are',
  COLD: 'Very low temperatures are',
  HEAVY_RAIN: 'Heavy rainfall is',
  HIGH_WIND: 'Strong winds are',
}

type Props = {
  /** Only risks the backend classified as HIGH. */
  risks: RiskIndicator[]
  locationName: string
  onDismiss: () => void
}

/** In-app forecast alert for HIGH risk levels. Never blocks the page; dismissible. */
export function RiskAlert({ risks, locationName, onDismiss }: Props) {
  if (!risks.length) return null
  return (
    <div
      role="alert"
      className="reveal fixed inset-x-4 bottom-4 z-40 rounded-2xl border border-coral/50 bg-ink-900/95 p-4 shadow-2xl backdrop-blur-md sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[24rem]"
    >
      <div className="flex items-start gap-3">
        <AlertIcon className="mt-0.5 h-6 w-6 shrink-0 text-coral" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-coral">High weather risk</p>
          <ul className="mt-1.5 space-y-1 text-sm text-white">
            {risks.map((r) => (
              <li key={r.risk_type}>
                {PHRASE[r.risk_type] ?? `${r.title} is`} possible in {locationName || 'this location'} {riskWhen(r)}.
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-mist">TrustCast forecast alert — not an official warning.</p>
          <a href="#risk" onClick={onDismiss} className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-cream hover:text-white">
            View risk <span aria-hidden="true">→</span>
          </a>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="-mr-1 -mt-1 rounded-full p-1.5 text-mist hover:bg-white/10 hover:text-white"
          aria-label="Dismiss alert"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </div>
  )
}
