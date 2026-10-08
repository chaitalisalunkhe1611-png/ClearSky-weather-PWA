export type TemperatureUnit = 'celsius' | 'fahrenheit'
export type WindUnit = 'kmh' | 'mph'

export function celsiusToFahrenheit(value: number): number {
  return (value * 9) / 5 + 32
}

export function kmhToMph(value: number): number {
  return value * 0.621371
}

export function formatTemperature(value: number | null | undefined, unit: TemperatureUnit): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const converted = unit === 'fahrenheit' ? celsiusToFahrenheit(value) : value
  return `${Math.round(converted)}°`
}

export function formatWindSpeed(value: number | null | undefined, unit: WindUnit): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const converted = unit === 'mph' ? kmhToMph(value) : value
  return `${Math.round(converted)} ${unit === 'mph' ? 'mph' : 'km/h'}`
}
