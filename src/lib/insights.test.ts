import { describe, expect, it } from 'vitest'
import { buildDailyBriefing } from './insights'
import { makeForecast } from '../test/forecastFixture'

const forecastHour = '2026-10-07T'

function setHourly(
  field: 'precipitation_probability' | 'uv_index' | 'wind_speed_10m',
  hour: string,
  value: number,
) {
  const forecast = makeForecast()
  const index = forecast.hourly.time.indexOf(`${forecastHour}${hour}:00`)
  if (index >= 0) forecast.hourly[field][index] = value
  return forecast
}

describe('daily briefing insight rules', () => {
  it('prioritizes rain, names its start hour and the dry window before it', () => {
    const forecast = setHourly('precipitation_probability', '14', 78)
    const briefing = buildDailyBriefing(forecast)
    expect(briefing.insights[0].rule).toBe('precipitation')
    expect(briefing.flags).toContain('umbrella')
    expect(briefing.message).toContain('2 PM')
    expect(briefing.message).toContain('dry skies through 1 PM')
  })

  it('flags high daytime UV and reports its peak hours', () => {
    const forecast = setHourly('uv_index', '12', 7)
    forecast.hourly.uv_index[forecast.hourly.time.indexOf(`${forecastHour}13:00`)] = 8
    forecast.hourly.uv_index[forecast.hourly.time.indexOf(`${forecastHour}14:00`)] = 8
    const briefing = buildDailyBriefing(forecast)
    expect(briefing.insights[0].rule).toBe('uv')
    expect(briefing.flags).toContain('sunscreen')
    expect(briefing.message).toContain('UV peaks at 8')
    expect(briefing.message).toContain('between 1 PM and 2 PM')
  })

  it('warns when observed or forecast wind exceeds 30 km/h', () => {
    const forecast = setHourly('wind_speed_10m', '15', 38)
    const briefing = buildDailyBriefing(forecast)
    expect(briefing.insights.some((insight) => insight.rule === 'wind')).toBe(true)
    expect(briefing.message).toContain('38 km/h')
    expect(briefing.flags).toContain('wind')
    expect(buildDailyBriefing(forecast, { windUnit: 'mph' }).message).toContain('24 mph')
  })

  it('flags a freezing low tonight and converts it for Fahrenheit preferences', () => {
    const forecast = makeForecast()
    forecast.daily.temperature_2m_min[1] = -2
    const celsius = buildDailyBriefing(forecast)
    const fahrenheit = buildDailyBriefing(forecast, { temperatureUnit: 'fahrenheit' })
    expect(celsius.insights[0].rule).toBe('frost')
    expect(celsius.message).toContain('near -2°')
    expect(fahrenheit.message).toContain('near 28°')
    expect(celsius.flags).toContain('frost')
  })

  it('notes a six-degree or greater change from yesterday', () => {
    const forecast = makeForecast()
    forecast.daily.temperature_2m_max[0] = 18
    forecast.daily.temperature_2m_max[1] = 25
    const briefing = buildDailyBriefing(forecast)
    expect(briefing.insights[0].rule).toBe('temperature-change')
    expect(briefing.message).toContain('7° warmer than yesterday')
    expect(buildDailyBriefing(forecast, { temperatureUnit: 'fahrenheit' }).message).toContain('13° warmer than yesterday')
  })

  it('chooses an outdoor window when no priority warning is active', () => {
    const forecast = makeForecast()
    forecast.hourly.temperature_2m[forecast.hourly.time.indexOf(`${forecastHour}10:00`)] = 20
    const briefing = buildDailyBriefing(forecast)
    expect(briefing.insights).toHaveLength(1)
    expect(briefing.insights[0].rule).toBe('outdoor-window')
    expect(briefing.message).toContain('gentlest outdoor window')
    expect(briefing.message).toContain('Today’s temperatures range')
  })

  it('composes no more than three prioritized alerts into a friendly 2–4 sentence brief', () => {
    const forecast = setHourly('precipitation_probability', '14', 75)
    forecast.hourly.uv_index[forecast.hourly.time.indexOf(`${forecastHour}12:00`)] = 8
    forecast.hourly.wind_speed_10m[forecast.hourly.time.indexOf(`${forecastHour}15:00`)] = 36
    forecast.daily.temperature_2m_min[1] = -4
    forecast.daily.temperature_2m_max[0] = 16
    forecast.daily.temperature_2m_max[1] = 25
    const briefing = buildDailyBriefing(forecast)
    const sentenceCount = briefing.message.split(/[.!?](?:\s|$)/).filter(Boolean).length
    expect(briefing.insights.map((insight) => insight.rule)).toEqual(['precipitation', 'uv', 'wind'])
    expect(briefing.insights).toHaveLength(3)
    expect(sentenceCount).toBeGreaterThanOrEqual(2)
    expect(sentenceCount).toBeLessThanOrEqual(4)
  })
})
