import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { API_BASE, formatCoords } from '../lib'
import type { GeocodeResult, Location, SelectedLocation } from '../types'

const MIN_CHARS = 2
const DEBOUNCE_MS = 350

type Props = {
  selected: SelectedLocation | null
  presets: Location[]
  onSelect: (location: SelectedLocation) => void
}

type Status = 'idle' | 'loading' | 'done' | 'error'

const fromGeocoder = (r: GeocodeResult): SelectedLocation => ({
  name: r.name,
  display_name: r.display_name,
  area: r.area,
  latitude: r.latitude,
  longitude: r.longitude,
  source: 'geocoder',
})

const fromPreset = (l: Location): SelectedLocation => ({
  name: l.name,
  display_name: l.name,
  area: 'India',
  latitude: l.latitude,
  longitude: l.longitude,
  source: 'preset',
})

/**
 * Real location search (Open-Meteo Geocoding API via the backend). Results come only from the API;
 * nothing is suggested from a local database except the five existing preset cities.
 */
export function LocationSearch({ selected, presets, onSelect }: Props) {
  const [editing, setEditing] = useState(false) // input shows whenever nothing is selected
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GeocodeResult[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const cache = useRef(new Map<string, GeocodeResult[]>())
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  const trimmed = query.trim()
  const showSuggestions = trimmed.length < MIN_CHARS
  const options: SelectedLocation[] = showSuggestions ? presets.map(fromPreset) : results.map(fromGeocoder)

  // Debounced search: one request after typing pauses; stale requests are aborted.
  useEffect(() => {
    if (trimmed.length < MIN_CHARS) return
    const key = trimmed.toLowerCase()
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      const cached = cache.current.get(key)
      if (cached) {
        setResults(cached)
        setStatus('done')
        return
      }
      try {
        const response = await fetch(`${API_BASE}/api/locations/search?q=${encodeURIComponent(trimmed)}`, { signal: controller.signal })
        const data = await response.json().catch(() => null)
        if (!response.ok || !data || !Array.isArray(data.results)) {
          throw new Error((data && typeof data.detail === 'string' && data.detail) || 'Location search is unavailable right now.')
        }
        cache.current.set(key, data.results)
        setResults(data.results)
        setStatus('done')
      } catch (err) {
        if (controller.signal.aborted) return
        setResults([])
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Location search failed.')
      }
    }, DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [trimmed])

  function onChange(value: string) {
    setQuery(value)
    setOpen(true)
    setActive(-1)
    setError('')
    if (value.trim().length < MIN_CHARS) {
      setResults([])
      setStatus('idle')
    } else {
      setStatus('loading')
    }
  }

  // Start every search session clean: no leftover text, results or errors from a previous one.
  function resetSearch() {
    setQuery('')
    setResults([])
    setStatus('idle')
    setError('')
    setActive(-1)
  }

  function choose(location: SelectedLocation) {
    onSelect(location)
    setEditing(false)
    setOpen(false)
    resetSearch()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      setOpen(true)
      setActive((i) => Math.min(options.length - 1, i + 1))
    } else if (event.key === 'ArrowUp') {
      setActive((i) => Math.max(0, i - 1))
    } else if (event.key === 'Enter') {
      if (open && active >= 0 && options[active]) choose(options[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
      if (selected) {
        setEditing(false)  // keep the current location; nothing is changed
        resetSearch()
      }
    } else {
      return
    }
    event.preventDefault()
  }

  if (!editing && selected) {
    return (
      <div className="field flex min-h-[46px] items-center justify-between gap-3 !bg-none">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{selected.name}</p>
          <p className="truncate text-xs text-mist">
            {selected.area && <span>{selected.area} · </span>}
            <span className="num text-mist/80">{formatCoords(selected.latitude, selected.longitude)}</span>
          </p>
        </div>
        <button
          type="button"
          className="shrink-0 rounded-full border border-white/15 px-3 py-1 text-[11px] font-semibold text-cream hover:border-cream/50"
          onClick={() => {
            resetSearch()
            setEditing(true)
            setOpen(true)
            window.setTimeout(() => inputRef.current?.focus(), 0)
          }}
          aria-label={`Change location (currently ${selected.display_name})`}
        >
          Change
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="relative">
        <svg viewBox="0 0 24 24" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-mist" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          aria-label="Search city, town or area in India"
          placeholder="Search city, town or area…"
          autoComplete="off"
          className="field !bg-none !pl-9"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
        />
      </div>

      {open && (
        <div className="absolute left-0 right-0 z-30 mt-2 overflow-hidden rounded-2xl border border-white/12 bg-ink-900/95 shadow-2xl backdrop-blur-xl">
          {showSuggestions && <p className="px-3 pt-2 text-[10px] font-bold uppercase tracking-wider text-mist">Suggestions · type to search any place in India</p>}
          {!showSuggestions && status === 'loading' && <p role="status" className="px-3 py-3 text-xs text-mist">Searching…</p>}
          {!showSuggestions && status === 'error' && <p role="alert" className="px-3 py-3 text-xs text-coral">{error}</p>}
          {!showSuggestions && status === 'done' && results.length === 0 && (
            <p role="status" className="px-3 py-3 text-xs text-mist">No locations found</p>
          )}
          {(showSuggestions || status === 'done') && options.length > 0 && (
            <ul id={listId} role="listbox" className="max-h-72 overflow-y-auto py-1">
              {options.map((o, i) => (
                <li
                  key={`${o.name}-${o.latitude}-${o.longitude}`}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(o)}
                  onMouseEnter={() => setActive(i)}
                  className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-white/10' : ''}`}
                >
                  <p className="text-sm font-semibold text-white">{o.name}</p>
                  <p className="truncate text-xs text-mist">{o.area}</p>
                  <p className="num text-[11px] text-mist/70">{formatCoords(o.latitude, o.longitude)}</p>
                </li>
              ))}
            </ul>
          )}
          {!showSuggestions && status === 'done' && results.length > 0 && (
            <p className="border-t border-white/5 px-3 py-1.5 text-[10px] text-mist/70">Place search via Open-Meteo geocoding</p>
          )}
        </div>
      )}
    </div>
  )
}
