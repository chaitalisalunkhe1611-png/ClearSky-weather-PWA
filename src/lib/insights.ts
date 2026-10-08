import type { Forecast } from './api'
import type { TemperatureUnit, WindUnit } from './units'
import { hourLabel } from './time'
import { formatTemperature, formatWindSpeed } from './units'

export type InsightFlag = 'umbrella' | 'sunscreen' | 'wind' | 'frost' | 'day-change' | 'outdoor'
export type InsightRule = 'precipitation' | 'uv' | 'wind' | 'frost' | 'temperature-change' | 'outdoor-window'

export interface BriefingInsight {
  rule: InsightRule
  flag: InsightFlag
  title: string
  sentence: string
}

export interface DailyBriefing {
  message: string
  insights: BriefingInsight[]
  flags: InsightFlag[]
}

export interface BriefingOptions {
  temperatureUnit?: TemperatureUnit
  windUnit?: WindUnit
}

const asNumber = (value: number | null | undefined): number | null =>
  value !== null && value !== undefined && Number.isFinite(value) ? value : null

function getTodayIndex(forecast: Forecast): number {
  const date = forecast.current.time.slice(0, 10)
  const sameDay = forecast.daily.time.indexOf(date)
  if (sameDay >= 0) return sameDay
  const nextDay = forecast.daily.time.findIndex((candidate) => candidate >= date)
  return nextDay >= 0 ? nextDay : 0
}

function getStartHourIndex(forecast: Forecast): number {
  const current = forecast.current.time
  const index = forecast.hourly.time.findIndex((time) => time >= current)
  return index >= 0 ? index : 0
}

function temperatureDelta(value: number, unit: TemperatureUnit): string {
  const converted = unit === 'fahrenheit' ? value * 9 / 5 : value
  return `${Math.round(converted)}°`
}

function dayRangeSentence(forecast: Forecast, unit: TemperatureUnit): string {
  const today = getTodayIndex(forecast)
  const low = asNumber(forecast.daily.temperature_2m_min[today])
  const high = asNumber(forecast.daily.temperature_2m_max[today])
  if (low !== null && high !== null) {
    return `Today’s temperatures range from ${formatTemperature(low, unit)} to ${formatTemperature(high, unit)}.`
  }
  return 'A quick look at the hourly forecast can help you plan the day.'
}

function bestOutdoorInsight(forecast: Forecast, unit: TemperatureUnit, todayIndex: number): BriefingInsight {
  const start = getStartHourIndex(forecast)
  const today = forecast.daily.time[todayIndex]
  const upcomingToday = forecast.hourly.time
    .map((time, index) => ({
      time,
      temperature: asNumber(forecast.hourly.temperature_2m[index]),
      probability: asNumber(forecast.hourly.precipitation_probability[index]),
      index,
    }))
    .filter((hour) => hour.index >= start && hour.time.slice(0, 10) === today && hour.temperature !== null)

  const candidates = upcomingToday.length > 0
    ? upcomingToday
    : forecast.hourly.time.map((time, index) => ({
      time,
      temperature: asNumber(forecast.hourly.temperature_2m[index]),
      probability: asNumber(forecast.hourly.precipitation_probability[index]),
      index,
    })).filter((hour) => hour.index >= start && hour.temperature !== null).slice(0, 12)

  const best = candidates.reduce<(typeof candidates)[number] | null>((current, hour) => {
    const probability = hour.probability ?? 0
    const mildness = Math.abs((hour.temperature ?? 20) - 20)
    const score = probability + mildness * 1.1
    if (!current) return hour
    const currentScore = (current.probability ?? 0) + Math.abs((current.temperature ?? 20) - 20) * 1.1
    return score < currentScore ? hour : current
  }, null)

  if (!best || best.temperature === null) {
    return {
      rule: 'outdoor-window', flag: 'outdoor', title: 'A little fresh air',
      sentence: 'The best outdoor window is still ahead—check the hourly outlook before you head out.',
    }
  }
  const chance = best.probability === null ? 'a low chance of rain' : `${Math.round(best.probability)}% chance of rain`
  return {
    rule: 'outdoor-window', flag: 'outdoor', title: 'Best outdoor window',
    sentence: `The gentlest outdoor window looks like ${hourLabel(best.time)}, around ${formatTemperature(best.temperature, unit)}, with ${chance}.`,
  }
}

/**
 * Turns an Open-Meteo forecast into a short, deterministic daily briefing.
 * The input remains in canonical Celsius and km/h; only presentation units vary.
 */
export function buildDailyBriefing(forecast: Forecast, options: BriefingOptions = {}): DailyBriefing {
  const unit = options.temperatureUnit ?? 'celsius'
  const windUnit = options.windUnit ?? 'kmh'
  const todayIndex = getTodayIndex(forecast)
  const today = forecast.daily.time[todayIndex]
  const startIndex = getStartHourIndex(forecast)
  const windowHours = forecast.hourly.time
    .map((time, index) => ({
      time,
      index,
      probability: asNumber(forecast.hourly.precipitation_probability[index]),
      temperature: asNumber(forecast.hourly.temperature_2m[index]),
      wind: asNumber(forecast.hourly.wind_speed_10m[index]),
      uv: asNumber(forecast.hourly.uv_index[index]),
    }))
    .filter((hour) => hour.index >= startIndex)
    .slice(0, 13)

  const detected: BriefingInsight[] = []

  // Priority 1 — precipitation in the next twelve hours.
  const wetIndex = windowHours.findIndex((hour) => (hour.probability ?? 0) > 50)
  if (wetIndex >= 0) {
    const wet = windowHours[wetIndex]
    const dryBefore = windowHours.slice(0, wetIndex).filter((hour) => (hour.probability ?? 0) <= 50)
    const dryNote = dryBefore.length > 0 ? `enjoy dry skies through ${hourLabel(dryBefore[dryBefore.length - 1].time)}, then ` : ''
    detected.push({
      rule: 'precipitation', flag: 'umbrella', title: 'Umbrella weather',
      sentence: `Rain is likely to begin around ${hourLabel(wet.time)} (${Math.round(wet.probability ?? 0)}%); ${dryNote}keep an umbrella handy.`,
    })
  }

  // Priority 2 — UV at or above six during the remaining daylight hours today.
  const sunrise = forecast.daily.sunrise[todayIndex]
  const sunset = forecast.daily.sunset[todayIndex]
  const brightHours = forecast.hourly.time
    .map((time, index) => ({ time, uv: asNumber(forecast.hourly.uv_index[index]), index }))
    .filter((hour) => hour.index >= startIndex && hour.time.slice(0, 10) === today && hour.uv !== null && hour.uv >= 6)
    .filter((hour) => !sunrise || !sunset || (hour.time >= sunrise && hour.time <= sunset))
  if (brightHours.length > 0) {
    const peak = Math.max(...brightHours.map((hour) => hour.uv ?? 0))
    const peakHours = brightHours.filter((hour) => hour.uv === peak)
    const first = hourLabel(peakHours[0].time)
    const last = hourLabel(peakHours[peakHours.length - 1].time)
    const period = first === last ? `around ${first}` : `between ${first} and ${last}`
    detected.push({
      rule: 'uv', flag: 'sunscreen', title: 'Sunscreen recommended',
      sentence: `UV peaks at ${Math.round(peak)} ${period}, so sunscreen is a good idea if you’ll be outside.`,
    })
  }

  // Priority 3 — strong breezes, including the live observation.
  const windObservations = [
    { time: forecast.current.time, speed: forecast.current.wind_speed_10m },
    ...windowHours.map((hour) => ({ time: hour.time, speed: hour.wind ?? 0 })),
  ]
  const strongestWind = windObservations.reduce((strongest, observation) =>
    observation.speed > strongest.speed ? observation : strongest,
  { time: forecast.current.time, speed: forecast.current.wind_speed_10m })
  if (strongestWind.speed > 30) {
    detected.push({
      rule: 'wind', flag: 'wind', title: 'Breezy conditions',
      sentence: `Wind may reach ${formatWindSpeed(strongestWind.speed, windUnit)} around ${hourLabel(strongestWind.time)}; secure anything loose outdoors.`,
    })
  }

  // Priority 4 — a freezing low on the local calendar day.
  const low = asNumber(forecast.daily.temperature_2m_min[todayIndex])
  if (low !== null && low <= 0) {
    detected.push({
      rule: 'frost', flag: 'frost', title: 'Frost watch',
      sentence: `Tonight’s low is near ${formatTemperature(low, unit)}; cover delicate plants before bed.`,
    })
  }

  // Priority 5 — a marked change from yesterday's high.
  const yesterdayHigh = asNumber(forecast.daily.temperature_2m_max[todayIndex - 1])
  const todayHigh = asNumber(forecast.daily.temperature_2m_max[todayIndex])
  if (yesterdayHigh !== null && todayHigh !== null && Math.abs(todayHigh - yesterdayHigh) >= 6) {
    const difference = Math.abs(todayHigh - yesterdayHigh)
    const direction = todayHigh > yesterdayHigh ? 'warmer' : 'cooler'
    detected.push({
      rule: 'temperature-change', flag: 'day-change', title: 'A different kind of day',
      sentence: `Today’s high is ${temperatureDelta(difference, unit)} ${direction} than yesterday, so it may feel noticeably different.`,
    })
  }

  if (detected.length === 0) {
    const outdoor = bestOutdoorInsight(forecast, unit, todayIndex)
    return {
      message: `${outdoor.sentence} ${dayRangeSentence(forecast, unit)}`,
      insights: [outdoor],
      flags: [outdoor.flag],
    }
  }

  const insights = detected.slice(0, 3)
  const sentences = insights.map((insight) => insight.sentence)
  if (sentences.length < 2) sentences.push(dayRangeSentence(forecast, unit))
  return {
    message: sentences.slice(0, 4).join(' '),
    insights,
    flags: insights.map((insight) => insight.flag),
  }
}
