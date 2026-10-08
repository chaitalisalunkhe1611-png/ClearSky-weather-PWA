import { z } from 'zod'

const nullableNumber = z.number().nullable()

const currentSchema = z.object({
  time: z.string(),
  interval: z.number().optional(),
  temperature_2m: z.number(),
  apparent_temperature: z.number(),
  relative_humidity_2m: z.number(),
  precipitation: z.number(),
  weather_code: z.number().int(),
  wind_speed_10m: z.number(),
  uv_index: z.number(),
  is_day: z.number().optional(),
}).passthrough()

const hourlySchema = z.object({
  time: z.array(z.string()),
  temperature_2m: z.array(nullableNumber),
  precipitation_probability: z.array(nullableNumber),
  precipitation: z.array(nullableNumber),
  weather_code: z.array(z.number().int().nullable()),
  wind_speed_10m: z.array(nullableNumber),
  uv_index: z.array(nullableNumber),
}).passthrough()

const dailySchema = z.object({
  time: z.array(z.string()),
  temperature_2m_max: z.array(nullableNumber),
  temperature_2m_min: z.array(nullableNumber),
  precipitation_probability_max: z.array(nullableNumber),
  weather_code: z.array(z.number().int().nullable()),
  sunrise: z.array(z.string().nullable()),
  sunset: z.array(z.string().nullable()),
}).passthrough()

export const forecastSchema = z.object({
  latitude: z.number(),
  longitude: z.number(),
  timezone: z.string(),
  timezone_abbreviation: z.string().optional(),
  utc_offset_seconds: z.number(),
  current: currentSchema,
  hourly: hourlySchema,
  daily: dailySchema,
}).passthrough().superRefine((forecast, context) => {
  const series = Object.values(forecast.hourly)
  const hourlyLength = forecast.hourly.time.length
  if (series.some((values) => Array.isArray(values) && values.length !== hourlyLength)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'Hourly forecast series have inconsistent lengths.' })
  }
  const dailySeries = Object.values(forecast.daily)
  const dailyLength = forecast.daily.time.length
  if (dailySeries.some((values) => Array.isArray(values) && values.length !== dailyLength)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: 'Daily forecast series have inconsistent lengths.' })
  }
})

export type Forecast = z.infer<typeof forecastSchema>

const geocodingResultSchema = z.object({
  id: z.number().optional(),
  name: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  elevation: z.number().optional(),
  feature_code: z.string().optional(),
  country_code: z.string().optional(),
  admin1: z.string().optional(),
  admin2: z.string().optional(),
  country: z.string().optional(),
  timezone: z.string().optional(),
}).passthrough()

export const geocodingSchema = z.object({
  results: z.array(geocodingResultSchema).optional(),
}).passthrough()

export type CityResult = z.infer<typeof geocodingResultSchema>

export const airQualitySchema = z.object({
  current: z.object({
    time: z.string(),
    interval: z.number().optional(),
    us_aqi: z.number().nullable(),
  }).passthrough(),
}).passthrough()

export type AirQuality = z.infer<typeof airQualitySchema>

export interface WeatherLocation {
  name: string
  latitude: number
  longitude: number
  admin1?: string
  country?: string
  countryCode?: string
  timezone?: string
}

async function fetchJson<T>(url: URL, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new Error(`Weather service responded with ${response.status}.`)
  }
  const payload: unknown = await response.json()
  const result = schema.safeParse(payload)
  if (!result.success) {
    throw new Error('The weather service returned data in an unexpected format.')
  }
  return result.data
}

export async function fetchForecast(location: WeatherLocation, signal?: AbortSignal): Promise<Forecast> {
  const url = new URL('https://api.open-meteo.com/v1/forecast')
  url.search = new URLSearchParams({
    latitude: String(location.latitude),
    longitude: String(location.longitude),
    current: 'temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,uv_index',
    hourly: 'temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m,uv_index',
    daily: 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,sunrise,sunset',
    forecast_days: '7',
    past_days: '1',
    timezone: 'auto',
    temperature_unit: 'celsius',
    wind_speed_unit: 'kmh',
  }).toString()
  return fetchJson(url, forecastSchema, signal)
}

export async function fetchAirQuality(location: WeatherLocation, signal?: AbortSignal): Promise<AirQuality> {
  const url = new URL('https://air-quality-api.open-meteo.com/v1/air-quality')
  url.search = new URLSearchParams({
    latitude: String(location.latitude),
    longitude: String(location.longitude),
    current: 'us_aqi',
    timezone: 'auto',
  }).toString()
  return fetchJson(url, airQualitySchema, signal)
}

export async function searchCities(query: string, signal?: AbortSignal): Promise<WeatherLocation[]> {
  const url = new URL('https://geocoding-api.open-meteo.com/v1/search')
  url.search = new URLSearchParams({ name: query, count: '5', language: 'en', format: 'json' }).toString()
  const result = await fetchJson(url, geocodingSchema, signal)
  return (result.results ?? []).map((city) => ({
    name: city.name,
    latitude: city.latitude,
    longitude: city.longitude,
    admin1: city.admin1,
    country: city.country,
    countryCode: city.country_code,
    timezone: city.timezone,
  }))
}
