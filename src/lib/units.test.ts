import { describe, expect, it } from 'vitest'
import { celsiusToFahrenheit, formatTemperature, formatWindSpeed, kmhToMph } from './units'

describe('unit conversions', () => {
  it('converts Celsius to Fahrenheit', () => {
    expect(celsiusToFahrenheit(0)).toBe(32)
    expect(celsiusToFahrenheit(20)).toBe(68)
    expect(formatTemperature(-4, 'fahrenheit')).toBe('25°')
  })

  it('converts kilometres per hour to miles per hour', () => {
    expect(kmhToMph(100)).toBeCloseTo(62.1371)
    expect(formatWindSpeed(16, 'mph')).toBe('10 mph')
    expect(formatWindSpeed(16, 'kmh')).toBe('16 km/h')
  })

  it('formats missing values accessibly', () => {
    expect(formatTemperature(null, 'celsius')).toBe('—')
    expect(formatWindSpeed(undefined, 'mph')).toBe('—')
  })
})
