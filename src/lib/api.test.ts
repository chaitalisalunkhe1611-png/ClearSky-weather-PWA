import { describe, expect, it } from 'vitest'
import { forecastSchema } from './api'
import { makeForecast } from '../test/forecastFixture'

describe('Open-Meteo data validation', () => {
  it('accepts a well-formed forecast payload', () => {
    expect(forecastSchema.safeParse(makeForecast()).success).toBe(true)
  })

  it('rejects hourly series whose lengths do not match the time axis', () => {
    const payload = makeForecast()
    payload.hourly.temperature_2m.pop()
    expect(forecastSchema.safeParse(payload).success).toBe(false)
  })
})
