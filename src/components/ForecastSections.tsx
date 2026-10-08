import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CloudRain,
  Droplets,
  Heart,
  Moon,
  ShieldCheck,
  Snowflake,
  Sparkles,
  Sunrise,
  Sunset,
  Umbrella,
  Wind,
  type LucideIcon,
} from 'lucide-react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { AirQuality, Forecast, WeatherLocation } from '../lib/api'
import type { InsightFlag } from '../lib/insights'
import { buildDailyBriefing } from '../lib/insights'
import type { TemperatureUnit, WindUnit } from '../lib/units'
import { formatTemperature, formatWindSpeed } from '../lib/units'
import { getAqiLevel } from '../lib/aqi'
import { hourLabel, weekdayLabel } from '../lib/time'
import { describeWeather } from '../lib/wmo'
import { WeatherIcon } from './WeatherIcon'

interface CurrentConditionsProps {
  forecast: Forecast
  airQuality: AirQuality | null
  location: WeatherLocation
  temperatureUnit: TemperatureUnit
  windUnit: WindUnit
  isSaved: boolean
  onToggleSaved: () => void
  night: boolean
}

function Stat({ icon: Icon, label, value, detail }: { icon: LucideIcon; label: string; value: string; detail?: string }) {
  return (
    <div className="condition-stat">
      <span className="stat-icon"><Icon size={17} aria-hidden="true" /></span>
      <div className="stat-copy">
        <span className="stat-label">{label}</span>
        <strong>{value}</strong>
        {detail ? <span className="stat-detail">{detail}</span> : null}
      </div>
    </div>
  )
}

function formatClock(value: string | null | undefined): string {
  return value ? hourLabel(value) : '—'
}

export function CurrentConditions({
  forecast, airQuality, location, temperatureUnit, windUnit, isSaved, onToggleSaved, night,
}: CurrentConditionsProps) {
  const { current, daily } = forecast
  const todayDate = current.time.slice(0, 10)
  const exactIndex = daily.time.indexOf(todayDate)
  const todayIndex = exactIndex >= 0 ? exactIndex : Math.max(0, daily.time.findIndex((date) => date >= todayDate))
  const description = describeWeather(current.weather_code)
  const aqi = airQuality?.current.us_aqi ?? null
  const aqiLevel = getAqiLevel(aqi)

  return (
    <section className="current-card glass-card" aria-labelledby="current-title">
      <div className="current-card-topline">
        <span className="section-kicker"><span className="live-dot" /> RIGHT NOW</span>
        <button
          type="button"
          className={`save-place-button ${isSaved ? 'is-saved' : ''}`}
          onClick={onToggleSaved}
          aria-label={isSaved ? `Remove ${location.name} from saved places` : `Save ${location.name}`}
          aria-pressed={isSaved}
        >
          <Heart size={16} aria-hidden="true" fill={isSaved ? 'currentColor' : 'none'} />
          <span>{isSaved ? 'Saved' : 'Save place'}</span>
        </button>
      </div>

      <div className="current-main">
        <div className="current-identity">
          <h2 id="current-title">{location.name}</h2>
          <p className="location-subtitle">{[location.admin1, location.country].filter(Boolean).join(' · ') || 'Your current location'}</p>
          <p className="condition-description">{description.label}</p>
          <p className="feels-like">Feels like {formatTemperature(current.apparent_temperature, temperatureUnit)}</p>
        </div>
        <div className="temperature-display">
          <WeatherIcon code={current.weather_code} size={62} className="current-weather-icon" night={night} />
          <span className="current-temperature" aria-label={`Current temperature ${formatTemperature(current.temperature_2m, temperatureUnit)}${temperatureUnit === 'fahrenheit' ? 'F' : 'C'}`}>
            {formatTemperature(current.temperature_2m, temperatureUnit)}
          </span>
          <span className="current-unit" aria-hidden="true">{temperatureUnit === 'fahrenheit' ? 'F' : 'C'}</span>
        </div>
      </div>

      <div className="condition-stats" aria-label="Current weather details">
        <Stat icon={Droplets} label="Humidity" value={`${Math.round(current.relative_humidity_2m)}%`} />
        <Stat icon={Wind} label="Wind" value={formatWindSpeed(current.wind_speed_10m, windUnit)} />
        <Stat icon={ShieldCheck} label="UV index" value={String(Math.round(current.uv_index))} detail={current.uv_index >= 6 ? 'High today' : 'Low to moderate'} />
        <div className="condition-stat aqi-stat" aria-label={`Air quality index ${aqi ?? 'unavailable'}, ${aqiLevel.detail}`}>
          <span className={`aqi-number ${aqiLevel.className}`}>{aqi === null ? '—' : Math.round(aqi)}</span>
          <div className="stat-copy">
            <span className="stat-label">US AQI</span>
            <strong className={`aqi-label ${aqiLevel.className}`}>{aqiLevel.label}</strong>
          </div>
        </div>
      </div>

      <div className="sun-times" aria-label="Sun times">
        <div className="sun-time-item">
          <span className="sun-time-icon sunrise-icon"><Sunrise size={18} aria-hidden="true" /></span>
          <span><small>Sunrise</small><strong>{formatClock(daily.sunrise[todayIndex])}</strong></span>
        </div>
        <div className="sun-path" aria-hidden="true"><span /></div>
        <div className="sun-time-item">
          <span className="sun-time-icon sunset-icon"><Sunset size={18} aria-hidden="true" /></span>
          <span><small>Sunset</small><strong>{formatClock(daily.sunset[todayIndex])}</strong></span>
        </div>
      </div>
    </section>
  )
}

const flagIcons: Record<InsightFlag, LucideIcon> = {
  umbrella: Umbrella,
  sunscreen: ShieldCheck,
  wind: Wind,
  frost: Snowflake,
  'day-change': ArrowUpDown,
  outdoor: Sparkles,
}

export function BriefingCard({ forecast, temperatureUnit, windUnit }: { forecast: Forecast; temperatureUnit: TemperatureUnit; windUnit: WindUnit }) {
  const briefing = buildDailyBriefing(forecast, { temperatureUnit, windUnit })
  const topInsight = briefing.insights[0]
  const HeaderIcon = topInsight ? flagIcons[topInsight.flag] : Sparkles
  return (
    <section className="briefing-card glass-card" aria-labelledby="briefing-title">
      <div className="briefing-heading">
        <span className="briefing-orb"><HeaderIcon size={19} aria-hidden="true" /></span>
        <div>
          <span className="section-kicker">CLEARSKY INSIGHTS</span>
          <h2 id="briefing-title">AI daily briefing</h2>
        </div>
        <span className="briefing-sparkle"><Sparkles size={16} aria-hidden="true" /></span>
      </div>
      <p className="briefing-message">{briefing.message}</p>
      <div className="briefing-tags" aria-label="Forecast notes">
        {briefing.insights.map((insight) => {
          const Icon = flagIcons[insight.flag]
          return <span className="briefing-tag" key={insight.rule}><Icon size={13} aria-hidden="true" />{insight.title}</span>
        })}
      </div>
      <p className="briefing-footnote">A clear-eyed take on the forecast. No AI servers, just weather data.</p>
    </section>
  )
}

interface HourlyDatum {
  time: string
  temperature: number | null
  probability: number | null
  precipitation: number | null
  weatherCode: number | null
}

function HourlyTooltip({ active, payload, temperatureUnit }: { active?: boolean; payload?: Array<{ payload: HourlyDatum }>; temperatureUnit: TemperatureUnit }) {
  if (!active || !payload?.[0]?.payload) return null
  const item = payload[0].payload
  const condition = describeWeather(item.weatherCode)
  return (
    <div className="chart-tooltip">
      <strong>{hourLabel(item.time)}</strong>
      <span>{condition.label}</span>
      <span><b>{formatTemperature(item.temperature, temperatureUnit)}</b> temperature</span>
      <span><b>{item.probability === null ? '—' : `${Math.round(item.probability)}%`}</b> rain chance</span>
    </div>
  )
}

export function HourlyForecast({ forecast, temperatureUnit }: { forecast: Forecast; temperatureUnit: TemperatureUnit }) {
  const { hourly, current } = forecast
  const currentIndex = Math.max(0, hourly.time.findIndex((time) => time >= current.time))
  const data: HourlyDatum[] = hourly.time.slice(currentIndex, currentIndex + 48).map((time, offset) => {
    const index = currentIndex + offset
    return {
      time,
      temperature: hourly.temperature_2m[index],
      probability: hourly.precipitation_probability[index],
      precipitation: hourly.precipitation[index],
      weatherCode: hourly.weather_code[index],
    }
  })

  return (
    <section className="forecast-card glass-card hourly-card" aria-labelledby="hourly-title">
      <div className="section-heading">
        <div>
          <span className="section-kicker">THE NEXT TWO DAYS</span>
          <h2 id="hourly-title">Hourly outlook</h2>
        </div>
        <div className="chart-legend" aria-label="Chart legend">
          <span><i className="legend-temp" /> Temperature</span>
          <span><i className="legend-rain" /> Rain chance</span>
        </div>
      </div>
      <div className="hourly-chart-scroll" role="group" aria-label="Scrollable 48-hour forecast chart">
        <p className="sr-only">A combined chart showing temperature and precipitation probability over the next {data.length} hours. Use the chart keyboard controls to explore each hour.</p>
        <div className="hourly-chart-inner">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart accessibilityLayer data={data} margin={{ top: 16, right: 10, bottom: 4, left: -15 }}>
              <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} />
              <XAxis
                dataKey="time"
                tickFormatter={(value: string) => hourLabel(value)}
                tick={{ fill: 'var(--chart-label)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                interval={3}
                minTickGap={14}
              />
              <YAxis
                yAxisId="temperature"
                tickFormatter={(value: number) => formatTemperature(value, temperatureUnit)}
                tick={{ fill: 'var(--chart-label)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={48}
                domain={['auto', 'auto']}
              />
              <YAxis yAxisId="probability" orientation="right" domain={[0, 100]} hide />
              <Tooltip content={<HourlyTooltip temperatureUnit={temperatureUnit} />} cursor={{ fill: 'var(--chart-hover)' }} />
              <Bar yAxisId="probability" dataKey="probability" fill="var(--chart-rain)" opacity={0.65} barSize={10} radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="temperature"
                dataKey="temperature"
                type="monotone"
                stroke="var(--chart-temp)"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--panel)' }}
                connectNulls
              />
              {data.length > 0 ? (
                <ReferenceLine
                  x={data[0].time}
                  yAxisId="temperature"
                  stroke="var(--chart-now)"
                  strokeDasharray="4 4"
                  label={{ value: 'NOW', position: 'insideTopLeft', fill: 'var(--chart-now)', fontSize: 10, fontWeight: 700 }}
                />
              ) : null}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="chart-caption"><CloudRain size={14} aria-hidden="true" /> Chance of precipitation is shown as soft blue bars.</p>
    </section>
  )
}

interface DailyDatum {
  date: string
  low: number
  high: number
  rain: number
  code: number | null
}

export function DailyForecast({ forecast, temperatureUnit }: { forecast: Forecast; temperatureUnit: TemperatureUnit }) {
  const today = forecast.current.time.slice(0, 10)
  const days: DailyDatum[] = forecast.daily.time
    .map((date, index) => ({
      date,
      low: forecast.daily.temperature_2m_min[index],
      high: forecast.daily.temperature_2m_max[index],
      rain: forecast.daily.precipitation_probability_max[index],
      code: forecast.daily.weather_code[index],
    }))
    .filter((day) => day.date >= today && day.low !== null && day.high !== null)
    .slice(0, 7) as DailyDatum[]
  const lows = days.map((day) => day.low)
  const highs = days.map((day) => day.high)
  const weekLow = Math.min(...lows)
  const weekHigh = Math.max(...highs)
  const range = Math.max(1, weekHigh - weekLow)

  return (
    <section className="forecast-card glass-card daily-card" aria-labelledby="daily-title">
      <div className="section-heading">
        <div>
          <span className="section-kicker">LOOKING AHEAD</span>
          <h2 id="daily-title">7-day forecast</h2>
        </div>
        <span className="daily-high-low"><ArrowDown size={13} /> Low <ArrowUp size={13} /> High</span>
      </div>
      <div className="daily-list" role="list" aria-label="Seven day forecast">
        {days.map((day) => {
          const left = ((day.low - weekLow) / range) * 100
          const width = Math.max(5, ((day.high - day.low) / range) * 100)
          return (
            <div className={`daily-row ${day.date === today ? 'is-today' : ''}`} key={day.date} role="listitem">
              <span className="daily-day">{day.date === today ? 'Today' : weekdayLabel(day.date)}</span>
              <WeatherIcon code={day.code} size={22} className="daily-weather-icon" />
              <span className="daily-rain"><CloudRain size={13} aria-hidden="true" />{day.rain === null ? '—' : `${Math.round(day.rain)}%`}</span>
              <span className="daily-temp daily-low">{formatTemperature(day.low, temperatureUnit)}</span>
              <div className="daily-temp-track" aria-hidden="true">
                <span style={{ left: `${left}%`, width: `${width}%` }} />
              </div>
              <span className="daily-temp daily-high">{formatTemperature(day.high, temperatureUnit)}</span>
            </div>
          )
        })}
      </div>
      <p className="daily-note"><Moon size={14} aria-hidden="true" /> Temperatures show the expected low and high for each local day.</p>
    </section>
  )
}
