import { airQualitySchema, forecastSchema, type Forecast, type AirQuality, type WeatherLocation } from './api'
import type { TemperatureUnit, WindUnit } from './units'

export interface CachedWeather {
  forecast: Forecast
  airQuality: AirQuality | null
  savedAt: number
}

export interface Preferences {
  temperatureUnit: TemperatureUnit
  windUnit: WindUnit
  theme: 'system' | 'light' | 'dark'
}

const WEATHER_PREFIX = 'clearsky:weather:'
const SAVED_LOCATIONS_KEY = 'clearsky:saved-locations'
const ACTIVE_LOCATION_KEY = 'clearsky:active-location'
const PREFERENCES_KEY = 'clearsky:preferences'

function safeRead<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key)
    return value ? JSON.parse(value) as T : fallback
  } catch {
    return fallback
  }
}

function safeWrite(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage can be disabled or full. The app remains usable without persistence.
  }
}

export function weatherCacheKey(location: WeatherLocation): string {
  return `${WEATHER_PREFIX}${location.latitude.toFixed(3)}:${location.longitude.toFixed(3)}`
}

export function readWeatherCache(location: WeatherLocation): CachedWeather | null {
  const value = safeRead<Partial<CachedWeather> | null>(weatherCacheKey(location), null)
  const forecast = forecastSchema.safeParse(value?.forecast)
  if (!value || !forecast.success || !Number.isFinite(value.savedAt)) return null
  const airQuality = value.airQuality ? airQualitySchema.safeParse(value.airQuality) : null
  return {
    forecast: forecast.data,
    airQuality: airQuality?.success ? airQuality.data : null,
    savedAt: value.savedAt as number,
  }
}

export function writeWeatherCache(
  location: WeatherLocation,
  forecast: Forecast,
  airQuality: AirQuality | null,
  savedAt = Date.now(),
): void {
  safeWrite(weatherCacheKey(location), { forecast, airQuality, savedAt } satisfies CachedWeather)
}

export function readSavedLocations(): WeatherLocation[] {
  const items = safeRead<WeatherLocation[]>(SAVED_LOCATIONS_KEY, [])
  return Array.isArray(items) ? items.filter(isWeatherLocation) : []
}

export function writeSavedLocations(locations: WeatherLocation[]): void {
  safeWrite(SAVED_LOCATIONS_KEY, locations)
}

export function readActiveLocation(): WeatherLocation | null {
  const value = safeRead<WeatherLocation | null>(ACTIVE_LOCATION_KEY, null)
  return isWeatherLocation(value) ? value : null
}

export function writeActiveLocation(location: WeatherLocation): void {
  safeWrite(ACTIVE_LOCATION_KEY, location)
}

export function readPreferences(): Preferences {
  const value = safeRead<Partial<Preferences>>(PREFERENCES_KEY, {})
  return {
    temperatureUnit: value.temperatureUnit === 'fahrenheit' ? 'fahrenheit' : 'celsius',
    windUnit: value.windUnit === 'mph' ? 'mph' : 'kmh',
    theme: value.theme === 'dark' || value.theme === 'light' ? value.theme : 'system',
  }
}

export function writePreferences(preferences: Preferences): void {
  safeWrite(PREFERENCES_KEY, preferences)
}

export function isWeatherLocation(value: unknown): value is WeatherLocation {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<WeatherLocation>
  return typeof item.name === 'string'
    && Number.isFinite(item.latitude) && typeof item.latitude === 'number'
    && Number.isFinite(item.longitude) && typeof item.longitude === 'number'
    && item.latitude >= -90 && item.latitude <= 90
    && item.longitude >= -180 && item.longitude <= 180
}
