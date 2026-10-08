import { forecastSchema } from '../lib/api'

export function makeForecast() {
  const firstDay = new Date(Date.UTC(2026, 9, 6))
  const dates = Array.from({ length: 8 }, (_, index) => {
    const date = new Date(firstDay)
    date.setUTCDate(date.getUTCDate() + index)
    return date.toISOString().slice(0, 10)
  })
  const times = Array.from({ length: 8 * 24 }, (_, index) => {
    const date = new Date(firstDay)
    date.setUTCHours(index, 0, 0, 0)
    return date.toISOString().slice(0, 16)
  })

  return forecastSchema.parse({
    latitude: 40.7128,
    longitude: -74.006,
    timezone: 'America/New_York',
    timezone_abbreviation: 'EDT',
    utc_offset_seconds: -14400,
    current: {
      time: '2026-10-07T08:00',
      interval: 900,
      temperature_2m: 20,
      apparent_temperature: 19,
      relative_humidity_2m: 52,
      precipitation: 0,
      weather_code: 1,
      wind_speed_10m: 12,
      uv_index: 3,
      is_day: 1,
    },
    hourly: {
      time: times,
      temperature_2m: times.map(() => 20),
      precipitation_probability: times.map(() => 0),
      precipitation: times.map(() => 0),
      weather_code: times.map(() => 1),
      wind_speed_10m: times.map(() => 12),
      uv_index: times.map((time) => {
        const hour = Number(time.slice(11, 13))
        return hour >= 11 && hour <= 15 ? 5 : 2
      }),
    },
    daily: {
      time: dates,
      temperature_2m_max: [24, 25, 23, 21, 22, 24, 26, 24],
      temperature_2m_min: [12, 12, 11, 10, 9, 11, 12, 13],
      precipitation_probability_max: dates.map(() => 10),
      weather_code: dates.map(() => 1),
      sunrise: dates.map((date) => `${date}T06:30`),
      sunset: dates.map((date) => `${date}T18:30`),
    },
  })
}
