import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDownRight,
  ArrowRight,
  Clock3,
  Github,
  Heart,
  LocateFixed,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Trash2,
  CloudSun,
} from 'lucide-react'
import { CitySearch } from './components/CitySearch'
import { CurrentConditions, BriefingCard, DailyForecast, HourlyForecast } from './components/ForecastSections'
import { SettingsDialog } from './components/SettingsDialog'
import { useWeather } from './hooks/useWeather'
import { type WeatherLocation } from './lib/api'
import { readActiveLocation, readPreferences, readSavedLocations, writeActiveLocation, writePreferences, writeSavedLocations, type Preferences } from './lib/storage'
import { localDateTimeLabel } from './lib/time'
import { weatherMood } from './lib/wmo'
import './styles.css'

const DEFAULT_LOCATION: WeatherLocation = {
  name: 'New York',
  latitude: 40.7128,
  longitude: -74.006,
  admin1: 'New York',
  country: 'United States',
  countryCode: 'US',
  timezone: 'America/New_York',
}

function locationFromHash(): WeatherLocation | null {
  try {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const coordinates = params.get('loc')?.split(',').map(Number)
    if (!coordinates || coordinates.length !== 2 || !coordinates.every(Number.isFinite)) return null
    if (coordinates[0] < -90 || coordinates[0] > 90 || coordinates[1] < -180 || coordinates[1] > 180) return null
    return {
      name: params.get('name') || 'Shared location',
      latitude: coordinates[0],
      longitude: coordinates[1],
      admin1: params.get('region') || undefined,
      country: params.get('country') || undefined,
      countryCode: params.get('code') || undefined,
      timezone: params.get('tz') || undefined,
    }
  } catch {
    return null
  }
}

function sameLocation(first: WeatherLocation, second: WeatherLocation): boolean {
  return first.latitude.toFixed(3) === second.latitude.toFixed(3)
    && first.longitude.toFixed(3) === second.longitude.toFixed(3)
}

function locationHash(location: WeatherLocation): string {
  const params = new URLSearchParams({
    loc: `${location.latitude},${location.longitude}`,
    name: location.name,
  })
  if (location.admin1) params.set('region', location.admin1)
  if (location.country) params.set('country', location.country)
  if (location.countryCode) params.set('code', location.countryCode)
  if (location.timezone) params.set('tz', location.timezone)
  return params.toString()
}

function savedTimestamp(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(timestamp))
}

function getTimeOfDay(time: string): string {
  const hour = Number(time.split('T')[1]?.slice(0, 2) ?? new Date().getHours())
  if (hour < 12) return 'morning'
  if (hour < 17) return 'afternoon'
  return 'evening'
}

function isLocationSaved(saved: WeatherLocation[], location: WeatherLocation): boolean {
  return saved.some((item) => sameLocation(item, location))
}

function WeatherSkeleton() {
  return (
    <div className="weather-skeleton" aria-label="Loading forecast" aria-busy="true">
      <div className="skeleton-card skeleton-current"><span /><span /><span /><span /></div>
      <div className="skeleton-card skeleton-brief"><span /><span /><span /></div>
      <div className="skeleton-card skeleton-chart"><span /><span /><span /></div>
      <div className="skeleton-card skeleton-days"><span /><span /><span /><span /></div>
    </div>
  )
}

function App() {
  const [activeLocation, setActiveLocation] = useState<WeatherLocation>(() =>
    locationFromHash() ?? readActiveLocation() ?? DEFAULT_LOCATION,
  )
  const [savedLocations, setSavedLocations] = useState<WeatherLocation[]>(readSavedLocations)
  const [preferences, setPreferences] = useState<Preferences>(readPreferences)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsButtonRef = useRef<HTMLButtonElement>(null)
  const [locationBusy, setLocationBusy] = useState(false)
  const [locationMessage, setLocationMessage] = useState('')
  const weather = useWeather(activeLocation)
  const forecast = weather.forecast
  const description = forecast?.current.weather_code
  const mood = weatherMood(description)
  const todayIndex = useMemo(() => {
    if (!forecast) return -1
    const today = forecast.current.time.slice(0, 10)
    const exactIndex = forecast.daily.time.indexOf(today)
    return exactIndex >= 0 ? exactIndex : Math.max(0, forecast.daily.time.findIndex((date) => date >= today))
  }, [forecast])
  const sunrise = forecast && todayIndex >= 0 ? forecast.daily.sunrise[todayIndex] : null
  const sunset = forecast && todayIndex >= 0 ? forecast.daily.sunset[todayIndex] : null
  const isNight = Boolean(forecast && sunrise && sunset && (forecast.current.time < sunrise || forecast.current.time > sunset))
  const currentLabel = forecast ? localDateTimeLabel(forecast.current.time, { weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric' }) : ''
  const savedActive = isLocationSaved(savedLocations, activeLocation)

  useEffect(() => {
    writeActiveLocation(activeLocation)
    const hash = locationHash(activeLocation)
    const currentHash = window.location.hash.replace(/^#/, '')
    if (currentHash !== hash) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`)
    }
  }, [activeLocation])

  useEffect(() => {
    writeSavedLocations(savedLocations)
  }, [savedLocations])

  useEffect(() => {
    writePreferences(preferences)
    document.documentElement.dataset.theme = preferences.theme
  }, [preferences])

  function selectLocation(location: WeatherLocation) {
    setActiveLocation(location)
    setLocationMessage('')
  }

  function toggleSavedLocation() {
    setSavedLocations((locations) => isLocationSaved(locations, activeLocation)
      ? locations.filter((location) => !sameLocation(location, activeLocation))
      : [activeLocation, ...locations])
  }

  function removeSavedLocation(location: WeatherLocation) {
    setSavedLocations((locations) => locations.filter((item) => !sameLocation(item, location)))
  }

  function closeSettings() {
    setSettingsOpen(false)
    window.requestAnimationFrame(() => settingsButtonRef.current?.focus())
  }

  function useMyLocation() {
    setLocationMessage('')
    if (!navigator.geolocation) {
      setLocationMessage('Location isn’t available in this browser. You can search for a city instead.')
      return
    }
    setLocationBusy(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        selectLocation({
          name: 'Your location',
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        })
        setLocationBusy(false)
      },
      (error) => {
        setLocationBusy(false)
        if (error.code === error.PERMISSION_DENIED) {
          setLocationMessage('Location access was declined. Search for a city instead—your location is never requested without asking.')
        } else if (error.code === error.TIMEOUT) {
          setLocationMessage('That took too long. Try again, or search for a city.')
        } else {
          setLocationMessage('We couldn’t get a location fix. Try again, or search for a city.')
        }
      },
      { enableHighAccuracy: false, timeout: 12_000, maximumAge: 5 * 60_000 },
    )
  }

  return (
    <div className="app-shell" data-weather={mood} data-time={isNight ? 'night' : 'day'}>
      <a className="skip-link" href="#main-content">Skip to forecast</a>
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <header className="topbar page-wrap">
        <a className="brand" href={`${window.location.pathname}${window.location.search}#${locationHash(activeLocation)}`} aria-label="ClearSky home">
          <span className="brand-mark"><CloudSun size={23} strokeWidth={1.8} aria-hidden="true" /></span>
          <span className="brand-copy"><strong>ClearSky</strong><small>YOUR WEATHER, QUIETER</small></span>
        </a>
        <div className="topbar-note"><ShieldCheck size={14} aria-hidden="true" /> Private by nature. Free by design.</div>
      </header>

      <main className="page-wrap" id="main-content">
        <div className="search-toolbar">
          <CitySearch onSelect={selectLocation} />
          <button className="locate-button" type="button" onClick={useMyLocation} disabled={locationBusy}>
            {locationBusy ? <LoaderCircle size={17} className="search-spinner" aria-hidden="true" /> : <LocateFixed size={17} aria-hidden="true" />}
            <span>{locationBusy ? 'Finding you…' : 'Use my location'}</span>
          </button>
          <button className="settings-button icon-button" type="button" onClick={() => setSettingsOpen(true)} aria-label="Open settings" ref={settingsButtonRef}>
            <Settings2 size={19} aria-hidden="true" />
          </button>
        </div>
        {locationMessage ? <p className="location-message" role="status">{locationMessage}</p> : null}

        <div className="page-intro">
          <div>
            <span className="eyebrow"><span className="intro-rule" /> YOUR SKY, AT A GLANCE</span>
            <h1>Good {forecast ? getTimeOfDay(forecast.current.time) : 'day'}.</h1>
            <p>Here’s what the sky has in store for <strong>{activeLocation.name}</strong>.</p>
          </div>
          {currentLabel ? (
            <div className="local-clock"><Clock3 size={16} aria-hidden="true" /><span>{currentLabel}</span></div>
          ) : null}
        </div>

        {savedLocations.length > 0 ? (
          <nav className="saved-places" aria-label="Saved places">
            <span className="saved-label"><Heart size={14} aria-hidden="true" /> SAVED PLACES</span>
            <div className="saved-place-list">
              {savedLocations.map((location) => {
                const active = sameLocation(location, activeLocation)
                return (
                  <div className={`saved-place ${active ? 'is-active' : ''}`} key={`${location.latitude}-${location.longitude}`}>
                    <button type="button" className="saved-place-select" onClick={() => selectLocation(location)} aria-current={active ? 'location' : undefined}>
                      <MapPin size={13} aria-hidden="true" />{location.name}
                    </button>
                    <button type="button" className="saved-place-remove" onClick={() => removeSavedLocation(location)} aria-label={`Remove ${location.name} from saved places`}>
                      <Trash2 size={13} aria-hidden="true" />
                    </button>
                  </div>
                )
              })}
            </div>
          </nav>
        ) : null}

        {weather.isStale && weather.savedAt ? (
          <div className="offline-banner" role="status">
            <span className="offline-dot" />
            <span>Showing data from <strong>{savedTimestamp(weather.savedAt)}</strong>. {weather.refreshing ? 'Checking for updates…' : weather.isOnline ? 'We couldn’t refresh just now.' : 'You’re offline.'}</span>
            <button type="button" onClick={weather.retry} aria-label="Try refreshing the forecast"><RefreshCw size={15} aria-hidden="true" /></button>
          </div>
        ) : null}

        {weather.loading && !forecast ? <WeatherSkeleton /> : null}
        {weather.error && !forecast ? (
          <section className="error-card glass-card" aria-labelledby="error-title">
            <span className="error-icon"><ArrowDownRight size={22} aria-hidden="true" /></span>
            <div>
              <span className="section-kicker">A LITTLE CLOUD IN THE WAY</span>
              <h2 id="error-title">We couldn’t load this forecast.</h2>
              <p>Check your connection and try again. ClearSky only contacts Open-Meteo for the weather you asked for.</p>
              <button className="primary-button" type="button" onClick={weather.retry}><RefreshCw size={16} aria-hidden="true" /> Try again</button>
            </div>
          </section>
        ) : null}

        {forecast ? (
          <>
            {weather.refreshing ? <p className="quiet-refresh" aria-live="polite"><LoaderCircle size={13} className="search-spinner" /> Updating forecast…</p> : null}
            <div className="current-grid">
              <CurrentConditions
                forecast={forecast}
                airQuality={weather.airQuality}
                location={activeLocation}
                temperatureUnit={preferences.temperatureUnit}
                windUnit={preferences.windUnit}
                isSaved={savedActive}
                onToggleSaved={toggleSavedLocation}
                night={isNight}
              />
              <BriefingCard forecast={forecast} temperatureUnit={preferences.temperatureUnit} windUnit={preferences.windUnit} />
            </div>

            <div className="forecast-grid">
              <HourlyForecast forecast={forecast} temperatureUnit={preferences.temperatureUnit} />
              <DailyForecast forecast={forecast} temperatureUnit={preferences.temperatureUnit} />
            </div>
          </>
        ) : null}

        <footer className="site-footer">
          <div className="footer-brand"><span className="footer-sun"><CloudSun size={21} aria-hidden="true" /></span><span>ClearSky</span></div>
          <p className="privacy-note">No accounts. No tracking. Your saved places and settings stay on this device.</p>
          <div className="footer-links">
            <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com <span>(CC BY 4.0)</span><ArrowRight size={13} aria-hidden="true" /></a>
            <a href="https://github.com/chaitalisalunkhe1611-png/ai_cartoonmaker" target="_blank" rel="noreferrer" aria-label="ClearSky on GitHub">GitHub <Github size={14} aria-hidden="true" /></a>
          </div>
        </footer>
      </main>
      {settingsOpen ? <SettingsDialog preferences={preferences} onChange={setPreferences} onClose={closeSettings} /> : null}
    </div>
  )
}

export default App
