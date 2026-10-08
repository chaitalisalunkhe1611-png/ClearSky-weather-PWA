export type WeatherKind = 'sun' | 'partly-cloudy' | 'cloud' | 'fog' | 'drizzle' | 'rain' | 'snow' | 'storm'

export interface WeatherDescription {
  label: string
  kind: WeatherKind
}

const descriptions: Record<number, WeatherDescription> = {
  0: { label: 'Clear sky', kind: 'sun' },
  1: { label: 'Mainly clear', kind: 'partly-cloudy' },
  2: { label: 'Partly cloudy', kind: 'partly-cloudy' },
  3: { label: 'Overcast', kind: 'cloud' },
  45: { label: 'Fog', kind: 'fog' },
  48: { label: 'Depositing rime fog', kind: 'fog' },
  51: { label: 'Light drizzle', kind: 'drizzle' },
  53: { label: 'Drizzle', kind: 'drizzle' },
  55: { label: 'Dense drizzle', kind: 'drizzle' },
  56: { label: 'Light freezing drizzle', kind: 'drizzle' },
  57: { label: 'Freezing drizzle', kind: 'drizzle' },
  61: { label: 'Light rain', kind: 'rain' },
  63: { label: 'Rain', kind: 'rain' },
  65: { label: 'Heavy rain', kind: 'rain' },
  66: { label: 'Light freezing rain', kind: 'rain' },
  67: { label: 'Freezing rain', kind: 'rain' },
  71: { label: 'Light snow', kind: 'snow' },
  73: { label: 'Snow', kind: 'snow' },
  75: { label: 'Heavy snow', kind: 'snow' },
  77: { label: 'Snow grains', kind: 'snow' },
  80: { label: 'Light rain showers', kind: 'rain' },
  81: { label: 'Rain showers', kind: 'rain' },
  82: { label: 'Violent rain showers', kind: 'rain' },
  85: { label: 'Snow showers', kind: 'snow' },
  86: { label: 'Heavy snow showers', kind: 'snow' },
  95: { label: 'Thunderstorm', kind: 'storm' },
  96: { label: 'Thunderstorm with hail', kind: 'storm' },
  99: { label: 'Thunderstorm with heavy hail', kind: 'storm' },
}

export function describeWeather(code: number | null | undefined): WeatherDescription {
  if (code === null || code === undefined) return { label: 'Conditions unavailable', kind: 'cloud' }
  if (code >= 95) return descriptions[code] ?? { label: 'Thunderstorm', kind: 'storm' }
  return descriptions[code] ?? { label: 'Conditions unavailable', kind: 'cloud' }
}

export function weatherMood(code: number | null | undefined): 'clear' | 'cloudy' | 'rainy' | 'snowy' | 'stormy' | 'foggy' {
  const kind = describeWeather(code).kind
  if (kind === 'sun') return 'clear'
  if (kind === 'partly-cloudy' || kind === 'cloud') return 'cloudy'
  if (kind === 'fog') return 'foggy'
  if (kind === 'drizzle' || kind === 'rain') return 'rainy'
  if (kind === 'snow') return 'snowy'
  return 'stormy'
}
