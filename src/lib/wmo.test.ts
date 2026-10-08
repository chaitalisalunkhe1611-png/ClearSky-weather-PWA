import { describe, expect, it } from 'vitest'
import { describeWeather, weatherMood } from './wmo'

describe('WMO weather code mapping', () => {
  it('maps clear and cloud conditions to readable descriptions', () => {
    expect(describeWeather(0)).toEqual({ label: 'Clear sky', kind: 'sun' })
    expect(describeWeather(2)).toEqual({ label: 'Partly cloudy', kind: 'partly-cloudy' })
    expect(describeWeather(3).label).toBe('Overcast')
  })

  it('covers precipitation, fog, snow, and thunderstorms', () => {
    expect(describeWeather(45).kind).toBe('fog')
    expect(describeWeather(55).label).toBe('Dense drizzle')
    expect(describeWeather(63).kind).toBe('rain')
    expect(describeWeather(75).label).toBe('Heavy snow')
    expect(describeWeather(96).label).toBe('Thunderstorm with hail')
    expect(describeWeather(97).kind).toBe('storm')
  })

  it('handles missing or unknown codes gracefully', () => {
    expect(describeWeather(null)).toEqual({ label: 'Conditions unavailable', kind: 'cloud' })
    expect(describeWeather(77)).toEqual({ label: 'Snow grains', kind: 'snow' })
    expect(describeWeather(12)).toEqual({ label: 'Conditions unavailable', kind: 'cloud' })
    expect(weatherMood(61)).toBe('rainy')
    expect(weatherMood(71)).toBe('snowy')
  })
})
