import { useEffect, useState } from 'react'
import { SparkIcon } from './ui'

/**
 * Brief decorative brand transition (≈2.7 s): soft clouds, faint rain, one gentle flash, then a
 * fade into the dashboard. It never blocks input (pointer-events: none), is not a forecast, and is
 * not rendered at all for prefers-reduced-motion (see .intro in index.css).
 */
export function Intro() {
  const [done, setDone] = useState(false)
  useEffect(() => {
    // Safety net: remove the overlay even if animationend never fires.
    const timer = window.setTimeout(() => setDone(true), 3200)
    return () => window.clearTimeout(timer)
  }, [])
  if (done) return null
  return (
    <div
      className="intro"
      aria-hidden="true"
      onAnimationEnd={(e) => { if (e.target === e.currentTarget) setDone(true) }}
    >
      <div className="intro-cloud intro-cloud-a" />
      <div className="intro-cloud intro-cloud-b" />
      <div className="intro-rain" />
      <div className="intro-flash" />
      <div className="intro-mark">
        <SparkIcon className="h-9 w-9 text-cream" />
        <span className="text-3xl font-light tracking-tight text-white">TrustCast</span>
      </div>
    </div>
  )
}
