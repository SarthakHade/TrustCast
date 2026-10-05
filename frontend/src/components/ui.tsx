import type { ReactNode } from 'react'
import type { ModelStatus } from '../types'

// ---------- Thin-line weather icons (decorative unless given a label) ----------
type IconProps = { className?: string; label?: string }

function Svg({ className = 'h-6 w-6', label, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {label && <title>{label}</title>}
      {children}
    </svg>
  )
}

const CLOUD = 'M14 34h20a7 7 0 0 0 .8-13.95A10 10 0 0 0 15.4 22 6 6 0 0 0 14 34Z'

export const SunIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="24" cy="24" r="7" />
    {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
      <line key={a} x1="24" y1="9" x2="24" y2="12.5" transform={`rotate(${a} 24 24)`} />
    ))}
  </Svg>
)
export const CloudIcon = (p: IconProps) => <Svg {...p}><path d={CLOUD} /></Svg>
export const PartlyCloudyIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="30" cy="17" r="5.5" />
    <line x1="30" y1="6.5" x2="30" y2="8.5" /><line x1="39.5" y1="17" x2="41.5" y2="17" /><line x1="36.8" y1="10.2" x2="38.2" y2="8.8" />
    <path d="M12 38h18a6 6 0 0 0 .7-11.96A8.5 8.5 0 0 0 14.2 27 5.2 5.2 0 0 0 12 38Z" />
  </Svg>
)
export const RainIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 29h20a7 7 0 0 0 .8-13.95A10 10 0 0 0 15.4 17 6 6 0 0 0 14 29Z" />
    <line x1="17" y1="34" x2="15" y2="39" /><line x1="24" y1="34" x2="22" y2="39" /><line x1="31" y1="34" x2="29" y2="39" />
  </Svg>
)
export const MoonIcon = (p: IconProps) => (
  <Svg {...p}><path d="M31 9a14 14 0 1 0 8 25A12 12 0 0 1 31 9Z" /></Svg>
)
export const WindIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 18h21a5 5 0 1 0-5-5" /><path d="M8 26h29a5 5 0 1 1-5 5" /><path d="M8 34h14" />
  </Svg>
)
export const ThermometerIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 28V10a3 3 0 0 1 6 0v18a7 7 0 1 1-6 0Z" /><line x1="24" y1="16" x2="24" y2="32" />
  </Svg>
)
export const SnowIcon = (p: IconProps) => (
  <Svg {...p}>
    <line x1="24" y1="8" x2="24" y2="40" /><line x1="10" y1="16" x2="38" y2="32" /><line x1="10" y1="32" x2="38" y2="16" />
    <path d="M20 10l4 4 4-4M20 38l4-4 4 4" />
  </Svg>
)
export const DropIcon = (p: IconProps) => (
  <Svg {...p}><path d="M24 8c6 8 10 13.5 10 19a10 10 0 0 1-20 0c0-5.5 4-11 10-19Z" /></Svg>
)
export const HumidityIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M24 8c6 8 10 13.5 10 19a10 10 0 0 1-20 0c0-5.5 4-11 10-19Z" /><line x1="19" y1="32" x2="29" y2="22" />
    <circle cx="20" cy="24" r="1.2" /><circle cx="28" cy="31" r="1.2" />
  </Svg>
)
export const SparkIcon = (p: IconProps) => (
  <Svg {...p}><path d="M24 6c1.2 9.5 8.5 16.8 18 18-9.5 1.2-16.8 8.5-18 18-1.2-9.5-8.5-16.8-18-18 9.5-1.2 16.8-8.5 18-18Z" /></Svg>
)
export const AlertIcon = (p: IconProps) => (
  <Svg {...p}><path d="M24 7 43 40H5L24 7Z" /><line x1="24" y1="19" x2="24" y2="29" /><circle cx="24" cy="34" r="0.8" fill="currentColor" /></Svg>
)

// ---------- Layout primitives ----------
export function SectionHeader({ index, question, title, titleId, children }: { index: string; question: string; title: string; titleId?: string; children?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:mb-8 lg:flex-row lg:items-end lg:justify-between lg:gap-10">
      <div className="max-w-3xl">
        <p className="eyebrow flex items-center gap-3">
          <span className="num text-cream/80">{index}</span>
          <span className="h-px w-8 bg-white/20" aria-hidden="true" />
          <span>{question}</span>
        </p>
        <h2 id={titleId} className="mt-3 text-3xl font-light tracking-tight text-white sm:text-4xl">{title}</h2>
      </div>
      {children}
    </header>
  )
}

/** Vertical connector between story chapters. */
export function Connector() {
  return (
    <div className="flex justify-center py-8 sm:py-12" aria-hidden="true">
      <div className="flex flex-col items-center gap-1.5">
        <span className="h-10 w-px bg-gradient-to-b from-transparent via-white/25 to-white/5" />
        <span className="h-1.5 w-1.5 rounded-full bg-cream/60" />
      </div>
    </div>
  )
}

export function Notice({ tone = 'error', children }: { tone?: 'error' | 'warn' | 'info'; children: ReactNode }) {
  const style = {
    error: 'border-coral/40 bg-coral/10 text-rose-100',
    warn: 'border-amberish/40 bg-amberish/10 text-amber-100',
    info: 'border-white/10 bg-white/5 text-slate-200',
  }[tone]
  return (
    <p role={tone === 'error' ? 'alert' : 'status'} className={`rounded-2xl border px-4 py-3 text-sm ${style}`}>
      {children}
    </p>
  )
}

export function Loading({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="flex items-center gap-3 text-sm text-mist">
      <span className="h-2 w-2 animate-pulse rounded-full bg-cream/70" aria-hidden="true" />
      {children}
    </p>
  )
}

const STATUS_STYLE: Record<ModelStatus, { label: string; dot: string; text: string }> = {
  live: { label: 'Live', dot: 'bg-sage', text: 'text-sage' },
  waiting: { label: 'Waiting for run', dot: 'bg-amberish', text: 'text-amberish' },
  unavailable: { label: 'Unavailable', dot: 'bg-amberish', text: 'text-amberish' },
  inactive: { label: 'Not running', dot: 'bg-slate-500', text: 'text-slate-400' },
  data_unavailable: { label: 'Data unavailable', dot: 'bg-amberish', text: 'text-amberish' },
  adapter_ready: { label: 'Adapter ready', dot: 'bg-slate-400', text: 'text-slate-300' },
  error: { label: 'Error', dot: 'bg-coral', text: 'text-coral' },
}

export function StatusPill({ status }: { status: ModelStatus }) {
  const s = STATUS_STYLE[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden="true" />
      {s.label}
    </span>
  )
}

/** Level badge: always shows the level as text, colour is only a secondary cue. */
export function LevelBadge({ level, hex, size = 'sm' }: { level: string; hex: string; size?: 'sm' | 'md' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-bold uppercase tracking-wider ${size === 'md' ? 'px-3 py-1 text-xs' : 'px-2.5 py-0.5 text-[11px]'}`}
      style={{ color: hex, background: `${hex}1f`, border: `1px solid ${hex}55` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex }} aria-hidden="true" />
      {level.replace('_', ' ')}
    </span>
  )
}

export function ModelDot({ hex }: { hex: string }) {
  return <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: hex }} aria-hidden="true" />
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0" title={hint}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-mist/80">{label}</p>
      <p className="num mt-0.5 truncate text-sm font-semibold text-slate-100">{value}</p>
    </div>
  )
}

