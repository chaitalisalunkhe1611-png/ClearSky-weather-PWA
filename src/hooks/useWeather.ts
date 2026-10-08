import { useCallback, useEffect, useState } from 'react'
import { fetchAirQuality, fetchForecast, type AirQuality, type Forecast, type WeatherLocation } from '../lib/api'
import { readWeatherCache, writeWeatherCache } from '../lib/storage'

const CACHE_TTL_MS = 15 * 60 * 1000

interface WeatherState {
  forecast: Forecast | null
  airQuality: AirQuality | null
  savedAt: number | null
  loading: boolean
  refreshing: boolean
  isStale: boolean
  error: string | null
}

const emptyState: WeatherState = {
  forecast: null,
  airQuality: null,
  savedAt: null,
  loading: true,
  refreshing: false,
  isStale: false,
  error: null,
}

export function useWeather(location: WeatherLocation) {
  const [state, setState] = useState<WeatherState>(emptyState)
  const [requestId, setRequestId] = useState(0)
  const [isOnline, setIsOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const online = () => setIsOnline(true)
    const offline = () => setIsOnline(false)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const cached = readWeatherCache(location)
    const age = cached ? Math.max(0, Date.now() - cached.savedAt) : Number.POSITIVE_INFINITY
    const cacheIsFresh = Boolean(cached && age < CACHE_TTL_MS)

    setState({
      forecast: cached?.forecast ?? null,
      airQuality: cached?.airQuality ?? null,
      savedAt: cached?.savedAt ?? null,
      loading: !cached,
      refreshing: Boolean(cached && isOnline && !cacheIsFresh),
      isStale: Boolean(cached && (!isOnline || !cacheIsFresh)),
      error: null,
    })

    // The local copy avoids needless requests during the 15-minute polite-cache window.
    // When offline, it is preferable to retain its true timestamp rather than let the
    // service worker's response cache make an old payload appear freshly fetched.
    if (cached && !isOnline) {
      return () => controller.abort()
    }
    if (cached && cacheIsFresh && isOnline) {
      const wait = Math.max(0, CACHE_TTL_MS - age)
      const timer = window.setTimeout(() => setRequestId((id) => id + 1), wait)
      return () => {
        window.clearTimeout(timer)
        controller.abort()
      }
    }

    async function load(): Promise<void> {
      try {
        const airPromise = fetchAirQuality(location, controller.signal).catch(() => null)
        const forecast = await fetchForecast(location, controller.signal)
        if (controller.signal.aborted) return
        const savedAt = isOnline ? Date.now() : cached?.savedAt ?? Date.now()
        const cachedAir = cached?.airQuality ?? null
        if (isOnline || !cached) writeWeatherCache(location, forecast, cachedAir, savedAt)
        setState({
          forecast,
          airQuality: cachedAir,
          savedAt,
          loading: false,
          refreshing: false,
          isStale: !isOnline,
          error: null,
        })

        // Air quality is supplemental; never let a slow AQI response hold up the forecast.
        const airQuality = await airPromise
        if (controller.signal.aborted || !airQuality) return
        if (isOnline || !cached) writeWeatherCache(location, forecast, airQuality, savedAt)
        setState((current) => ({ ...current, airQuality }))
      } catch (error) {
        if (controller.signal.aborted) return
        controller.abort()
        if (cached) {
          setState({
            forecast: cached.forecast,
            airQuality: cached.airQuality,
            savedAt: cached.savedAt,
            loading: false,
            refreshing: false,
            isStale: true,
            error: null,
          })
        } else {
          setState({ ...emptyState, loading: false, error: error instanceof Error ? error.message : 'Could not load this forecast.' })
        }
      }
    }

    void load()
    return () => controller.abort()
  }, [location, requestId, isOnline])

  const retry = useCallback(() => setRequestId((id) => id + 1), [])
  return { ...state, isOnline, retry }
}
