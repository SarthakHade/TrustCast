import { useId } from 'react'
import { smoothLine, type Pt } from '../lib'

/** Tiny trend line of real values (no axes). Gaps (null) break the line. */
export function Sparkline({ values, color, height = 44, fill = true, label }: { values: (number | null)[]; color: string; height?: number; fill?: boolean; label?: string }) {
  const gradientId = useId()
  const finite = values.filter((v): v is number => v !== null)
  if (finite.length < 2) return null
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min || 1
  const width = 200
  const pts = values.map((v, i) => (v === null ? null : { x: (i / (values.length - 1)) * width, y: 4 + (1 - (v - min) / span) * (height - 8) }))
  const line = smoothLine(pts)
  const firstIdx = pts.findIndex((p) => p !== null)
  const lastIdx = pts.length - 1 - [...pts].reverse().findIndex((p) => p !== null)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-full w-full" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {label && <title>{label}</title>}
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && firstIdx >= 0 && !values.includes(null) && (
        <path d={`${line}L${(pts[lastIdx] as Pt).x},${height}L${(pts[firstIdx] as Pt).x},${height}Z`} fill={`url(#${gradientId})`} />
      )}
      <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
    </svg>
  )
}
