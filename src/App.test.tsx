import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { makeForecast } from './test/forecastFixture'

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('ClearSky search to forecast flow', () => {
  it('searches a city with the keyboard and renders its weather', async () => {
    const forecast = makeForecast()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = new URL(input.toString())
      if (url.hostname === 'geocoding-api.open-meteo.com') {
        return Promise.resolve(jsonResponse({
          results: [{
            name: 'Portland', latitude: 45.5152, longitude: -122.6784,
            admin1: 'Oregon', country: 'United States', country_code: 'US', timezone: 'America/Los_Angeles',
          }],
        }))
      }
      if (url.hostname === 'air-quality-api.open-meteo.com') {
        return Promise.resolve(jsonResponse({ current: { time: '2026-10-07T08:00', us_aqi: 34 } }))
      }
      if (url.hostname === 'api.open-meteo.com') return Promise.resolve(jsonResponse(forecast))
      return Promise.reject(new Error(`Unexpected request to ${url.hostname}`))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const search = screen.getByRole('combobox', { name: 'Search for a city' })
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(search).toHaveFocus()
    fireEvent.change(search, { target: { value: 'Portland' } })
    const option = await screen.findByRole('option', { name: /Portland.*Oregon.*United States/ })
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    expect(search).toHaveAttribute('aria-activedescendant')
    fireEvent.keyDown(search, { key: 'Enter' })

    await screen.findByRole('heading', { name: 'Portland' })
    expect(screen.getByText('Oregon · United States')).toBeInTheDocument()
    expect(screen.getByLabelText('Current temperature 20°C')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI daily briefing' })).toBeInTheDocument()
    expect(option).toBeDefined()
  })
})
