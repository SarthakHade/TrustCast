import { describe, expect, it } from 'vitest'
import { highRiskAlert, riskHeadline } from './lib'
import type { RiskIndicator } from './types'

// TEST FIXTURES: minimal risk indicators shaped like /api/risks output.
function indicator(risk_type: string, level: RiskIndicator['level'], peak = '2026-10-06T00:00:00Z'): RiskIndicator {
  return {
    risk_type, title: risk_type, variable: 'temperature', unit: '°C', status: 'ok', reason: null, direction: 'below',
    thresholds: { ELEVATED: 10, HIGH: 4 }, aggregation: 'hourly', basis: '', level, peak_time: peak, window_start: null,
    accumulation_hours: null, forecast_value: 1, lower: null, upper: null, range_source: null, key_threshold: 4,
    range_position: null, threshold_crossing: false, models_exceeding: 3, models_total: 4, model_consensus: '3/4',
    messages: [], timeline: [],
  }
}
const place = { latitude: 32.79, longitude: 78.99 }

describe('high-risk alert', () => {
  it('appears only for HIGH levels from the risk engine', () => {
    const normal = highRiskAlert({ risks: [indicator('HEAT', 'NORMAL'), indicator('COLD', 'ELEVATED')] }, place, false, [])
    expect(normal.show).toBe(false)
    const high = highRiskAlert({ risks: [indicator('COLD', 'HIGH'), indicator('HEAT', 'NORMAL')] }, place, false, [])
    expect(high.show).toBe(true)
    expect(high.risks.map((r) => r.risk_type)).toEqual(['COLD'])
  })

  it('waits for the risk result and never invents one', () => {
    expect(highRiskAlert(null, place, false, []).show).toBe(false)
    expect(highRiskAlert({ risks: [indicator('COLD', 'HIGH')] }, place, true, []).show).toBe(false)
    expect(highRiskAlert({ risks: [indicator('COLD', 'HIGH')] }, null, false, []).show).toBe(false)
  })

  it('stays dismissed across re-renders of the same result but returns for a new hazard', () => {
    const risks = { risks: [indicator('COLD', 'HIGH')] }
    const first = highRiskAlert(risks, place, false, [])
    const again = highRiskAlert({ risks: [indicator('COLD', 'HIGH')] }, place, false, [first.key])
    expect(again.key).toBe(first.key)
    expect(again.show).toBe(false)
    const changed = highRiskAlert({ risks: [indicator('COLD', 'HIGH', '2026-10-07T00:00:00Z')] }, place, false, [first.key])
    expect(changed.show).toBe(true)
  })

  it('uses plain risk wording', () => {
    expect(riskHeadline(indicator('COLD', 'HIGH'))).toBe('High cold risk')
    expect(riskHeadline(indicator('HEAT', 'NORMAL'))).toBe('No significant heat risk')
  })
})
