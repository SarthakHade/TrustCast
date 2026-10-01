const LIMITATIONS = [
  'ERA5 is a gridded reanalysis used as the historical reference, not direct station observations. It is produced by ECMWF, which may slightly favour the ECMWF models.',
  'The current verification period is only 21 days, covering a single season.',
  'Reliability, trust weights and uncertainty are all derived from the same historical period (calibration and evaluation are not yet separated), so future uncertainty coverage is not guaranteed.',
  'The current blend uses one weight set for the whole forecast period, taken from the selected lead-day configuration.',
  'The prediction range has a fixed width at every hour; it does not widen when models disagree more. Model disagreement is shown separately.',
  'Heat and cold thresholds are demo thresholds, not local climatological warning thresholds. The rain (64.5 / 115.6 mm per 24 h) and wind (41 / 62 km/h) cut-offs are referenced to published categories, but the output is not an official warning.',
  'Production deployment should use longer rolling historical windows and out-of-sample validation.',
  "NCUM-G: NCMRWF's official API and SWFDP portal publish chart products only (checked on every refresh), so no NCUM-G values are ingested, scored, weighted or blended until a machine-readable feed is available.",
  'DWD AICON: official runs are published on DWD open data, but as GRIB2 on the native icosahedral grid (CCSDS-compressed); point extraction needs a GRIB toolchain that is not part of this prototype.',
  'NOAA AIGEFS: live 31-member ensemble (temperature, wind; 6-hourly). No archived AIGEFS forecasts exist for verification, so its reliability is not calibrated and it is not weighted; its ensemble spread is shown as an uncertainty source. Precipitation is not ingested.',
  'GraphCast and Pangu-Weather are optional and not running: no inference pipeline or verified public point-forecast feed is connected.',
]

export function Limitations() {
  return (
    <section id="limitations" aria-labelledby="limitations-title" className="scroll-mt-6">
      <details className="card group p-5 sm:p-8">
        <summary className="flex items-center justify-between gap-4">
          <span>
            <span className="eyebrow block">Methodology &amp; honesty</span>
            <span id="limitations-title" className="mt-2 block text-2xl font-light text-white sm:text-3xl">Prototype limitations</span>
          </span>
          <span className="shrink-0 rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-slate-200 group-open:hidden">Show</span>
          <span className="hidden shrink-0 rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-slate-200 group-open:inline">Hide</span>
        </summary>
        <ol className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2">
          {LIMITATIONS.map((text, i) => (
            <li key={text} className="card-soft flex gap-3 p-4 text-sm leading-relaxed text-slate-200">
              <span className="num shrink-0 text-cream/70">{String(i + 1).padStart(2, '0')}</span>
              <span>{text}</span>
            </li>
          ))}
        </ol>
        <div className="mt-4 rounded-2xl border border-white/5 bg-black/20 p-4 text-xs leading-relaxed text-mist">
          <p className="font-semibold text-slate-200">Data-leakage check</p>
          <p className="mt-1">
            Verification pairs each archived forecast, issued about 24 h (Day 1) or 48 h (Day 2) before its valid time, with the ERA5 value at that same valid time. No information from after the forecast was issued enters the forecast value. Live forecasts keep their own run (init) time, lead time and valid time, and are blended only at matching valid times.
          </p>
        </div>
      </details>
    </section>
  )
}
