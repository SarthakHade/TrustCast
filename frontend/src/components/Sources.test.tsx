import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { Model, ProviderForecast } from '../types'
import { Sources } from './Sources'

// TEST FIXTURES: four live models with one forecast record each.
const NAMES = ['ECMWF IFS', 'NOAA GFS', 'ECMWF AIFS', 'DWD ICON']
const models: Model[] = NAMES.map((name) => ({ name, model_type: 'Physics NWP', provider: name.split(' ')[0], status: 'live' }))
const results: ProviderForecast[] = NAMES.map((name, i) => ({
  model: name, model_type: 'Physics NWP', provider: name.split(' ')[0], status: 'live', init_time: '2026-10-05T00:00:00Z',
  variables: ['temperature', 'precipitation', 'wind_speed', 'humidity'],
  forecast: [{ init_time: '2026-10-05T00:00:00Z', valid_time: '2099-01-01T00:00:00Z', lead_time_hours: 6, temperature: 28 + i, precipitation: 0, wind_speed: 10, humidity: 70 }],
}))

function renderSources() {
  render(<Sources models={models} results={results} loading={false} error="" openedAt={0} contributors={NAMES} exclusions={{}} />)
  return screen.getAllByRole('article')
}

const expanded = (card: HTMLElement) => within(card).getByRole('button', { name: /details/i }).getAttribute('aria-expanded')

describe('model Details accordion', () => {
  afterEach(cleanup)

  it('opens only the clicked model', () => {
    const cards = renderSources()
    fireEvent.click(within(cards[0]).getByRole('button', { name: 'Details' }))
    expect(cards.map(expanded)).toEqual(['true', 'false', 'false', 'false'])
    expect(within(cards[0]).getByText('Forecast source')).toBeTruthy()
    expect(within(cards[1]).queryByText('Forecast source')).toBeNull()
  })

  it('opening another model closes the previous one, and clicking again closes it', () => {
    const cards = renderSources()
    fireEvent.click(within(cards[0]).getByRole('button', { name: 'Details' }))
    fireEvent.click(within(cards[1]).getByRole('button', { name: 'Details' }))
    expect(cards.map(expanded)).toEqual(['false', 'true', 'false', 'false'])
    fireEvent.click(within(cards[1]).getByRole('button', { name: 'Hide details' }))
    expect(cards.map(expanded)).toEqual(['false', 'false', 'false', 'false'])
  })

  it('shows only the four contributing models, no extra source rows', () => {
    const cards = renderSources()
    expect(cards).toHaveLength(4)
    expect(screen.queryByText(/additional sources/i)).toBeNull()
    expect(screen.queryByText(/NCUM/)).toBeNull()
  })
})
